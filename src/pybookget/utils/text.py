"""Text and URL parsing utilities."""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import url64


def extract_between(text: str, start: str, end: str) -> Optional[str]:
    """Extract text between two markers.

    Args:
        text: Text to search in
        start: Starting marker
        end: Ending marker

    Returns:
        Extracted text or None if not found
    """
    try:
        start_idx = text.index(start) + len(start)
        end_idx = text.index(end, start_idx)
        return text[start_idx:end_idx]
    except ValueError:
        return None


def get_domain(url: str) -> str:
    """Extract domain from URL.

    Args:
        url: URL to parse

    Returns:
        Domain name (e.g., 'example.com')
    """
    parsed = urlparse(url)
    return parsed.netloc


def get_host_url(url: str) -> str:
    """Extract scheme and host from URL.

    Args:
        url: URL to parse

    Returns:
        Base URL with scheme and host (e.g., 'https://example.com')
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def parse_url_pattern(pattern: str) -> Tuple[str, Optional[str]]:
    """Parse URL pattern with placeholders like [PAGE], [VOL], etc.

    Args:
        pattern: URL pattern string

    Returns:
        Tuple of (base_pattern, placeholder) where placeholder is 'PAGE', 'VOL', etc.
    """
    placeholders = ['PAGE', 'VOL', 'AB', 'NUM']

    for placeholder in placeholders:
        if f'[{placeholder}]' in pattern:
            return (pattern, placeholder)

    return (pattern, None)


def format_url_pattern(
    pattern: str,
    value: int,
    placeholder: str = 'PAGE',
    width: int = 4,
) -> str:
    """Format URL pattern with specific value.

    Args:
        pattern: URL pattern with placeholder
        value: Value to insert
        placeholder: Placeholder name ('PAGE', 'VOL', etc.)
        width: Zero-padding width

    Returns:
        Formatted URL
    """
    formatted_value = str(value).zfill(width)
    return pattern.replace(f'[{placeholder}]', formatted_value)


def extract_id_from_url(url: str, pattern: Optional[str] = None) -> Optional[str]:
    """Extract ID from URL using regex pattern.

    Args:
        url: URL to parse
        pattern: Regex pattern to use (default extracts last path segment)

    Returns:
        Extracted ID or None
    """
    if pattern:
        match = re.search(pattern, url)
        return match.group(1) if match else None

    # Default: extract last path segment
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    return path_parts[-1] if path_parts else None


def parse_range_string(range_str: str) -> Tuple[int, int]:
    """Parse range string like '1-100' or '4:434'.

    Args:
        range_str: Range string

    Returns:
        Tuple of (start, end)

    Raises:
        ValueError: If format is invalid
    """
    # Support both '-' and ':' as separators
    separator = ':' if ':' in range_str else '-'
    parts = range_str.split(separator)

    if len(parts) != 2:
        raise ValueError(f"Invalid range format: {range_str}")

    try:
        start = int(parts[0])
        end = int(parts[1])
        return (start, end)
    except ValueError:
        raise ValueError(f"Invalid range values: {range_str}")


def url_to_slug(url: str) -> str:
    """Convert URL to a reversible, filesystem-safe slug.

    Uses url64 library for URL-safe base64 encoding.

    Args:
        url: URL to convert (UTF-8)

    Returns:
        Base64url-encoded slug (no padding)

    Raises:
        ValueError: If URL cannot be encoded

    Examples:
        >>> url_to_slug("https://example.org/manifest.json")
        'aHR0cHM6Ly9leGFtcGxlLm9yZy9tYW5pZmVzdC5qc29u'
    """
    try:
        return url64.encode(url)
    except Exception as e:
        raise ValueError(f"Failed to encode URL to slug: {e}")


def slug_to_url(slug: str) -> str:
    """Decode a base64url slug back to the original URL.

    Uses url64 library for URL-safe base64 decoding.

    Args:
        slug: Base64url-encoded slug

    Returns:
        Original URL (UTF-8)

    Raises:
        ValueError: If slug cannot be decoded

    Examples:
        >>> slug_to_url('aHR0cHM6Ly9leGFtcGxlLm9yZy9tYW5pZmVzdC5qc29u')
        'https://example.org/manifest.json'
    """
    try:
        return url64.decode(slug)
    except Exception as e:
        raise ValueError(f"Failed to decode slug to URL: {e}")
