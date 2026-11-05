"""Tests for the download manager and download_file (no network: httpx.MockTransport)."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from pybookget.config import Config
from pybookget.http import client as client_module
from pybookget.http import download as download_module
from pybookget.http.client import create_client, download_file, parse_retry_after
from pybookget.http.download import DownloadManager, DownloadTask


def make_config(tmp_path, **kwargs) -> Config:
    kwargs.setdefault("retry_wait_min", 0)
    kwargs.setdefault("retry_wait_max", 0)
    kwargs.setdefault("trust_env", False)  # ignore the test environment's proxy settings
    return Config(download_dir=str(tmp_path), show_progress=False, **kwargs)


def use_transport(monkeypatch, handler):
    """Make DownloadManager's client use a fake server."""
    monkeypatch.setattr(
        download_module,
        "create_client",
        lambda cfg: client_module.create_client(cfg, transport=httpx.MockTransport(handler)),
    )


def fetch(config, handler, url, dest):
    async def main():
        async with create_client(config, transport=httpx.MockTransport(handler)) as c:
            return await download_file(c, url, dest, config)

    return asyncio.run(main())


# --- streaming --------------------------------------------------------------------------


def test_run_streams_tasks_with_bounded_lookahead(tmp_path, monkeypatch):
    """A generator of 2,000 tasks is consumed lazily: never more than ~3x workers ahead."""
    workers = 4
    produced = 0
    finished = 0
    max_ahead = 0

    async def handler(request):
        await asyncio.sleep(0.001)
        return httpx.Response(200, content=b"x")

    use_transport(monkeypatch, handler)

    def tasks():
        nonlocal produced, max_ahead
        for i in range(2000):
            produced += 1
            max_ahead = max(max_ahead, produced - finished)
            yield DownloadTask(url=f"https://example.org/{i}", save_path=tmp_path / f"{i}.bin")

    def callback(task, success):
        nonlocal finished
        finished += 1

    dm = DownloadManager(make_config(tmp_path), max_workers=workers, show_progress=False)
    stats = asyncio.run(dm.run(tasks(), callback=callback))

    assert (stats.successful, stats.failed) == (2000, 0)
    assert finished == 2000
    # queue (2 * workers) + one task per worker + the one being put
    assert max_ahead <= 3 * workers + 1


def test_run_accepts_async_iterables(tmp_path, monkeypatch):
    use_transport(monkeypatch, lambda request: httpx.Response(200, content=b"x"))

    async def tasks():
        for i in range(10):
            yield DownloadTask(url=f"https://example.org/{i}", save_path=tmp_path / f"{i}.bin")

    dm = DownloadManager(make_config(tmp_path), max_workers=3, show_progress=False)
    stats = asyncio.run(dm.run(tasks()))
    assert stats.successful == 10
    assert len(list(tmp_path.glob("*.bin"))) == 10


def test_existing_files_are_skipped(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=b"new")

    use_transport(monkeypatch, handler)
    (tmp_path / "0.bin").write_bytes(b"old")
    tasks = [DownloadTask(url=f"https://example.org/{i}", save_path=tmp_path / f"{i}.bin") for i in range(3)]

    stats = asyncio.run(DownloadManager(make_config(tmp_path), max_workers=2, show_progress=False).run(tasks))
    assert (stats.successful, stats.skipped, stats.failed) == (3, 1, 0)
    assert sorted(calls) == ["/1", "/2"]
    assert (tmp_path / "0.bin").read_bytes() == b"old"


# --- results belong to the right task ----------------------------------------------------


def test_callback_reports_each_tasks_own_result(tmp_path, monkeypatch):
    """Early tasks finish last; failures must still be reported for the failing task."""

    async def handler(request):
        i = int(request.url.path.strip("/"))
        await asyncio.sleep(0.05 * (5 - i))  # task 0 slowest, task 4 fastest
        return httpx.Response(404 if i % 2 else 200, content=b"x")

    use_transport(monkeypatch, handler)
    tasks = [DownloadTask(url=f"https://example.org/{i}", save_path=tmp_path / f"{i}.bin") for i in range(5)]
    results = {}

    dm = DownloadManager(make_config(tmp_path), max_workers=5, show_progress=False)
    dm.add_tasks(tasks)
    assert asyncio.run(dm.execute(callback=lambda t, ok: results.__setitem__(t.url, ok))) == 3

    assert results == {f"https://example.org/{i}": i % 2 == 0 for i in range(5)}
    assert [t.error for t in tasks] == [None, "HTTP 404", None, "HTTP 404", None]


