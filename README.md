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

Requires Python 3.12 or newer. The project is managed with [uv](https://docs.astral.sh/uv/).

```bash
# Install from source (creates .venv from uv.lock)
cd pybookget
uv sync

# Run the CLI from the project environment
uv run pybookget --help

# Or install with pip (once published): the CLI and the book handlers need the [cli] extra
pip install "pybookget[cli]"

# The library core alone (IIIF parsing and the HTTP layer, no CLI)
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
    iiif_quality="color",  # Always downloads full resolution images
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

### Page Images of a Manifest

`canvas_images()` turns a parsed manifest into the full-size URL of each page
image (with its fallback), and `fetch()` gets one with pybookget's retries, rate
limits and fallback on 404, returning the response instead of writing a file.
Both need only the core install.

```python
import asyncio
from pybookget.config import Config
from pybookget.formats.iiif import canvas_images, parse_iiif_manifest
from pybookget.http import create_client, fetch

async def first_page(manifest_url):
    config = Config(rate_limits=[(5, 1)], max_keepalive_connections=8)
    async with create_client(config) as client:
        manifest = parse_iiif_manifest((await fetch(client, manifest_url, config)).json())
        page = canvas_images(manifest, config)[0]  # page.index, page.canvas, page.url, page.fallback_url
        response = await fetch(client, page.url, config, fallback_url=page.fallback_url)
        return response.content, str(response.url)

asyncio.run(first_page("https://www.loc.gov/item/ltf90007547/manifest.json"))
```

Manifests also carry `rights` (v2 `license`, v3 `rights`) and
`required_statement` (v2 `attribution`, v3 `requiredStatement`), and
`pybookget.models.iiif.label_text()` reads any IIIF label shape.

### Manifests (IIIF and METS)

`pybookget.formats.manifest` reads an item's pages from a IIIF Presentation manifest (v2 or v3)
or a METS document with MODS (plain, or in an OAI-PMH `GetRecord` response), with the core
install only. `read_manifest()` detects the format (`detect_format()`, or pass `format="iiif"` /
`"mets"`) and returns a `ManifestItem`: `format`, `id`, `label`, `rights`,
`required_statement`, `identifiers`, `metadata` and `pages`, a `ManifestPage` per page with an
image (`index`, `id`, `label`, `url`, `fallback_url`, `ocr_url`, `ocr_format`).

```python
import asyncio
from pybookget.config import Config
from pybookget.formats.manifest import read_manifest
from pybookget.http import create_client, fetch

async def pages(url):
    config = Config()
    async with create_client(config) as client:
        item = read_manifest((await fetch(client, url, config)).content, config)
        print(item.format, item.id, item.label, item.rights)
        for page in item.pages:  # existing OCR: page.ocr_url, page.ocr_format ("alto"/"hocr")
            print(page.index, page.label, page.url, page.fallback_url, page.ocr_url)

asyncio.run(pages("https://library.example.org/oai?verb=GetRecord&metadataPrefix=mets&identifier=oai:example:1234"))
```

- **IIIF**: the pages and URLs of `canvas_images()`; OCR from a canvas's `seeAlso` or
  `rendering` whose `format` or `profile` names ALTO or hOCR (ALTO preferred); `metadata` holds
  the manifest's metadata pairs.
- **METS**: the `TYPE="page"` divs of the physical structMap, by `ORDER`; the image is the
  page's file in the first of `Config.mets_image_groups` (`MAX`, `ORIGINAL`, `MASTER`,
  `DEFAULT`) that has one, then any other group of `image/*` files except thumbnails, and the
  fallback its file in the next group; OCR from the `FULLTEXT`, `ALTO` or `OCR` group
  (`Config.mets_ocr_groups`). Title, names, dates, identifiers and rights come from the MODS
  record the logical structMap points to; hrefs are kept as given.

### IIIF Collections

`read_collection()` lists one level of a IIIF Collection (v2 or v3) as `CollectionEntry`s
(`id`, `label`, `kind`: `"manifest"` or `"collection"`); `detect_format()` returns
`"iiif-collection"` for one. A listed collection is read by reading its id in turn. Paged
collections (`first`/`next`) and collections that embed a nested collection's members are not
read yet (`NotImplementedError`).

```python
from pybookget.formats.manifest import read_collection

for entry in read_collection(collection_json):
    print(entry.kind, entry.id, entry.label)
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
--proxy               HTTP/HTTPS proxy for every request (default: the environment's, see Proxies)
--user-agent, -U      Custom user agent
--no-ssl-verify       Disable SSL verification
--quality             JPEG quality 1-100 (default: 80)
--iiif-quality        IIIF quality: default, color, gray, bitonal (default: default)
--iiif-format         IIIF format: jpg, png, webp, tif (default: jpg)
--rate-limit          Limit requests as REQUESTS/SECONDS, e.g. 10/1 (repeatable)
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
    max_retries=3,                    # Retries after the first attempt (4 attempts)
    retry_wait_min=1.0,               # Min wait between retries (seconds)
    retry_wait_max=10.0,              # Max wait between retries (seconds)
    retry_multiplier=2.0,             # Exponential backoff multiplier

    # IIIF Image API parameters (always requests full resolution)
    iiif_quality="default",           # Quality: default, color, gray, bitonal
    iiif_format="jpg",                # Format: jpg, png, webp, tif
    iiif_region="full",               # Region parameter (usually 'full')
    iiif_rotation="0",                # Rotation parameter (usually '0')

    cookie_file="cookies.txt",        # Cookie file path
    header_file="headers.txt",        # Header file path
    proxy="http://proxy:8080",        # Proxy for every request (default None: the environment's)
    trust_env=True,                   # Read proxy settings from the environment (default True)
    verify_ssl=True,                  # TLS certificate verification (default True)
    max_keepalive_connections=0,      # 0 = a new connection per request; keep some for bulk runs
    quality=80,                       # JPEG quality

    # Rate limiting (pyrate-limiter): (requests, seconds) windows, all applied at once
    rate_limits=[(10, 1), (80, 10), (400, 60)],
)
```

## Rate Limiting

`rate_limits` caps the request rate of everything that shares one `Config`: all
HTTP clients pybookget creates from it, all concurrent downloads, manifest
requests, retries and fallback URLs. Each window is `(requests, seconds)`, and
all windows apply at once, so `[(10, 1), (80, 10), (400, 60)]` allows at most 10
requests per second, 80 per 10 seconds and 400 per minute. Requests that would
exceed a window wait (asynchronously) until a slot is free.

```bash
pybookget download "URL" --rate-limit 10/1 --rate-limit 80/10 --rate-limit 400/60
```

The limit is enforced with [pyrate-limiter](https://github.com/vutran1710/PyrateLimiter)
through an httpx request hook, so it also applies when requests go through a
proxy. Windows that contradict each other (e.g. a longer window allowing fewer
requests than a shorter one) are rejected when the `Config` is created. The
default is no limit.

## Retry Logic (Tenacity)

pybookget uses [tenacity](https://tenacity.readthedocs.io/) for robust retry management with exponential backoff.

### How It Works

- **Automatic Retries**: Failed downloads are automatically retried
- **Exponential Backoff**: Wait time doubles after each retry (1s, 2s, 4s, 8s...)
- **Configurable**: Adjust max retries, min/max wait times via config
- **Smart**: Only retries errors that can go away (see below); a 404 fails at once
- **Polite**: Honours the server's `Retry-After` header on 429/503 (up to `retry_after_max`, default 300 s)
- **Deadline per attempt** (optional): `attempt_timeout` cuts an attempt that takes longer than that
  (counted from when it is sent, after the rate limits) and retries it, so a connection that trickles
  does not hold a download for minutes; `attempt_min_rate` (bytes per second) adds time for large
  files by their Content-Length. `timeout` alone applies to each phase (connect, read, ...) and a
  trickle never reaches it.

### Retry Configuration

```python
config = Config(
    max_retries=5,         # Retry up to 5 times (6 attempts)
    retry_wait_min=2.0,    # Start with 2 second wait
    retry_wait_max=60.0,   # Cap at 60 seconds
    retry_multiplier=3.0,  # Triple the wait each time (2s, 6s, 18s, 54s)
    attempt_timeout=30,    # One attempt may take 30 s ...
    attempt_min_rate=50_000,  # ... plus 1 s per 50 KB of Content-Length
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
- HTTP 408, 425, 429, 500, 502, 503 and 504 (busy, overloaded or briefly failing servers), and Cloudflare's 520-524
  (the site behind Cloudflare sent an unusable answer, refused the connection or timed out)
- `httpx.TransportError` - timeouts, connection and proxy errors, broken connections

Other HTTP errors (404, 403, 410, ...) are final and are not retried; a 404 still
tries the task's `fallback_url` if it has one. The wait before a retry is the
exponential backoff, or the server's `Retry-After` if that is longer.

After all retries are exhausted, the file is marked as failed (`task.error` says
why) and skipped.

## Bulk Downloads

`DownloadManager.run()` streams tasks from any iterable or async iterable (for
example a generator over a page list) with `max_workers` concurrent downloads.
Only a small bounded queue of tasks is held in memory, so millions of files are
fine. The callback gets each task with its own result.

```python
from pybookget.http.download import DownloadManager, DownloadTask

def tasks():
    for line in open("pages.tsv"):
        url, path = line.rstrip("\n").split("\t")
        yield DownloadTask(url=url, save_path=path)

def log_failure(task, success):
    if not success:
        print(task.url, task.error)

config = Config(rate_limits=[(10, 1)], proxy="http://proxy:8080")
dm = DownloadManager(config, max_workers=8)
stats = await dm.run(tasks(), callback=log_failure)
print(stats.successful, stats.skipped, stats.failed)
```

Files are written atomically: each download goes to a hidden temporary file in
the target directory and is renamed into place once complete, so an interrupted
run never leaves a truncated file that the next run would skip as done.

## IIIF Features

pybookget includes advanced IIIF (International Image Interoperability Framework) support with automatic Image API version detection and fallback mechanisms for maximum compatibility.

### Full Resolution Downloads

The IIIF handler always requests full resolution images using the correct size parameter for each IIIF Image API version:

- **IIIF Image API v3**: Uses `"max"` (canonical full-size parameter)
- **IIIF Image API v2**: Uses `"full"` (canonical full-size parameter)
- **Version detection**: Automatic based on service metadata in the manifest

#### Example

```python
# Downloads full resolution images
config = Config(
    iiif_quality="color",
    iiif_format="jpg",
)
result = asyncio.run(download_from_url(manifest_url, config, handler="iiif"))
```

#### CLI Usage

```bash
# Download full resolution images (always)
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json"

# Combine with other IIIF parameters
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json" \
    --iiif-quality color \
    --iiif-format png
```

### Fallback URL Mechanism

Some IIIF servers don't fully support the IIIF Image API parameters. pybookget automatically handles this with a fallback mechanism:

1. **Primary attempt**: Tries the IIIF URL with full-size parameters (`max` or `full`)
2. **Fallback on 404**: If the server returns 404, automatically tries the direct image URL
3. **Logging**: Both attempts are logged for debugging

This ensures compatibility with:
- Fully compliant IIIF servers (use IIIF Image API URLs)
- Partially compliant servers (fall back to direct URLs)
- Legacy IIIF implementations

#### Example

```python
# The handler automatically tries both URLs if needed:
# Primary:  {service}/full/max/0/default.jpg  (v3)
# Fallback: {image.id}  (direct image URL from manifest)

result = asyncio.run(download_from_url(manifest_url, config, handler="iiif"))
# No special configuration needed - fallback is automatic!
```

### IIIF Image API Parameters

Full control over IIIF Image API request parameters:

```python
config = Config(
    iiif_region="full",        # Region: 'full' or 'x,y,w,h'
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
# Full size image (v2)
https://iiif.example.org/image123/full/full/0/default.jpg

# Full size image (v3)
https://iiif.example.org/image123/full/max/0/default.jpg

# Full size, grayscale PNG (v3)
https://iiif.example.org/image123/full/max/0/gray.png
```

## Proxies

By default the environment's proxy settings apply, as httpx reads them:
`HTTPS_PROXY`, `HTTP_PROXY` and `ALL_PROXY` (upper or lower case), with
`NO_PROXY` naming the hosts that are reached directly. An HTTPS proxy is used
for `https://` URLs only. `proxy=` (`--proxy`) sends every request through one
proxy instead; `trust_env=False` ignores the environment (no proxy, no
`SSL_CERT_FILE`, no `.netrc`).

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
# Install the project and its development dependencies (dev group)
uv sync

# Run tests
uv run pytest

# Format code
uv run black src/pybookget/

# Type checking
uv run mypy src/pybookget/

# Linting
uv run ruff check src/pybookget/
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

MIT License - see LICENSE file for details.

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
