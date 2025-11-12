"""File operation utilities."""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The path object
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_extension(url_or_path: str, default: str = ".jpg") -> str:
    """Extract file extension from URL or path.

    Args:
        url_or_path: URL or file path
        default: Default extension if none found

    Returns:
        File extension including the dot (e.g., '.jpg')
    """
    parsed = urlparse(url_or_path)
    path = Path(parsed.path)

    if path.suffix:
        return path.suffix.lower()

    return default


def generate_filename(
    index: int,
    extension: str = ".jpg",
    width: int = 4,
    prefix: str = "",
) -> str:
    """Generate a formatted filename.

    Args:
        index: File index/number
        extension: File extension
        width: Zero-padding width
        prefix: Optional prefix for filename

    Returns:
        Formatted filename
    """
    number = str(index).zfill(width)
    return f"{prefix}{number}{extension}"