def test_failing_callback_does_not_stop_the_run(tmp_path, monkeypatch):
    use_transport(monkeypatch, lambda request: httpx.Response(200, content=b"x"))
    tasks = [DownloadTask(url=f"https://example.org/{i}", save_path=tmp_path / f"{i}.bin") for i in range(4)]

    def callback(task, success):
        raise RuntimeError("boom")

    stats = asyncio.run(DownloadManager(make_config(tmp_path), max_workers=2, show_progress=False).run(tasks, callback=callback))
    assert stats.successful == 4


# --- retry policy -----------------------------------------------------------------------


def test_404_is_not_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        fetch(make_config(tmp_path, max_retries=3), handler, "https://example.org/a", tmp_path / "a")
    assert len(calls) == 1


def test_404_still_uses_the_fallback_url(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(404 if request.url.path == "/primary" else 200, content=b"fallback")

    use_transport(monkeypatch, handler)
    task = DownloadTask(
        url="https://example.org/primary",
        fallback_url="https://example.org/fallback",
        save_path=tmp_path / "a.jpg",
    )
    stats = asyncio.run(DownloadManager(make_config(tmp_path, max_retries=3), show_progress=False).run([task]))
    assert stats.successful == 1
    assert calls == ["/primary", "/fallback"]
    assert (tmp_path / "a.jpg").read_bytes() == b"fallback"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_server_errors_are_retried(tmp_path, status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status if len(calls) < 3 else 200, content=b"ok")

    fetch(make_config(tmp_path, max_retries=3), handler, "https://example.org/a", tmp_path / "a")
    assert len(calls) == 3
    assert (tmp_path / "a").read_bytes() == b"ok"


def test_transport_errors_are_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, content=b"ok")

    fetch(make_config(tmp_path, max_retries=2), handler, "https://example.org/a", tmp_path / "a")
    assert len(calls) == 2


def test_retry_after_is_honoured(tmp_path):
    calls = []

    def handler(request):
        calls.append(time.monotonic())
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, content=b"ok")

    fetch(make_config(tmp_path, max_retries=2), handler, "https://example.org/a", tmp_path / "a")
    assert calls[1] - calls[0] >= 0.95


def test_retry_after_is_capped(tmp_path):
    calls = []

    def handler(request):
        calls.append(time.monotonic())
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": "3600"})
        return httpx.Response(200, content=b"ok")

    fetch(make_config(tmp_path, max_retries=2, retry_after_max=0.2), handler, "https://example.org/a", tmp_path / "a")
    assert 0.15 <= calls[1] - calls[0] < 1.0


def test_parse_retry_after():
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after(" 0 ") == 0.0
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("soon") is None
    in_a_minute = format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
    assert 55 <= parse_retry_after(in_a_minute) <= 60
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0  # in the past


# --- atomic writes ----------------------------------------------------------------------


def test_interrupted_write_leaves_no_file(tmp_path, monkeypatch):
    """If the rename into place fails, neither the target nor a temporary file remains."""

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(client_module.os, "replace", broken_replace)
    with pytest.raises(OSError):
        fetch(make_config(tmp_path), lambda r: httpx.Response(200, content=b"x" * 1000), "https://example.org/a", tmp_path / "a.jp2")
    assert list(tmp_path.iterdir()) == []


def test_completed_write_leaves_only_the_file(tmp_path):
    fetch(make_config(tmp_path), lambda r: httpx.Response(200, content=b"data"), "https://example.org/a", tmp_path / "a.jp2")
    assert [p.name for p in tmp_path.iterdir()] == ["a.jp2"]
    assert (tmp_path / "a.jp2").read_bytes() == b"data"


def test_leftover_temporary_file_does_not_count_as_downloaded(tmp_path, monkeypatch):
    """A .part file from a killed run is ignored; the real file is downloaded."""
    (tmp_path / ".a.jp2.xyz.part").write_bytes(b"trunc")
    use_transport(monkeypatch, lambda r: httpx.Response(200, content=b"full"))
    task = DownloadTask(url="https://example.org/a", save_path=tmp_path / "a.jp2")
    stats = asyncio.run(DownloadManager(make_config(tmp_path), show_progress=False).run([task]))
    assert (stats.successful, stats.skipped) == (1, 0)
    assert (tmp_path / "a.jp2").read_bytes() == b"full"


# --- defaults ---------------------------------------------------------------------------


def test_tls_verification_is_on_by_default(tmp_path):
    assert Config(download_dir=str(tmp_path)).verify_ssl is True
