"""Proxy settings: the environment's, as httpx reads them (NO_PROXY included), an explicit proxy, or none.

A server on loopback answers; the proxy is a closed local port, so a request sent through it fails at once.
"""

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from pybookget.config import Config
from pybookget.http.client import create_client, fetch

DEAD_PROXY = "http://127.0.0.1:9"


@pytest.fixture
def url():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/page.jpg"
    server.shutdown()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def get(url, **kwargs):
    config = Config(max_retries=1, retry_wait_min=0, retry_wait_max=0, timeout=5, **kwargs)

    async def main():
        async with create_client(config) as client:
            return (await fetch(client, url, config)).content

    return asyncio.run(main())


@pytest.mark.parametrize("name", ["HTTP_PROXY", "http_proxy", "ALL_PROXY"])
def test_the_environment_proxy_applies(monkeypatch, url, name):
    monkeypatch.setenv(name, DEAD_PROXY)
    with pytest.raises(httpx.ConnectError):
        get(url)


def test_no_proxy_is_respected(monkeypatch, url):
    monkeypatch.setenv("HTTP_PROXY", DEAD_PROXY)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    assert get(url) == b"ok"


def test_an_https_proxy_leaves_http_urls_alone(monkeypatch, url):
    monkeypatch.setenv("HTTPS_PROXY", DEAD_PROXY)
    assert get(url) == b"ok"


def test_trust_env_false_ignores_the_environment(monkeypatch, url):
    monkeypatch.setenv("HTTP_PROXY", DEAD_PROXY)
    assert Config(trust_env=False).proxy is None
    assert get(url, trust_env=False) == b"ok"


def test_an_explicit_proxy_applies_to_every_request(monkeypatch, url):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with pytest.raises(httpx.ConnectError):
        get(url, proxy=DEAD_PROXY)
