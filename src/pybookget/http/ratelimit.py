"""Request rate limiting with pyrate-limiter (async).

``Config.rate_limits`` holds (requests, seconds) windows that all apply at once,
e.g. ``[(10, 1), (80, 10), (400, 60)]``. Every httpx client made by
``create_client()`` waits on the same limiter before each request (via an httpx
request event hook, so retries, redirects and fallback URLs count, and proxies
make no difference), so the limits hold across all concurrent downloads that
share one Config.

asyncio locks are bound to the event loop they are first used in, so the
limiter is kept per event loop: code that calls ``asyncio.run()`` several times
with one Config (e.g. the interactive CLI) gets a fresh limiter in each loop.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pyrate_limiter import Limiter, Rate, validate_rate_list

if TYPE_CHECKING:  # pragma: no cover
    from pybookget.config import Config


def to_rates(rate_limits: list[tuple[int, float]]) -> list[Rate]:
    """Convert (requests, seconds) windows to pyrate-limiter Rates, shortest window first.

    Raises:
        ValueError: if a window is not positive, or the windows contradict each
            other (e.g. a longer window allowing fewer requests than a shorter one).
    """
    rates = []
    for requests, seconds in rate_limits:
        if requests < 1 or seconds <= 0:
            raise ValueError(
                f"Invalid rate limit ({requests}, {seconds}): "
                "requests must be >= 1 and seconds > 0"
            )
        rates.append(Rate(int(requests), max(1, round(seconds * 1000))))
    rates.sort(key=lambda rate: rate.interval)
    if not validate_rate_list(rates):
        raise ValueError(
            f"Inconsistent rate limits {rate_limits}: longer windows must allow more "
            "requests, but a lower average rate, than shorter ones"
        )
    return rates


def build_limiter(rate_limits: list[tuple[int, float]]) -> Limiter:
    """Create a pyrate-limiter Limiter from (requests, seconds) windows."""
    return Limiter(to_rates(rate_limits))


def get_limiter(config: Config) -> Limiter | None:
    """Return the limiter shared by all clients of ``config`` in the running event loop.

    Returns None when ``config.rate_limits`` is not set. Must be called from
    inside a running event loop.
    """
    if not config.rate_limits:
        return None
    loop = asyncio.get_running_loop()
    limiter = config._limiters.get(loop)
    if limiter is None:
        limiter = build_limiter(config.rate_limits)
        config._limiters[loop] = limiter
    return limiter


async def wait_for_rate_limit(config: Config) -> None:
    """Wait until ``config.rate_limits`` allow one more request (no-op without limits)."""
    limiter = get_limiter(config)
    if limiter is not None:
        await limiter.try_acquire_async("pybookget")


def parse_rate_limit(spec: str) -> tuple[int, float]:
    """Parse a CLI rate limit like ``"10/1"`` (10 requests per 1 second) or ``"400/60"``."""
    try:
        requests, seconds = spec.split("/")
        parsed = (int(requests), float(seconds))
    except ValueError:
        raise ValueError(f"Invalid rate limit {spec!r}: expected REQUESTS/SECONDS, e.g. 10/1")
    if parsed[0] < 1 or parsed[1] <= 0:
        raise ValueError(f"Invalid rate limit {spec!r}: requests must be >= 1 and seconds > 0")
    return parsed
