"""HTTP client infrastructure for pybookget (async-only).

Uses httpx directly for maximum resilience and simplicity.
"""

from pybookget.http.client import (
    create_client,  # Returns AsyncClient
    download_file,  # Async function
)
from pybookget.http.cookies import load_cookies_from_file
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.http.headers import load_headers_from_file

__all__ = [
    "DownloadManager",
    "DownloadTask",
    "create_client",
    "download_file",
    "load_cookies_from_file",
    "load_headers_from_file",
]
