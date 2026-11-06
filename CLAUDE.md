# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pybookget** is a Python tool for downloading IIIF-compliant digital books from academic libraries and cultural institutions worldwide. This is a complete Python rewrite of the original [bookget](https://github.com/deweizhu/bookget) Go project.

**Key Design Philosophy:**
- **Async-only**: Built with asyncio for efficient I/O-bound operations
- **Direct httpx usage**: No custom HTTP client wrappers for maximum resilience
- **IIIF-focused**: Universal IIIF handler with smart features, extensible for custom sites
- **Library-first**: Importable as a library, not just a CLI tool
- **Explicit over implicit**: Manual handler selection via `--handler` flag (defaults to 'iiif')
- **File-level resumability**: Skip existing files, no partial file downloads
- **Simple and explicit**: Minimal abstractions, easy to understand and debug

## Installation

Python 3.12+ (`requires-python = ">=3.12"`, pinned in `.python-version`), managed with uv
(`[tool.uv] required-version = ">=0.13.6"`, build backend `uv_build`). Dependencies are locked in
`uv.lock`; there is no requirements.txt.

```bash
# Create .venv with the project and the dev dependency group
cd pybookget
uv sync

# Add a dependency (updates pyproject.toml and uv.lock)
uv add <package>
```

The core dependencies (httpx, h2, tenacity, pyrate-limiter, tqdm, fake-useragent) cover the IIIF
and METS parsers (`formats/iiif.py`, `formats/mets.py`, `models/iiif.py`, `models/mets.py`), the
manifest API (`formats/manifest.py`) and the HTTP layer (`http/`), which other projects
(linecaster) use as a library. The CLI and the handlers need the `[cli]` extra (click, url64,
tldextract, rocrate); `pybookget.download_from_url` is imported lazily so `import pybookget` works
without it. The dev group installs `pybookget[cli]`. Keep handler-only dependencies out of the core.

## Development Commands

```bash
# Run CLI during development
python -m pybookget.cli download "https://www.loc.gov/item/ltf90007547/manifest.json"

# Or if installed
pybookget download "https://www.loc.gov/item/ltf90007547/manifest.json"

# Run with options
pybookget download "URL" \
    --handler iiif \
    --output ./books \
    --pages "1:50"

# List available handlers
pybookget list-handlers

# Interactive mode
pybookget interactive --handler iiif

# Batch download from file
pybookget batch urls.txt --concurrent 4

# Enable verbose logging
pybookget download "URL" --verbose
```

## Testing

```bash
# Run tests (tests/, no network: httpx.MockTransport fakes the servers)
uv run pytest

# With coverage
uv run pytest --cov=pybookget

# Type checking
uv run mypy src/pybookget/

# Linting
uv run ruff check src/pybookget/

# Code formatting
uv run black src/pybookget/
```

## Architecture

### Project Structure

```
pybookget/                 # Git repository root
├── README.md              # Comprehensive documentation
├── CLAUDE.md              # This file
├── LICENSE                # MIT
├── pyproject.toml         # Package configuration (uv_build, dependency groups)
├── uv.lock                # Locked dependencies (uv)
├── .python-version        # 3.12
├── tests/                 # pytest suite (test_ratelimit.py, test_download.py, test_iiif.py, test_manifest.py, test_proxy.py)
└── src/                   # Source code (src layout)
    └── pybookget/         # Python package
        ├── __init__.py        # Package exports
        ├── __main__.py        # Entry point for python -m pybookget
        ├── config.py          # Configuration management (Config class)
        ├── cli.py             # Click-based CLI interface
        ├── formats/           # Format parsers
        │   ├── iiif.py        # IIIF parser, canvas_images(), image_url()
        │   ├── mets.py        # METS/MODS parser (METSParser)
        │   └── manifest.py    # read_manifest(): IIIF or METS as ManifestItem/ManifestPage; read_collection()
        ├── models/            # Data models
        │   ├── iiif.py        # IIIF manifest parsing (v2 & v3)
        │   └── mets.py        # METS document, pages, files, MODS metadata
        ├── http/              # HTTP utilities (async-only)
        │   ├── client.py      # httpx AsyncClient factory
        │   ├── download.py    # Async download manager with fallback support
        │   ├── ratelimit.py   # pyrate-limiter limits shared per Config and event loop
        │   ├── cookies.py     # Cookie file parsing (Netscape format)
        │   └── headers.py     # Header file parsing
        ├── utils/             # Utility functions
        │   ├── file.py        # File operations
        │   └── text.py        # Text parsing
        ├── router/            # Handler registry pattern
        │   ├── base.py        # BaseHandler abstract class
        │   └── registry.py    # Handler registry, decorator, download_from_url()
        └── handlers/          # Handler implementations
            └── iiif.py        # Universal IIIF handler (v2 & v3)
```

