"""
pybookget - A Python tool for downloading digital books from academic libraries.

This package provides functionality to download high-resolution images from 50+
digital libraries and cultural institutions worldwide, with support for IIIF,
DZI, and custom institutional APIs.
"""

__version__ = "1.0.0"
__author__ = "Sebastian Majstorovic"
__email__ = "storytracer@gmail.com"
__license__ = "AGPL-3.0"

from pybookget.config import Config
from pybookget.router.registry import download_from_url

__all__ = ["Config", "download_from_url", "__version__"]
