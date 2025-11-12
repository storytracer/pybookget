"""Command-line interface for pybookget using Click."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from pybookget import __version__
from pybookget.config import Config
from pybookget.router.registry import download_from_url, HandlerRegistry


# Setup logging - default to WARNING to avoid interfering with progress bars
# INFO and DEBUG logs are only shown when --verbose is used
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.option('--version', '-v', is_flag=True, help='Show version and exit')
@click.pass_context
def cli(ctx, version):
    """pybookget - Download IIIF-compliant digital books.

    A Python tool for downloading high-resolution images from any
    IIIF-compliant digital library worldwide (Harvard, Princeton,
    Library of Congress, and many more).
    """
    if version:
        click.echo(f"pybookget version {__version__}")
        ctx.exit()

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument('url')
@click.option('--handler', '-h', default='iiif', help='Handler to use (default: iiif)')
@click.option('--output', '-o', default='./downloads', help='Output directory')
@click.option('--pages', '-p', help='Page range (e.g., "4:434")')
@click.option('--volume', help='Volume range for multi-volume books')
@click.option('--threads', '-t', default=1, help='Threads per download task')
@click.option('--concurrent', '-c', default=16, help='Max concurrent tasks')
@click.option('--timeout', default=300, help='Request timeout in seconds')
@click.option('--max-retries', default=3, help='Maximum retry attempts')
@click.option('--retry-wait-min', default=1.0, help='Minimum wait between retries (seconds)')
@click.option('--retry-wait-max', default=10.0, help='Maximum wait between retries (seconds)')
@click.option('--cookie-file', help='Path to cookie file (Netscape format)')
@click.option('--header-file', help='Path to header file')
@click.option('--proxy', help='HTTP/HTTPS proxy')
@click.option('--user-agent', '-U', help='Custom user agent')
@click.option('--no-ssl-verify', is_flag=True, help='Disable SSL verification')
@click.option('--quality', default=80, help='JPEG quality (1-100)')
@click.option('--iiif-max-size', type=int, help='IIIF max image dimension in pixels (default: full size)')
@click.option('--iiif-quality', default='default', help='IIIF quality: default, color, gray, bitonal')
@click.option('--iiif-format', default='jpg', help='IIIF format: jpg, png, webp, tif')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def download(
    url: str,
    handler: str,
    output: str,
    pages: Optional[str],
    volume: Optional[str],
    threads: int,
    concurrent: int,
    timeout: int,
    max_retries: int,
    retry_wait_min: float,
    retry_wait_max: float,
    cookie_file: Optional[str],
    header_file: Optional[str],
    proxy: Optional[str],
    user_agent: Optional[str],
    no_ssl_verify: bool,
    quality: int,
    iiif_max_size: Optional[int],
    iiif_quality: str,
    iiif_format: str,
    verbose: bool,
):
    """Download a book from a URL.

    Example:
        pybookget download "https://iiif.lib.harvard.edu/manifests/..." -o ./books
    """
    # Enable verbose logging if requested
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
        # Also enable httpx logging
        logging.getLogger('httpx').setLevel(logging.INFO)

    # Create configuration
    config = Config(
        download_dir=output,
        page_range=pages,
        volume_range=volume,
        threads_per_task=threads,
        max_concurrent_tasks=concurrent,
        timeout=timeout,
        max_retries=max_retries,
        retry_wait_min=retry_wait_min,
        retry_wait_max=retry_wait_max,
        cookie_file=cookie_file,
        header_file=header_file,
        proxy=proxy,
        verify_ssl=not no_ssl_verify,
        quality=quality,
        iiif_max_size=iiif_max_size,
        iiif_quality=iiif_quality,
        iiif_format=iiif_format,
    )

    if user_agent:
        config.user_agent = user_agent

    # Execute download
    click.echo(f"Handler: {handler}")
    click.echo(f"Downloading from: {url}")
    click.echo(f"Output directory: {output}")

    result = asyncio.run(download_from_url(url, config, handler=handler))

    if result and result.get('success'):
        click.echo(f"\n✓ Success!")
        click.echo(f"  Title: {result['title']}")
        click.echo(f"  Downloaded: {result['downloaded']}/{result['total_pages']} pages")
        click.echo(f"  Location: {result['save_path']}")
    else:
        error = result.get('error', 'Unknown error') if result else 'Handler not found'
        click.echo(f"\n✗ Failed: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--handler', '-h', default='iiif', help='Handler to use (default: iiif)')
@click.option('--output', '-o', default='./downloads', help='Output directory')
@click.option('--concurrent', '-c', default=4, help='Max concurrent books')
@click.option('--threads', '-t', default=1, help='Threads per download task')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def batch(
    file: str,
    handler: str,
    output: str,
    concurrent: int,
    threads: int,
    verbose: bool,
):
    """Download multiple books from a file containing URLs.

    The file should contain one URL per line.

    Example:
        pybookget batch urls.txt -o ./books -c 4
    """
    # Enable verbose logging if requested
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
        # Also enable httpx logging
        logging.getLogger('httpx').setLevel(logging.INFO)

    # Read URLs from file
    urls = []
    with open(file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)

    if not urls:
        click.echo("No URLs found in file", err=True)
        sys.exit(1)

    click.echo(f"Found {len(urls)} URLs to download")
    click.echo(f"Concurrent books: {concurrent}")

    # Create configuration
    config = Config(
        download_dir=output,
        max_concurrent_tasks=concurrent,
        threads_per_task=threads,
    )

    # Download each URL
    async def download_all():
        """Async function to download all URLs concurrently."""
        nonlocal successful, failed

        with click.progressbar(length=len(urls), label='Downloading books') as bar:
            # Create semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(concurrent)

            async def download_with_semaphore(url):
                async with semaphore:
                    try:
                        result = await download_from_url(url, config, handler=handler)
                        if result and result.get('success'):
                            return True
                        else:
                            logger.error(f"Failed to download: {url}")
                            return False
                    except Exception as e:
                        logger.error(f"Error downloading {url}: {e}")
                        return False

            # Create all download tasks
            tasks = [download_with_semaphore(url) for url in urls]

            # Process results as they complete
            for coro in asyncio.as_completed(tasks):
                success = await coro
                if success:
                    successful += 1
                else:
                    failed += 1
                bar.update(1)

    successful = 0
    failed = 0

    asyncio.run(download_all())

    click.echo(f"\nComplete: {successful} successful, {failed} failed")


@cli.command()
@click.option('--handler', '-h', default='iiif', help='Handler to use (default: iiif)')
def interactive(handler: str):
    """Interactive mode - prompts for URLs to download.

    Enter URLs one at a time, or 'quit' to exit.
    """
    click.echo(f"Interactive mode - using '{handler}' handler")
    click.echo("Enter URLs to download (or 'quit' to exit)")
    click.echo()

    config = Config()

    while True:
        url = click.prompt("Enter URL", type=str, default='', show_default=False)

        if not url or url.lower() in ['quit', 'exit', 'q']:
            click.echo("Goodbye!")
            break

        # Download the URL
        result = asyncio.run(download_from_url(url, config, handler=handler))

        if result and result.get('success'):
            click.echo(f"✓ Downloaded {result['downloaded']} pages to {result['save_path']}")
        else:
            error = result.get('error', 'Unknown error') if result else 'Handler not found'
            click.echo(f"✗ Failed: {error}", err=True)

        click.echo()


@cli.command()
def list_handlers():
    """List available handlers."""
    click.echo("Available handlers:")
    click.echo()

    handlers = HandlerRegistry.list_available_handlers()

    for handler in handlers:
        click.echo(f"  • {handler}")

    click.echo()
    click.echo(f"Total: {len(handlers)} handler(s) available")
    click.echo()
    click.echo("The 'iiif' handler (default) works with any IIIF Presentation API v2/v3")
    click.echo("manifest from any digital library worldwide (Harvard, Princeton, LoC, etc.).")
    click.echo()
    click.echo("Use --handler to specify: pybookget download URL --handler iiif")


@cli.command()
@click.argument('url')
@click.option('--handler', '-h', default='iiif', help='Handler to test (default: iiif)')
def info(url: str, handler: str):
    """Show information about a URL and handler.

    This helps verify the handler can be initialized for a URL.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc

    click.echo(f"URL: {url}")
    click.echo(f"Domain: {domain}")
    click.echo(f"Handler: {handler}")
    click.echo()

    # Try to get handler
    config = Config()
    handler_instance = HandlerRegistry.get_handler(handler, url, config)

    if handler_instance:
        click.echo(f"✓ Handler '{handler}' initialized successfully")
        click.echo(f"  Class: {handler_instance.__class__.__name__}")
        click.echo(f"  Module: {handler_instance.__class__.__module__}")
    else:
        click.echo(f"✗ Handler '{handler}' not found")
        click.echo()
        click.echo("Use 'pybookget list-handlers' to see available handlers")


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
