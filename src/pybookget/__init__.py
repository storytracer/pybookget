"""
pybookget - A Python tool for downloading digital books from academic libraries.

This package provides functionality to download high-resolution images from
IIIF-compliant digital libraries and cultural institutions worldwide, and from
custom institutional APIs.
"""

__version__ = "1.1.0"
__author__ = "Sebastian Majstorovic"
__email__ = "storytracer@gmail.com"
__license__ = "MIT"

from pybookget.config import Config

__all__ = ["Config", "__version__", "download_from_url"]


def __getattr__(name):
    # The handlers need the [cli] extra; import them only when asked for, so the IIIF
    # parser and the HTTP layer work with the core dependencies alone
    if name == "download_from_url":
        from pybookget.router.registry import download_from_url

        return download_from_url
    raise AttributeError(f"module 'pybookget' has no attribute {name!r}")
