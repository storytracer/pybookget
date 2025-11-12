"""Header file parsing utilities.

Supports simple key-value header file format.
"""

from pathlib import Path
from typing import Dict


def load_headers_from_file(header_file: str) -> Dict[str, str]:
    """Load HTTP headers from file.

    File format is simple key: value pairs, one per line.

    Args:
        header_file: Path to header file

    Returns:
        Dictionary of header name to value

    Example file format:
        Accept: application/json
        Authorization: Bearer token123
        X-Custom-Header: value
    """
    headers = {}
    header_path = Path(header_file)

    if not header_path.exists():
        return headers

    with open(header_path, 'r') as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse header line
            if ':' in line:
                name, value = line.split(':', 1)
                headers[name.strip()] = value.strip()

    return headers
