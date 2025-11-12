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

```bash
# Install in development mode
cd pybookget
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

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
    --pages "1:50" \
    --iiif-max-size 2000

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
# Run tests (when tests are added)
pytest

# With coverage
pytest --cov=pybookget

# Type checking
mypy src/pybookget/

# Linting
ruff check src/pybookget/

# Code formatting
black src/pybookget/
```

## Architecture

### Project Structure

```
pybookget/                 # Git repository root
├── README.md              # Comprehensive documentation
├── CLAUDE.md              # This file
├── LICENSE                # GPL-3.0
├── pyproject.toml         # Package configuration
├── requirements.txt       # Direct dependencies list
└── src/                   # Source code (src layout)
    └── pybookget/         # Python package
        ├── __init__.py        # Package exports
        ├── __main__.py        # Entry point for python -m pybookget
        ├── config.py          # Configuration management (Config class)
        ├── cli.py             # Click-based CLI interface
        ├── models/            # Data models
        │   └── iiif.py        # IIIF manifest parsing (v2 & v3)
        ├── http/              # HTTP utilities (async-only)
        │   ├── client.py      # httpx AsyncClient factory
        │   ├── download.py    # Async download manager with fallback support
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
- **IIIF Image API parameters** (max_size, quality, format, region, rotation)
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

**Smart Size Negotiation:**
- `_calculate_size_parameter()`: Intelligently determines optimal IIIF size based on:
  - Configured `iiif_max_size` limit
  - Actual image dimensions from manifest
  - Image orientation (landscape vs portrait)
- Requests full size when images fit within limits
- Constrains by larger dimension when exceeding limits

**Fallback URL Mechanism:**
- `_build_image_url_with_fallback()`: Returns (primary_url, fallback_url) tuples
- Primary: Optimized IIIF URL with size parameters
- Fallback: Direct image URL (used if IIIF params return 404)
- Automatic retry in download manager on 404 errors

**Key Methods:**
- `run()`: Main execution flow
- `_extract_title()`: Handles v2/v3 label formats
- `_extract_image_urls()`: Extracts images from canvases
- `_build_image_url()`: Builds IIIF Image API URLs
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
  - Semaphore-based concurrency control
  - Progress tracking with tqdm
  - **Fallback retry on 404**: Tries fallback_url if primary fails with 404
  - Tenacity retry logic for network errors

**Retry Logic:**
- Uses tenacity library for exponential backoff
- Configurable max retries, wait times, multiplier
- Only retries on httpx errors (HTTPError, TimeoutException, NetworkError)

#### 6. **Models** (`src/pybookget/models/iiif.py`)
Data models for IIIF manifests:
- `IIIFManifest`: Top-level manifest (v2/v3)
- `IIIFCanvas`: Canvas/page representation
- `IIIFImage`: Image with service info
- `IIIFService`: IIIF Image API service
- `parse_iiif_manifest()`: Parser supporting both v2 and v3

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
- Full size: `https://iiif.example.org/image123/full/full/0/default.jpg`
- Constrained width: `https://iiif.example.org/image123/full/2000,/0/default.jpg`
- Constrained height: `https://iiif.example.org/image123/full/,1500/0/gray.png`

**Smart Sizing Logic:**
1. No `iiif_max_size` → Request `full`
2. Image dimensions unknown → Request `{max_size},` (safe constraint)
3. Image fits within max → Request `full`
4. Landscape (width > height) → Request `{max_size},`
5. Portrait/Square → Request `,{max_size}`

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
    proxy="http://...",           # HTTP/HTTPS proxy
    verify_ssl=False,             # SSL verification

    # Retry configuration (tenacity)
    max_retries=3,                # Max retry attempts
    retry_wait_min=1.0,           # Min wait between retries
    retry_wait_max=10.0,          # Max wait between retries
    retry_multiplier=2.0,         # Exponential backoff multiplier

    # IIIF Image API parameters
    iiif_max_size=2000,           # Max dimension (None = full size)
    iiif_quality="default",       # default, color, gray, bitonal
    iiif_format="jpg",            # jpg, png, webp, tif
    iiif_region="full",           # Region parameter
    iiif_rotation="0",            # Rotation parameter

    # Authentication
    cookie_file="cookies.txt",    # Netscape format
    header_file="headers.txt",    # Custom headers

    # Other
    sleep_interval=0,             # Rate limiting (seconds)
    show_progress=True,           # Progress bars
)
```

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
- **click**: CLI framework
- **tqdm**: Progress bars
- **pydantic** (optional): May be used for validation in future

## Testing Strategy

(Tests to be added)
- Unit tests for parsers (IIIF manifest parsing)
- Unit tests for URL builders (IIIF Image API URLs)
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
