# pybookget

A Python tool for downloading IIIF-compliant digital books from academic libraries and cultural institutions worldwide.

## Features

- 🖼️ **Universal IIIF Support**: Full support for IIIF Presentation API v2 and v3 - works with any compliant manifest
- 🌍 **Works Everywhere**: Compatible with Library of Congress, Harvard, Princeton, Yale, and any IIIF-compliant library worldwide
- 🎯 **Explicit Handler Selection**: Manually specify which handler to use (defaults to 'iiif')
- 🧠 **Smart Size Negotiation**: Intelligent IIIF size calculation based on image dimensions and orientation
- 🔄 **Automatic Fallback**: Falls back to direct URLs if IIIF parameters aren't supported
- ⚡ **Direct httpx Usage**: No custom wrappers - uses httpx directly for maximum resilience
- 🚀 **HTTP/2 Support**: Modern HTTP/2 protocol for faster downloads
- ⚙️ **Async-Only**: Built with asyncio for efficient I/O-bound operations
- 🔁 **Tenacity Retry Logic**: Configurable exponential backoff retries with tenacity
- 📦 **Library & CLI**: Use as a Python library or command-line tool
- 🔄 **File-Level Resumability**: Automatically skip already downloaded files
- 🎯 **Page Ranges**: Download specific page ranges from books
- 🔐 **Authentication**: Support for cookies and custom headers
- 🔧 **Extensible Architecture**: Easy to add custom site-specific handlers

## Installation

```bash
# Install from source
cd pybookget
pip install -e .

# Or install with pip (once published)
pip install pybookget
```

## Quick Start

### Command Line

```bash
# Download a single book (uses 'iiif' handler by default)
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json"

# Explicitly specify handler
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json" \
    --handler iiif \
    --output ./my-books \
    --pages "1:50" \
    --threads 4

# Download multiple books from a file
pybookget batch urls.txt --handler iiif --concurrent 4

# Interactive mode
pybookget interactive --handler iiif

# List available handlers
pybookget list-handlers
```

### Python Library

```python
import asyncio
from pybookget import download_from_url, Config

# Simple download (uses 'iiif' handler by default)
result = asyncio.run(download_from_url("https://www.loc.gov/item/ltf90007547/manifest.json"))

# With custom configuration and explicit handler
config = Config(
    download_dir="./books",
    page_range="1:100",
    threads_per_task=4,
    max_concurrent_tasks=8,
    iiif_max_size=2000,  # Limit to 2000px for bandwidth savings
    iiif_quality="color",
    iiif_format="jpg",
)

result = asyncio.run(download_from_url(
    "https://www.loc.gov/item/ltf90007547/manifest.json",
    config,
    handler="iiif"
))

print(f"Downloaded {result['downloaded']} pages to {result['save_path']}")
```

### Batch Processing with Async Parallelization

```python
import asyncio
from pybookget import download_from_url, Config

urls = [
    "https://www.loc.gov/item/ltf90007547/manifest.json",
    "https://www.loc.gov/item/ltf90007548/manifest.json",
    "https://www.loc.gov/item/ltf90007549/manifest.json",
]

config = Config(
    download_dir="./books",
    max_concurrent_tasks=4,
)

async def download_all():
    # Create semaphore to limit concurrent downloads
    semaphore = asyncio.Semaphore(4)

    async def download_with_limit(url):
        async with semaphore:
            try:
                result = await download_from_url(url, config, handler="iiif")
                print(f"✓ {url}: {result['downloaded']} pages")
                return result
            except Exception as e:
                print(f"✗ {url}: {e}")
                return None

    # Download all books concurrently
    results = await asyncio.gather(*[download_with_limit(url) for url in urls])
    return results

# Run the async function
results = asyncio.run(download_all())
```

### Direct httpx Usage

For custom implementations, use httpx directly:

```python
import asyncio
import httpx
from pybookget.config import Config
from pybookget.http import create_client, download_file
from pathlib import Path

async def download_custom():
    config = Config()
    client = create_client(config)

    try:
        # Fetch manifest directly with httpx
        response = await client.get("https://www.loc.gov/item/ltf90007547/manifest.json")
        manifest = response.json()

        # Download files concurrently
        tasks = [
            download_file(
                client=client,
                url=image_url,
                dest_path=Path(f"./output/{idx:04d}.jpg"),
                config=config,
            )
            for idx, image_url in enumerate(image_urls)
        ]
        await asyncio.gather(*tasks)
    finally:
        await client.aclose()

asyncio.run(download_custom())
```

## Supported Sites

**pybookget supports any IIIF-compliant digital library worldwide**, including:

### Example Compatible Libraries
- **Library of Congress** - www.loc.gov
- **Harvard University Library** - iiif.lib.harvard.edu
- **Princeton University Library** - catalog.princeton.edu
- **Yale University Library** - collections.library.yale.edu
- **Stanford Libraries** - purl.stanford.edu
- **Bodleian Libraries (Oxford)** - iiif.bodleian.ox.ac.uk
- **National Library of Wales** - damsssl.llgc.org.uk
- **Wellcome Collection** - wellcomelibrary.org
- **Internet Archive** (IIIF manifests) - iiif.archivelab.org
- **And many more...**

If a library provides IIIF Presentation API v2 or v3 manifests, pybookget can download from it.

### Adding Custom Handlers

For libraries with custom APIs or non-IIIF formats, you can easily add custom handlers using the extensible architecture. See the "Extending with Custom Handlers" section below.

## Configuration Options

### CLI Options

```
--output, -o          Output directory (default: ./downloads)
--pages, -p           Page range (e.g., "4:434")
--volume              Volume range for multi-volume books
--threads, -t         Threads per download task (default: 1)
--concurrent, -c      Max concurrent tasks (default: 16)
--timeout             Request timeout in seconds (default: 300)
--cookie-file         Path to cookie file (Netscape format)
--header-file         Path to header file
--proxy               HTTP/HTTPS proxy
--user-agent, -U      Custom user agent
--no-ssl-verify       Disable SSL verification
--quality             JPEG quality 1-100 (default: 80)
--iiif-max-size       IIIF max image dimension in pixels (default: full size)
--iiif-quality        IIIF quality: default, color, gray, bitonal (default: default)
--iiif-format         IIIF format: jpg, png, webp, tif (default: jpg)
--verbose             Enable verbose logging
```

### Config Object

```python
config = Config(
    download_dir="./downloads",       # Output directory
    page_range="1:100",               # Page range
    volume_range="1:5",               # Volume range
    threads_per_task=1,               # Threads per task
    max_concurrent_tasks=16,          # Max concurrent tasks
    timeout=300,                      # Timeout in seconds

    # Retry configuration (tenacity)
    max_retries=3,                    # Maximum retry attempts
    retry_wait_min=1.0,               # Min wait between retries (seconds)
    retry_wait_max=10.0,              # Max wait between retries (seconds)
    retry_multiplier=2.0,             # Exponential backoff multiplier

    # IIIF Image API parameters
    iiif_max_size=2000,               # Max dimension in pixels (None = full size)
    iiif_quality="default",           # Quality: default, color, gray, bitonal
    iiif_format="jpg",                # Format: jpg, png, webp, tif
    iiif_region="full",               # Region parameter (usually 'full')
    iiif_rotation="0",                # Rotation parameter (usually '0')

    cookie_file="cookies.txt",        # Cookie file path
    header_file="headers.txt",        # Header file path
    proxy="http://proxy:8080",        # Proxy URL
    verify_ssl=False,                 # SSL verification
    quality=80,                       # JPEG quality
)
```

## Retry Logic (Tenacity)

