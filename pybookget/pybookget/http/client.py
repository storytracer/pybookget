"""HTTP client utilities using httpx directly (async-only).

This module provides helper functions for creating async httpx clients with
proper configuration from Config objects. No custom wrappers - just
direct httpx usage for maximum resilience.

Retry logic is handled by tenacity decorators for explicit and configurable
retry behavior.
"""

from pathlib import Path
from typing import Dict, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from pybookget.config import Config
from pybookget.http.cookies import load_cookies_from_file
from pybookget.http.headers import load_headers_from_file


def create_client(config: Config) -> httpx.AsyncClient:
    """Create an async httpx client from configuration.

    Args:
        config: Configuration object

    Returns:
        Configured httpx.AsyncClient instance

    Example:
        >>> config = Config()
        >>> async with create_client(config) as client:
        ...     response = await client.get(url)
    """
    # Build headers
    headers = {'User-Agent': config.user_agent}

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

    # Create async client with configuration
    return httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        timeout=config.timeout,
        verify=config.verify_ssl,
        follow_redirects=True,
        http2=True,
        proxies=config.proxy,
    )


def create_retry_decorator(config: Config):
    """Create a tenacity retry decorator from config.

    Args:
        config: Configuration object

    Returns:
        Configured retry decorator
    """
    return retry(
        stop=stop_after_attempt(config.max_retries),
        wait=wait_exponential(
            multiplier=config.retry_multiplier,
            min=config.retry_wait_min,
            max=config.retry_wait_max,
        ),
        retry=retry_if_exception_type((
            httpx.HTTPError,
            httpx.TimeoutException,
            httpx.NetworkError,
        )),
        reraise=True,
    )


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_path: Path,
    config: Config,
    headers: Optional[Dict[str, str]] = None,
) -> Path:
    """Download a file using httpx client with tenacity retry logic.

    File is only written to disk after complete download.
    If file exists, it is skipped (file-level resumability).

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

    # Create retry decorator from config
    retry_decorator = create_retry_decorator(config)

    # Define async download function with retry logic
    @retry_decorator
    async def _download_with_retry():
        # Download entire file into memory first, then write to disk
        # This ensures atomic writes - file only exists if fully downloaded
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content

    # Execute download with retries
    content = await _download_with_retry()

    # Write complete file to disk atomically
    dest_path.write_bytes(content)

    return dest_path