### Core Components

#### 1. **Config** (`src/pybookget/config.py`)
Central configuration class with:
- Download paths and output settings
- Page/volume range filtering
- Concurrency settings (threads, concurrent tasks)
- HTTP settings (timeout, user agent, proxy, SSL)
- **IIIF Image API parameters** (quality, format, region, rotation)
- **METS file groups**: `mets_image_groups` (image priority, default `MAX`, `ORIGINAL`,
  `MASTER`, `DEFAULT`) and `mets_ocr_groups` (`FULLTEXT`, `ALTO`, `OCR`)
- Retry configuration (tenacity integration)
- Rate limiting

#### 2. **CLI** (`src/pybookget/cli.py`)
Click-based command-line interface with commands:
- `download` - Download single book
- `batch` - Download multiple books from file
- `interactive` - Interactive mode
- `list-handlers` - List available handlers
- `info` - Show handler information

#### 3. **Handler System** (`src/pybookget/router/`, `src/pybookget/handlers/`)
- **BaseHandler**: Abstract base class for all handlers
- **Handler Registry**: Decorator-based registration (`@register_handler("name")`)
- **Explicit Selection**: Users specify handler via `--handler iiif` (default)
- **No Auto-Matching**: URLs are NOT automatically routed by domain patterns

#### 4. **IIIF Handler** (`src/pybookget/handlers/iiif.py`)
Universal IIIF Presentation API v2/v3 handler with advanced features:

The URL logic is public, in `formats/iiif.py`, so it can be used without a handler:
- `image_api_version(service)`: IIIF Image API version (2 or 3; 2 when unknown)
- `full_size_parameter(service)`: `"max"` for v3, `"full"` for v2 (always full resolution)
- `image_url(image, config)`: (primary, fallback) — the Image API request built from the
  `iiif_*` config, and the image's own URL (used if the request returns 404); without a service
  the image's own URL only
- `canvas_images(manifest, config)`: a `CanvasImage(index, canvas, image, url, fallback_url)` per
  canvas with an image; `index` counts from 1 as the handlers number their files

**Key Methods:**
- `run()`: Main execution flow
- `_extract_title()`: Handles v2/v3 label formats
- `_extract_image_urls()`: (primary, fallback) pairs for canvases (via `image_url`; e-rara uses it)
- `_download_images_with_fallback()`: Downloads with fallback support

#### 5. **HTTP Layer** (`src/pybookget/http/`)

**Direct httpx Usage:**
- `create_client()`: Factory for httpx.AsyncClient with config
- No custom HTTP wrappers - uses httpx directly
- HTTP/2 support enabled by default

**Download Manager** (`download.py`):
- `DownloadTask`: Task definition with primary + fallback URLs
- `DownloadManager`: Async concurrent download manager
  - File-level resumability (skip existing files)
  - Streaming `run(tasks)`: any iterable/async iterable, `max_workers` workers on a bounded
    queue (2 × workers), constant memory for millions of files; `execute()` runs the
    `add_tasks()` queue through it. Returns `DownloadStats` (successful, failed, skipped)
  - Callback `(task, success)` always gets the task the result belongs to; failures set
    `task.error`; a failing callback or task never stops a worker
  - Atomic writes (`client.write_atomically`): hidden `.<name>.<random>.part` file, then
    `os.replace`, in a thread (`asyncio.to_thread`) so disk I/O doesn't stall the loop; no fsync
  - Progress tracking with tqdm
  - **Fallback retry on 404**: Tries fallback_url if primary fails with 404
  - Tenacity retry logic for network errors

**`client.fetch(client, url, config, headers=None, fallback_url=None)`**: GET with the retry
policy below, returning the read `httpx.Response` (`response.url` says where the content came
from); on 404 it fetches `fallback_url` instead. `download_file` uses it. Connections are not kept
alive by default (`Config.max_keepalive_connections = 0`); bulk callers set it higher. `Config`
creates no folders; handlers create theirs in `get_save_dir()`.