pybookget uses [tenacity](https://tenacity.readthedocs.io/) for robust retry management with exponential backoff.

### How It Works

- **Automatic Retries**: Failed downloads are automatically retried
- **Exponential Backoff**: Wait time doubles after each retry (1s, 2s, 4s, 8s...)
- **Configurable**: Adjust max retries, min/max wait times via config
- **Smart**: Only retries on network/HTTP errors, not on other exceptions

### Retry Configuration

```python
config = Config(
    max_retries=5,         # Try up to 5 times
    retry_wait_min=2.0,    # Start with 2 second wait
    retry_wait_max=60.0,   # Cap at 60 seconds
    retry_multiplier=3.0,  # Triple the wait each time (2s, 6s, 18s, 54s)
)
```

### CLI Retry Options

```bash
# Configure retries via CLI
pybookget download URL \
    --max-retries 5 \
    --retry-wait-min 2.0 \
    --retry-wait-max 60.0
```

### What Gets Retried

Retries are triggered for:
- `httpx.HTTPError` - HTTP errors (4xx, 5xx)
- `httpx.TimeoutException` - Request timeouts
- `httpx.NetworkError` - Network connectivity issues

After all retries are exhausted, the file is marked as failed and skipped.

## IIIF Features

pybookget includes advanced IIIF (International Image Interoperability Framework) support with smart size negotiation and fallback mechanisms for maximum compatibility.

### Smart Size Negotiation

The IIIF handler intelligently calculates optimal image sizes based on:
- Your configured maximum dimension (`iiif_max_size`)
- Actual image dimensions from the manifest
- Image orientation (landscape vs portrait)

#### How It Works

1. **No size limit** (`iiif_max_size=None`): Requests full resolution images
2. **Image fits within limit**: Requests full size even if limit is set
3. **Image exceeds limit**: Constrains by the larger dimension
   - Landscape images: constrains width (e.g., `2000,`)
   - Portrait/square images: constrains height (e.g., `,2000`)

#### Example

```python
# Download with 2000px maximum dimension
config = Config(iiif_max_size=2000)
result = asyncio.run(download_from_url(manifest_url, config, handler="iiif"))

# This will:
# - Request full size for images ≤2000x2000px
# - Request 2000px width for landscape images >2000px wide
# - Request 2000px height for portrait images >2000px tall
```

#### CLI Usage

```bash
# Limit images to 2000px on longest side (saves bandwidth)
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json" \
    --iiif-max-size 2000

# Request full resolution (default)
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json"

# Combine with other IIIF parameters
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json" \
    --iiif-max-size 1500 \
    --iiif-quality color \
    --iiif-format png
```

### Fallback URL Mechanism

Some IIIF servers don't fully support the IIIF Image API parameters. pybookget automatically handles this with a fallback mechanism:

1. **Primary attempt**: Tries the optimized IIIF URL with size parameters
2. **Fallback on 404**: If the server returns 404, automatically tries the direct image URL
3. **Logging**: Both attempts are logged for debugging

This ensures compatibility with:
- Fully compliant IIIF servers (use optimized URLs)
- Partially compliant servers (fall back to direct URLs)
- Legacy IIIF implementations

#### Example

```python
# The handler automatically tries both URLs if needed:
# Primary:  {service}/full/2000,/0/default.jpg
# Fallback: {image.id}  (direct image URL)

config = Config(iiif_max_size=2000)
result = asyncio.run(download_from_url(manifest_url, config, handler="iiif"))
# No special configuration needed - fallback is automatic!
```

### IIIF Image API Parameters

Full control over IIIF Image API request parameters:

```python
config = Config(
    iiif_region="full",        # Region: 'full' or 'x,y,w,h'
    iiif_size=None,            # Auto-calculated from iiif_max_size
    iiif_rotation="0",         # Rotation: 0, 90, 180, 270
    iiif_quality="default",    # Quality: default, color, gray, bitonal
    iiif_format="jpg",         # Format: jpg, png, webp, tif
)
```

The IIIF URL format is:
```
{scheme}://{server}{/prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
```

Example generated URLs:
```
# Full size image
https://iiif.example.org/image123/full/full/0/default.jpg

# Constrained to 2000px width (landscape)
https://iiif.example.org/image123/full/2000,/0/default.jpg

# Constrained to 1500px height (portrait), grayscale PNG
https://iiif.example.org/image123/full/,1500/0/gray.png
```

## Authentication

### Cookie Files

Create a `cookies.txt` file in Netscape format:

```
# Netscape HTTP Cookie File
.example.com    TRUE    /    FALSE    1735689600    sessionid    abc123
```

Usage:
```bash
pybookget download "https://..." --cookie-file cookies.txt
```

### Header Files

Create a `headers.txt` file:

```
Authorization: Bearer token123
X-Custom-Header: value
```

Usage:
```bash
pybookget download "https://..." --header-file headers.txt
```

## Extending with Custom Handlers

Add support for new sites by creating custom handlers:

```python
from pybookget.router.base import BaseHandler
from pybookget.router.registry import register_handler

@register_handler("example.com")
class ExampleHandler(BaseHandler):
    """Handler for example.com"""

    async def run(self):
        # Extract book ID
        self.book_id = self.get_book_id()

        # Fetch manifest/API data
        client = self._ensure_client()
        response = await client.get(self.url)
        data = response.json()

        # Extract image URLs
        image_urls = [item['url'] for item in data['images']]

        # Download images
        downloaded = await self.download_images(image_urls)

        return self._create_result(len(image_urls), downloaded)
```

## Architecture

```
pybookget/
├── __init__.py           # Package initialization
├── config.py             # Configuration management
├── cli.py                # Click-based CLI interface
├── models/               # Data models (IIIF, etc.)
│   └── iiif.py
├── http/                 # HTTP utilities (async-only)
│   ├── client.py         # httpx AsyncClient factory
│   ├── download.py       # Async download manager
│   ├── cookies.py        # Cookie file parsing
│   └── headers.py        # Header file parsing
├── utils/                # Utility functions
│   ├── file.py           # File operations
│   └── text.py           # Text parsing
├── router/               # Factory pattern for extensibility
│   ├── base.py           # BaseHandler abstract class
│   └── registry.py       # Handler registry and decorator
└── handlers/             # Handler implementations
    └── iiif.py           # Universal IIIF handler (v2 & v3)
    # Add custom handlers here for non-IIIF sites
```

### Design Principles

- **Async-only**: Built with asyncio for efficient I/O-bound operations
- **Direct httpx usage**: No custom HTTP client wrappers for maximum resilience
- **File-level resumability**: Skip existing files, no partial file downloads
- **No below-file parallelization**: Each file is downloaded atomically
- **Simple and explicit**: Minimal abstractions, easy to understand and debug

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black pybookget/

# Type checking
mypy pybookget/

# Linting
ruff check pybookget/
```

## Migrated from Go

This is a Python rewrite of the original [bookget](https://github.com/deweizhu/bookget) Go project, designed to be:

- **More Pythonic**: Object-oriented design with modern Python practices
- **Async-only**: Built with asyncio for efficient I/O-bound operations
- **Library-first**: Importable as a library, not just a CLI tool
- **Type-hinted**: Better IDE support and code documentation
- **Modular**: Easy to extend with new site handlers
- **Concurrent**: Built-in support for parallel downloads with asyncio

## License

AGPL-3.0 License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to:

1. **Add custom site handlers** for libraries with non-IIIF APIs
2. Improve the IIIF handler
3. Report bugs or request features
4. Improve documentation
5. Add tests

### Adding a Custom Handler

1. Create `handlers/mysite.py`:
```python
from pybookget.router.base import BaseHandler
from pybookget.router.registry import register_handler

@register_handler("mysite")  # Register by name, not domain
class MySiteHandler(BaseHandler):
    async def run(self):
        # Your custom implementation here
        # Extract book ID, fetch data, download images
        pass
```

2. Import in `handlers/__init__.py`:
```python
from pybookget.handlers import iiif, mysite
```

3. Import in `router/registry.py` in `_initialize_handlers()`:
```python
from pybookget.handlers import (iiif, mysite)
```

4. Use with CLI or library:
```bash
pybookget download URL --handler mysite
```

```python
result = asyncio.run(download_from_url(url, config, handler="mysite"))
```

## Credits

- Original Go implementation: [bookget](https://github.com/deweizhu/bookget) by deweizhu
- Python rewrite: Sebastian Majstorovic (storytracer@gmail.com)
