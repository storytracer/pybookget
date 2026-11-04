"""Tests for request rate limiting (Config.rate_limits, pyrate-limiter via an httpx hook)."""

import asyncio
import time
from pathlib import Path

import httpx
import pytest

from pybookget.config import Config
from pybookget.http import client as client_module
from pybookget.http import download as download_module
from pybookget.http.client import create_client, download_file
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.http.ratelimit import get_limiter, parse_rate_limit


def ok_transport(calls=None):
    """A fake server answering 200 to everything, optionally recording request times."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(time.monotonic())
        return httpx.Response(200, content=b"image-bytes")

    return httpx.MockTransport(handler)


def make_config(tmp_path, **kwargs) -> Config:
    kwargs.setdefault("proxy", None)
    config = Config(download_dir=str(tmp_path), show_progress=False, **kwargs)
    config.proxy = kwargs["proxy"]  # ignore HTTPS_PROXY/HTTP_PROXY from the test environment
    return config


# --- parsing and validation -------------------------------------------------------------


def test_parse_rate_limit():
    assert parse_rate_limit("10/1") == (10, 1.0)
    assert parse_rate_limit("400/60") == (400, 60.0)
    assert parse_rate_limit("1/0.5") == (1, 0.5)


@pytest.mark.parametrize("spec", ["10", "10/", "a/1", "0/1", "10/0", "10/-1", "1/2/3"])
def test_parse_rate_limit_rejects(spec):
    with pytest.raises(ValueError):
        parse_rate_limit(spec)


def test_config_normalises_rate_limits(tmp_path):
    config = make_config(tmp_path, rate_limits=[("10", "1"), (80, 10)])
    assert config.rate_limits == [(10, 1.0), (80, 10.0)]


@pytest.mark.parametrize(
    "rate_limits",
    [
        [(0, 1)],  # no requests allowed
        [(10, 0)],  # zero-length window
        [(10, 1), (5, 10)],  # longer window allows fewer requests than a shorter one
    ],
)
def test_config_rejects_invalid_rate_limits(tmp_path, rate_limits):
    with pytest.raises(ValueError):
        make_config(tmp_path, rate_limits=rate_limits)


def test_no_rate_limits_means_no_limiter(tmp_path):
    config = make_config(tmp_path)

    async def main():
        return get_limiter(config)

    assert asyncio.run(main()) is None


# --- enforcement ------------------------------------------------------------------------


def test_limit_is_shared_by_all_clients_of_a_config(tmp_path):
    """15 requests over two clients at 5 per 0.5 s need three windows (>= ~1 s)."""
    config = make_config(tmp_path, rate_limits=[(5, 0.5)])
    calls = []

    async def main():
        a = create_client(config, transport=ok_transport(calls))
        b = create_client(config, transport=ok_transport(calls))
        try:
            await asyncio.gather(
                *(c.get(f"https://example.org/{i}") for i, c in enumerate([a, b] * 7 + [a]))
            )
        finally:
            await a.aclose()
            await b.aclose()

    start = time.monotonic()
    asyncio.run(main())
    assert len(calls) == 15
    assert time.monotonic() - start >= 0.95
    # no window of 0.5 s holds more than 5 requests (small tolerance for timer jitter)
    calls.sort()
    for i in range(len(calls) - 5):
        assert calls[i + 5] - calls[i] >= 0.45


def test_without_limits_requests_are_not_delayed(tmp_path):
    config = make_config(tmp_path)

    async def main():
        async with create_client(config, transport=ok_transport()) as c:
            await asyncio.gather(*(c.get(f"https://example.org/{i}") for i in range(30)))

    start = time.monotonic()
    asyncio.run(main())
    assert time.monotonic() - start < 0.5


def test_retries_count_against_the_limit(tmp_path):
    """A 500 followed by a retry: the retry waits for the next slot (1 per 0.5 s)."""
    config = make_config(
        tmp_path, rate_limits=[(1, 0.5)], max_retries=2, retry_wait_min=0, retry_wait_max=0
    )
    calls = []

    def handler(request):
        calls.append(time.monotonic())
        return httpx.Response(500 if len(calls) == 1 else 200, content=b"x")

    async def main():
        async with create_client(config, transport=httpx.MockTransport(handler)) as c:
            await download_file(c, "https://example.org/a.jp2", tmp_path / "a.jp2", config)

    asyncio.run(main())
    assert len(calls) == 2
    assert calls[1] - calls[0] >= 0.45
    assert (tmp_path / "a.jp2").read_bytes() == b"x"


def test_limit_applies_when_a_proxy_is_configured(tmp_path):
    """Proxied requests bypass custom transports in httpx, but not request hooks.

    The proxy is a closed local port, so each request fails at once; three requests
    at 1 per 0.3 s still take >= ~0.6 s because each waits for the limiter first.
    """
    config = make_config(tmp_path, rate_limits=[(1, 0.3)], proxy="http://127.0.0.1:9")

    async def main():
        async with create_client(config) as c:
            for i in range(3):
                with pytest.raises(httpx.ConnectError):
                    await c.get(f"https://example.org/{i}")

    start = time.monotonic()
    asyncio.run(main())
    assert time.monotonic() - start >= 0.55


def test_one_config_works_across_event_loops(tmp_path):
    """The interactive CLI calls asyncio.run() repeatedly with one Config."""
    config = make_config(tmp_path, rate_limits=[(5, 0.5)])

    async def main():
        async with create_client(config, transport=ok_transport()) as c:
            r = await c.get("https://example.org/x")
            return r.status_code

    assert asyncio.run(main()) == 200
    assert asyncio.run(main()) == 200


def test_download_manager_respects_the_limit(tmp_path, monkeypatch):
    """6 files at 3 per 0.3 s need two windows; all files are written."""
    config = make_config(tmp_path, rate_limits=[(3, 0.3)])
    calls = []
    monkeypatch.setattr(
        download_module,
        "create_client",
        lambda cfg: client_module.create_client(cfg, transport=ok_transport(calls)),
    )
    tasks = [
        DownloadTask(url=f"https://example.org/{i:04d}.jp2", save_path=tmp_path / f"{i:04d}.jp2")
        for i in range(6)
    ]
    dm = DownloadManager(config, max_workers=6, show_progress=False)
    dm.add_tasks(tasks)

    start = time.monotonic()
    assert asyncio.run(dm.execute()) == 6
    assert time.monotonic() - start >= 0.28
    assert len(calls) == 6
    assert all(Path(t.save_path).read_bytes() == b"image-bytes" for t in tasks)
