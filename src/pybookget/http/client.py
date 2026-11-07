"""HTTP client utilities using httpx directly (async-only).

This module provides helper functions for creating async httpx clients with
proper configuration from Config objects. No custom wrappers - just
direct httpx usage for maximum resilience.

Retry logic is handled by tenacity decorators for explicit and configurable
retry behavior.
"""

import asyncio
import logging
import os
import tempfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from pybookget.config import Config
from pybookget.http.cookies import load_cookies_from_file
from pybookget.http.headers import load_headers_from_file
from pybookget.http.ratelimit import wait_for_rate_limit

logger = logging.getLogger(__name__)


def create_client(
    config: Config, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Create an async httpx client from configuration.

    If ``config.rate_limits`` is set, every request (including retries) first
    waits on the limiter shared by all clients of this config. If
    ``config.attempt_timeout`` is set, each attempt must be done within its
    deadline (``attempt_deadline``), counted from when it is sent, after the
    rate limits; the response body is then read in a response hook, so a
    response is complete when ``client.get`` returns (no streaming). An attempt
    past its deadline raises ``httpx.ReadTimeout``, which ``is_retryable``
    retries.

    Args:
        config: Configuration object
        transport: Optional httpx transport (e.g. httpx.MockTransport in tests)

    Returns:
        Configured httpx.AsyncClient instance

    Example:
        >>> config = Config()
        >>> async with create_client(config) as client:
        ...     response = await client.get(url)
    """
    # Build headers with user agent
    if config.use_fake_user_agent:
        # Generate random user agent for request masking
        from fake_useragent import UserAgent

        ua = UserAgent()
        user_agent = ua.random
    else:
        # Use static user agent from config
        user_agent = config.user_agent

    headers = {'User-Agent': user_agent}

    # Load additional headers from file
    if config.header_file and Path(config.header_file).exists():
        file_headers = load_headers_from_file(config.header_file)
        headers.update(file_headers)

    # Build cookies
    cookies = {}
    if config.cookie_file and Path(config.cookie_file).exists():
        cookie_list = load_cookies_from_file(config.cookie_file)
        for cookie in cookie_list:
            cookies[cookie.name] = cookie.value

    # Rate limiting: wait on the shared limiter before every request
    event_hooks = {}
    if config.rate_limits:
        async def _wait_for_rate_limit(request: httpx.Request) -> None:
            await wait_for_rate_limit(config)

        event_hooks["request"] = [_wait_for_rate_limit]

    # A deadline per attempt, started after the rate limits (the hooks run in order)
    if config.attempt_timeout is not None:
        event_hooks.setdefault("request", []).append(_attempt_started(config))
        event_hooks["response"] = [_attempt_finished(config)]

    # Create async client with configuration. By default connections are not kept
    # alive, so every request opens a new one (config.max_keepalive_connections)
    return httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        timeout=config.timeout,
        verify=config.verify_ssl,
        follow_redirects=True,
        http2=True,
        proxy=config.proxy,
        trust_env=config.trust_env,
        limits=httpx.Limits(max_keepalive_connections=config.max_keepalive_connections),
        event_hooks=event_hooks,
        transport=transport,
    )


_ATTEMPT_START = "pybookget.attempt_start"


def attempt_deadline(config: Config, content_length: str | None) -> float:
    """Seconds one attempt may take: ``config.attempt_timeout``, plus the
    response's Content-Length divided by ``config.attempt_min_rate`` when both
    are known (a large file gets the time it needs at that rate)."""
    seconds = float(config.attempt_timeout)
    if config.attempt_min_rate and content_length and content_length.isdigit():
        seconds += int(content_length) / config.attempt_min_rate
    return seconds


def _attempt_started(config: Config):
    async def hook(request: httpx.Request) -> None:
        request.extensions[_ATTEMPT_START] = asyncio.get_running_loop().time()
        # until the response's headers: no phase may take longer than the whole attempt
        limit = float(config.attempt_timeout)
        timeouts = dict(request.extensions.get("timeout") or {})
        request.extensions["timeout"] = {
            phase: limit if timeouts.get(phase) is None else min(timeouts[phase], limit)
            for phase in ("connect", "read", "write", "pool")
        }
    return hook


def _attempt_finished(config: Config):
    async def hook(response: httpx.Response) -> None:
        start = response.request.extensions.get(_ATTEMPT_START)
        if start is None:
            return
        seconds = attempt_deadline(config, response.headers.get("Content-Length"))
        remaining = start + seconds - asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(max(remaining, 0.0)):
                await response.aread()
        except TimeoutError:
            await response.aclose()
            raise httpx.ReadTimeout(
                f"attempt took longer than its deadline ({seconds:.1f} s)", request=response.request
            ) from None
    return hook


# HTTP statuses worth retrying: the server is busy, overloaded or briefly failing.
# Every other 4xx (404, 403, ...) is final and fails immediately.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_retryable(exc: BaseException) -> bool:
    """Whether a failed request should be retried.

    Retries transport failures (timeouts, connection and proxy errors, broken
    connections) and the statuses in ``RETRYABLE_STATUS_CODES``.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP-date), or None."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class wait_retry_after_or_exponential(wait_base):
    """Exponential backoff, or the server's Retry-After if that is longer.

    Retry-After (sent with 429 and 503) is honoured up to ``retry_after_max``
    seconds, so a server asking us to slow down gets at least that pause.
    """

    def __init__(self, config: Config):
        self.exponential = wait_exponential(
            multiplier=config.retry_multiplier,
            min=config.retry_wait_min,
            max=config.retry_wait_max,
        )
        self.retry_after_max = config.retry_after_max

    def __call__(self, retry_state: RetryCallState) -> float:
        wait = self.exponential(retry_state)
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, httpx.HTTPStatusError):
            retry_after = parse_retry_after(exc.response.headers.get("Retry-After"))
            if retry_after is not None:
                wait = max(wait, min(retry_after, self.retry_after_max))
        return wait


