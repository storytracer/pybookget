"""Cookie file parsing utilities.

Supports Netscape cookie file format used by browsers and tools like curl.
"""

from http.cookiejar import Cookie
from pathlib import Path
from typing import List


def load_cookies_from_file(cookie_file: str) -> List[Cookie]:
    """Load cookies from Netscape cookie file format.

    The Netscape cookie format is:
    # domain flag path secure expiration name value

    Args:
        cookie_file: Path to cookie file

    Returns:
        List of Cookie objects

    Example file format:
        # Netscape HTTP Cookie File
        .example.com    TRUE    /    FALSE    1735689600    sessionid    abc123
    """
    cookies = []
    cookie_path = Path(cookie_file)

    if not cookie_path.exists():
        return cookies

    with open(cookie_path, 'r') as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse cookie line
            parts = line.split('\t')
            if len(parts) < 7:
                continue

            domain, flag, path, secure, expiration, name, value = parts[:7]

            # Convert string values to appropriate types
            domain_specified = flag.upper() == 'TRUE'
            secure_flag = secure.upper() == 'TRUE'

            try:
                expires = int(expiration)
            except ValueError:
                expires = None

            # Create cookie object
            cookie = Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=domain_specified,
                domain_initial_dot=domain.startswith('.'),
                path=path,
                path_specified=True,
                secure=secure_flag,
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
            cookies.append(cookie)

    return cookies
