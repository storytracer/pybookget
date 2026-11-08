"""Tests for the deadline per attempt (Config.attempt_timeout, attempt_min_rate): an attempt that trickles is
cancelled and retried; the deadline starts after the rate limits; Content-Length extends it at attempt_min_rate."""

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from pybookget.config import Config
from pybookget.http.client import attempt_deadline, create_client, fetch


def make_config(**kwargs) -> Config:
    kwargs.setdefault("trust_env", False)  # ignore the test environment's proxy settings
    kwargs.setdefault("retry_wait_min", 0)
    kwargs.setdefault("retry_wait_max", 0)
    return Config(show_progress=False, **kwargs)


def trickling_transport(calls: list, slow_attempts: int = 1, chunks: int = 20, pause: float = 0.1):
    """The first ``slow_attempts`` attempts send their body in ``chunks`` pieces ``pause`` seconds apart; later
    attempts send it at once."""

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(time.monotonic())
        if len(calls) <= slow_attempts:
            async def body():
                for _ in range(chunks):
                    await asyncio.sleep(pause)
                    yield b"x"
            return httpx.Response(200, content=body())
        return httpx.Response(200, content=b"x" * chunks)

    return httpx.MockTransport(handler)


def run(coro):
    return asyncio.run(coro)


def test_a_trickling_attempt_is_cut_at_its_deadline_and_retried():
    calls = []

    async def go():
        config = make_config(attempt_timeout=0.3)
        async with create_client(config, transport=trickling_transport(calls)) as c:
            t = time.monotonic()
            response = await fetch(c, "https://example.org/a.jp2", config)
            return response, time.monotonic() - t

    response, elapsed = run(go())
    assert response.content == b"x" * 20 and len(calls) == 2
    assert elapsed < 1.5                       # cut after 0.3 s, not the 2 s the trickle takes


def test_without_attempt_timeout_a_trickle_is_waited_for():
    calls = []

    async def go():
        config = make_config()
        async with create_client(config, transport=trickling_transport(calls, chunks=5)) as c:
            return await fetch(c, "https://example.org/a.jp2", config)

    assert run(go()).content == b"xxxxx" and len(calls) == 1


def test_attempts_that_always_trickle_fail_after_the_retries():
    calls = []

    async def go():
        config = make_config(attempt_timeout=0.2, max_retries=2)
        async with create_client(config, transport=trickling_transport(calls, slow_attempts=99)) as c:
            await fetch(c, "https://example.org/a.jp2", config)

    with pytest.raises(httpx.ReadTimeout, match="deadline"):
        run(go())
    assert len(calls) == 3                                   # the first attempt and two retries


def test_no_retries_is_a_single_attempt():
    calls = []

    async def go():
        config = make_config(attempt_timeout=0.2, max_retries=0)
        async with create_client(config, transport=trickling_transport(calls, slow_attempts=99)) as c:
            await fetch(c, "https://example.org/a.jp2", config)

    with pytest.raises(httpx.ReadTimeout, match="deadline"):
        run(go())
    assert len(calls) == 1


def test_the_deadline_starts_after_the_rate_limits():
    """Two requests per second: the fourth waits over a second for the limiter, but each attempt is quick."""
    calls = []

    async def go():
        config = make_config(attempt_timeout=0.3, rate_limits=[(2, 1)])
        async with create_client(config, transport=trickling_transport(calls, slow_attempts=0)) as c:
            return await asyncio.gather(*(fetch(c, f"https://example.org/{i}.jp2", config) for i in range(4)))

    responses = run(go())
    assert [r.status_code for r in responses] == [200] * 4 and len(calls) == 4      # no attempt was cut


def test_content_length_extends_the_deadline_at_the_minimum_rate():
    config = make_config(attempt_timeout=30, attempt_min_rate=50_000)
    assert attempt_deadline(config, "300000") == pytest.approx(36.0)
    assert attempt_deadline(config, None) == 30.0
    assert attempt_deadline(make_config(attempt_timeout=30), "300000") == 30.0


@pytest.fixture
def slow_headers_server():
    """Sends its headers after ``state["delay"]`` seconds on the first request, at once afterwards."""
    state = {"delay": 2.0, "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"] += 1
            if state["requests"] == 1:
                time.sleep(state["delay"])
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}/a.jp2"
    yield state
    server.shutdown()


def test_an_attempt_waiting_for_its_headers_is_cut_too(slow_headers_server):
    async def go():
        config = make_config(attempt_timeout=0.5)
        async with create_client(config) as c:
            t = time.monotonic()
            response = await fetch(c, slow_headers_server["url"], config)
            return response, time.monotonic() - t

    response, elapsed = run(go())
    assert response.content == b"ok" and slow_headers_server["requests"] == 2
    assert elapsed < 1.8