def create_retry_decorator(config: Config):
    """Create a tenacity retry decorator from config.

    Retries only what ``is_retryable`` accepts, up to ``config.max_retries``
    attempts, waiting with exponential backoff or the server's Retry-After.

    Args:
        config: Configuration object

    Returns:
        Configured retry decorator
    """
    return retry(
        stop=stop_after_attempt(config.max_retries),
        wait=wait_retry_after_or_exponential(config),
        retry=retry_if_exception(is_retryable),
        reraise=True,
    )


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_path: Path,
    config: Config,
    headers: dict[str, str] | None = None,
) -> Path:
    """Download a file using httpx client with tenacity retry logic.

    The file appears at ``dest_path`` only once it is complete: the content is
    written to a hidden temporary file in the same directory and renamed into
    place, so an interrupted run never leaves a truncated file that a later run
    would skip as done. If the file exists, it is skipped (file-level resumability).

    Retries are handled by tenacity with exponential backoff.

    Args:
        client: httpx.AsyncClient instance
        url: URL to download from
        dest_path: Destination file path
        config: Config object for retry settings
        headers: Optional additional headers

    Returns:
        Path to downloaded file

    Raises:
        httpx.HTTPError: If download fails after all retries
    """
    # Skip if file already exists (file-level resumability)
    if dest_path.exists():
        return dest_path

    # Ensure parent directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Download the entire file into memory first (with retries), then write it to disk
    content = (await fetch(client, url, config, headers=headers)).content

    # Write complete file to disk atomically (temporary file, then rename), in a
    # thread so disk I/O never stalls the other downloads on the event loop
    await asyncio.to_thread(write_atomically, dest_path, content)

    return dest_path


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    config: Config,
    headers: dict[str, str] | None = None,
    fallback_url: str | None = None,
) -> httpx.Response:
    """GET ``url`` with tenacity retry logic and return the (read) response.

    Retries what ``is_retryable`` accepts, as ``download_file`` does. If the URL
    returns 404 and there is a ``fallback_url``, that is fetched instead (with
    its own retries). ``response.url`` says which URL, after redirects, the
    content came from.

    Raises:
        httpx.HTTPError: If the request (and the fallback) fails after all retries
    """

    @create_retry_decorator(config)
    async def _get(u: str) -> httpx.Response:
        response = await client.get(u, headers=headers)
        response.raise_for_status()
        return response

    try:
        return await _get(url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404 or not fallback_url:
            raise
        logger.warning(f"Primary URL returned 404, trying fallback: {fallback_url}")
        return await _get(fallback_url)


def write_atomically(dest_path: Path, content: bytes) -> None:
    """Write ``content`` to ``dest_path`` so the file only ever exists complete.

    Writes to a hidden ``.<name>.<random>.part`` file in the same directory,
    then renames it over ``dest_path`` (atomic on POSIX and Windows), so a
    killed or crashed process never leaves a truncated file behind. There is
    no fsync: a power loss or OS crash right after the rename could still lose
    the data, which costs too much to rule out for millions of files. The
    temporary file is removed if anything fails.
    """
    fd, tmp_name = tempfile.mkstemp(dir=dest_path.parent, prefix=f".{dest_path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.replace(tmp_name, dest_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