**Retry Logic:**
- Uses tenacity library for exponential backoff
- Configurable max retries, wait times, multiplier
- `client.is_retryable`: retries `httpx.TransportError` and statuses 408/425/429/500/502/503/504
  only; other 4xx (404, 403, ...) fail at once
- `client.wait_retry_after_or_exponential`: waits the backoff or the server's `Retry-After`
  (seconds or HTTP-date), whichever is longer, capped at `Config.retry_after_max` (300 s)

#### 6. **Manifests** (`src/pybookget/formats/manifest.py`)
The format-independent API linecaster uses (core install only):
- `detect_format(data)`: `"iiif"` (JSON/dict with a IIIF Presentation context, type Manifest
  or sequences), `"iiif-collection"` (type Collection / sc:Collection) or `"mets"` (XML with a
  mets:mets root, or an OAI-PMH response with exactly one METS record); `ValueError` otherwise
- `read_collection(data)`: one level of a IIIF Collection (v2 or v3) as `CollectionEntry(id,
  label, kind)`, kind `"manifest"` or `"collection"` (a listed collection, read in turn by the
  caller), in order: v3 `items`; v2 `members`, else `collections` then `manifests` (bare URIs
  too). A skeleton: paged collections (`first`/`next`) and collections embedding a nested
  collection's members raise `NotImplementedError` (xfail tests); `read_manifest` refuses a
  collection with a `ValueError` naming `read_collection`
- `read_manifest(data, config, format=None)`: a `ManifestItem(format, id, label, rights,
  required_statement, identifiers, metadata, pages)`; `pages` are `ManifestPage(index, id,
  label, url, fallback_url, ocr_url, ocr_format)` for the pages with an image, `index` from 1
- IIIF: `canvas_images()` plus OCR links from the canvas's `seeAlso`/`rendering`
  (`IIIFCanvas.see_also`, `IIIFCanvas.rendering`); ALTO before hOCR
- METS: `METSParser.parse_element()`; physical page divs (TYPE "page", any case) sorted by
  `ORDER` when every page has one; file pointers from `fptr/@FILEID` and `fptr//area/@FILEID`;
  image = the page's file in the first group of `Config.mets_image_groups` that has one, then
  other `image/*` groups (never `THUMBS`, `MIN`, `LOCAL`, ...), fallback = the next group's;
  MODS from the dmdSec of the first logical div with a DMDID; the digitisation's originInfo is
  skipped; `required_statement` is the DFG-viewer `dv:owner`

#### 7. **Models** (`src/pybookget/models/iiif.py`, `src/pybookget/models/mets.py`)
Data models for IIIF manifests:
- `IIIFManifest`: Top-level manifest (v2/v3)
- `IIIFCanvas`: Canvas/page representation
- `IIIFImage`: Image with service info
- `IIIFService`: IIIF Image API service
- `parse_iiif_manifest()`: Parser supporting both v2 and v3
- `METSDocument` (pages in reading order, files by ID, file groups, OBJID, dv:owner/dv:license),
  `METSPage`, `METSFile`, `METSMetadata` (MODS, with `METSName` names and roles)

### Handler Flow

```
User Request
    ↓
CLI/Library API
    ↓
download_from_url(url, config, handler="iiif")  # Explicit handler selection
    ↓
HandlerRegistry.get_handler(handler, url, config)
    ↓
IIIFHandler.run()
    ├── Fetch manifest
    ├── Parse manifest (v2/v3)
    ├── Extract title
    ├── Extract image URLs with fallbacks
    │   ├── _build_image_url_with_fallback()
    │   ├── _calculate_size_parameter() (smart sizing)
    │   └── Returns (primary_url, fallback_url)
    ├── Create DownloadTasks with fallback URLs
    └── DownloadManager.execute()
        ├── Try primary IIIF URL
        ├── On 404: Try fallback URL
        └── Return results
```

### Key Design Patterns

- **Strategy Pattern**: BaseHandler defines interface, handlers implement specific logic
- **Factory Pattern**: Handler registry creates handlers by name
- **Decorator Pattern**: `@register_handler()` for handler registration
- **Explicit Configuration**: All settings via Config class, no magic defaults
- **Async/Await**: All I/O operations use asyncio
- **Dataclass Pattern**: Extensive use of dataclasses for data structures

### IIIF Image API

The IIIF handler constructs URLs following the IIIF Image API specification:

```
{scheme}://{server}{/prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
```

**Example URLs:**
- Full size (v2): `https://iiif.example.org/image123/full/full/0/default.jpg`
- Full size (v3): `https://iiif.example.org/image123/full/max/0/default.jpg`

**Size Parameter Selection:**
- IIIF Image API v3: Always uses `"max"` (canonical full-size parameter)
- IIIF Image API v2: Always uses `"full"` (canonical full-size parameter)
- Version detection is automatic based on service metadata

## Configuration

Configuration is managed through the `Config` dataclass in `pybookget/config.py`.

### Key Configuration Options

```python
config = Config(
    # Download settings
    download_dir="./downloads",
    page_range="1:100",           # Filter pages
    volume_range="1:5",           # Filter volumes

    # Concurrency
    threads_per_task=1,           # Threads per download
    max_concurrent_tasks=16,      # Concurrent downloads

    # HTTP settings
    timeout=300,                  # Request timeout (seconds)
    user_agent="...",             # Custom user agent
    proxy="http://...",           # proxy for every request; None = the environment's
    trust_env=True,               # environment proxy settings (HTTP(S)_PROXY, ALL_PROXY, NO_PROXY)
    verify_ssl=True,              # TLS verification (default True)

    # Retry configuration (tenacity)
    max_retries=3,                # Max retry attempts
    retry_wait_min=1.0,           # Min wait between retries
    retry_wait_max=10.0,          # Max wait between retries
    retry_multiplier=2.0,         # Exponential backoff multiplier

    # IIIF Image API parameters (always requests full size)
    iiif_quality="default",       # default, color, gray, bitonal
    iiif_format="jpg",            # jpg, png, webp, tif
    iiif_region="full",           # Region parameter
    iiif_rotation="0",            # Rotation parameter

    # Authentication
    cookie_file="cookies.txt",    # Netscape format
    header_file="headers.txt",    # Custom headers

    # Other
    sleep_interval=0,             # Pause after each download (seconds, per worker)
    rate_limits=[(10, 1), (400, 60)],  # (requests, seconds) windows, all at once; None = no limit
    show_progress=True,           # Progress bars
)
```

### Proxies

`Config` does not read proxy variables itself: with `proxy=None` httpx applies the environment's
settings (`trust_env=True`: upper- and lower-case `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`, and
`NO_PROXY`). An explicit `proxy` overrides them for every request; `trust_env=False` ignores the
environment. Tests build their Config with `trust_env=False` (or run against a loopback server
with a dead proxy port, `tests/test_proxy.py`).

### Rate limiting

`Config.rate_limits` is enforced by pyrate-limiter (`http/ratelimit.py`). `create_client()`
registers an httpx **request event hook** that awaits the limiter before every request, so
retries, redirects, fallback URLs and manifest fetches all count, and every client created from
the same Config shares one limit. A hook rather than a custom transport on purpose: when a
client has `proxy=`, httpx routes requests through its own proxy transport and bypasses a custom
transport (tested in `tests/test_ratelimit.py`). The limiter is cached per Config **and event
loop** (`Config._limiters`), because asyncio locks bind to a loop and the interactive CLI calls
`asyncio.run()` repeatedly with one Config. Windows are validated with pyrate's
`validate_rate_list` when the Config is created. CLI: `--rate-limit REQUESTS/SECONDS`
(repeatable) on `download` and `batch`.

## Adding Custom Handlers

To add support for a new site/API:

1. **Create handler** in `src/pybookget/handlers/mysite.py`:
```python
from pybookget.router.base import BaseHandler
from pybookget.router.registry import register_handler

@register_handler("mysite")  # Register by name, not domain
class MySiteHandler(BaseHandler):
    """Handler for mysite.com custom API"""

    async def run(self):
        # Extract book ID
        self.book_id = self.get_book_id()

        # Fetch data
        client = self._ensure_client()
        response = await client.get(self.url)
        data = response.json()

        # Extract image URLs
        image_urls = [item['url'] for item in data['images']]

        # Download images
        save_dir = self.get_save_dir()
        downloaded = await self.download_images(image_urls, save_dir)

        return self._create_result(len(image_urls), downloaded)
```

2. **Import in** `src/pybookget/handlers/__init__.py`:
```python
from pybookget.handlers import iiif, mysite
```

3. **Import in** `src/pybookget/router/registry.py` in `_initialize_handlers()`:
```python
from pybookget.handlers import iiif, mysite
```

4. **Use with CLI or library**:
```bash
pybookget download URL --handler mysite
```

```python
result = asyncio.run(download_from_url(url, config, handler="mysite"))
```

## Common Tasks

### Reading a manifest
```python
from pybookget.models.iiif import parse_iiif_manifest
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get("https://www.loc.gov/item/ltf90007547/manifest.json")
    manifest_data = response.json()
    manifest = parse_iiif_manifest(manifest_data)

    print(f"Title: {manifest.label}")
    print(f"Canvases: {len(manifest.canvases)}")
```

### Using the download manager directly
```python
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.config import Config
from pathlib import Path

config = Config()
dm = DownloadManager(config)

tasks = [
    DownloadTask(
        url="https://example.com/image1.jpg",
        save_path=Path("./output/0001.jpg"),
        fallback_url="https://example.com/fallback/image1.jpg"
    ),
    # ... more tasks
]

dm.add_tasks(tasks)
successful = await dm.execute()
```

### Creating a custom client
```python
from pybookget.http.client import create_client
from pybookget.config import Config

config = Config(
    timeout=300,
    verify_ssl=False,
    proxy="http://proxy:8080"
)

client = create_client(config)
# Use client for requests
response = await client.get("https://example.com")
await client.aclose()
```

## Important Notes for Development

1. **Async-only**: All I/O operations must be async. Use `asyncio.run()` at the top level.

2. **No automatic URL routing**: Users must explicitly specify handler via `--handler` flag.

3. **Handler registration by name**: `@register_handler("iiif")` not `@register_handler("*.edu")`

4. **File-level resumability**: Files are skipped if they exist. No partial downloads.

5. **Direct httpx usage**: Don't create custom HTTP wrappers. Use httpx directly.

6. **IIIF is the focus**: The IIIF handler is the primary/default handler. Custom handlers are for special cases.

7. **Smart features**: Size negotiation and fallback URLs make the IIIF handler work with more servers.

8. **Configuration over convention**: All behavior is controlled via Config class.

## Dependencies

Key dependencies (see `pyproject.toml`):
- **httpx**: Async HTTP client with HTTP/2 support
- **tenacity**: Retry logic with exponential backoff
- **pyrate-limiter** (4.x): Async request rate limiting (`Config.rate_limits`)
- **click** (`[cli]` extra): CLI framework
- **tqdm**: Progress bars
- **pydantic** (optional): May be used for validation in future

## Testing Strategy

`tests/test_ratelimit.py` covers rate limiting (parsing, validation, shared limits, retries,
proxies, repeated event loops, DownloadManager). `tests/test_download.py` covers the download
manager and `download_file` (streaming, per-task results, retry policy, Retry-After, atomic
writes, defaults). `tests/test_iiif.py` covers manifest parsing (v2/v3, labels, rights), page
image URLs and `fetch` (retries, fallback on 404); `tests/test_manifest.py` the manifest API
(DFG METS with MODS, OAI-PMH wrapping, image group priority, IIIF v2/v3 OCR links, format
detection, collections); `tests/test_proxy.py` the proxy settings. Still to be added:
- Integration tests for download manager
- Mock-based tests for handlers
- CLI tests with Click's testing utilities

## Differences from Go Version

| Aspect | Go (bookget) | Python (pybookget) |
|--------|-------------|-------------------|
| **Handlers** | 50+ site-specific handlers | Universal IIIF + extensible for custom sites |
| **URL Routing** | Automatic domain matching | Explicit `--handler` selection |
| **Concurrency** | Goroutines + channels | asyncio + semaphores |
| **HTTP Client** | Custom gohttp package | Direct httpx usage |
| **IIIF Support** | Basic | Smart size negotiation + fallbacks |
| **Usage** | CLI-only | Library + CLI |
| **Type System** | Go types | Python type hints + dataclasses |
| **Config** | INI files | Python dataclass (programmatic) |

## Philosophy

The Python rewrite prioritizes:
- **Simplicity**: Fewer abstractions, easier to understand
- **Explicitness**: No magic, clear intent
- **Modularity**: Easy to import and use as a library
- **Standards**: Follows IIIF specifications closely
- **Compatibility**: Works with maximum number of IIIF servers via smart features
- **Python idioms**: Async/await, dataclasses, type hints, modern packaging
