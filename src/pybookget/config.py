"""Configuration management for pybookget."""

import weakref
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Configuration for pybookget downloader.

    This class manages all configuration options including download paths,
    concurrency settings, authentication, and page/volume ranges.
    """

    # Download paths
    download_dir: str = "./downloads"
    cookie_file: str | None = None
    header_file: str | None = None

    # Page and volume ranges
    page_range: str | None = None  # Format: "4:434"
    page_start: int | None = None
    page_end: int | None = None
    volume_range: str | None = None
    volume_start: int | None = None
    volume_end: int | None = None

    # Concurrency settings
    max_concurrent_tasks: int = 16  # Number of concurrent book downloads
    threads_per_task: int = 1  # Threads per image download

    # HTTP settings
    timeout: int = 300  # seconds
    use_fake_user_agent: bool = True  # Use random user agents for masking
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # An explicit proxy for every request. None: the environment's proxy settings apply as httpx
    # reads them (HTTPS_PROXY, HTTP_PROXY, ALL_PROXY, upper or lower case, and NO_PROXY), if trust_env
    proxy: str | None = None
    # Read proxy settings (and SSL_CERT_FILE, .netrc) from the environment, as httpx does; False ignores them
    trust_env: bool = True
    verify_ssl: bool = True  # Verify TLS certificates (disable with --no-ssl-verify)
    # Idle connections kept open for reuse; 0 opens a new connection for every request.
    # Keeping some (e.g. 16) saves a TLS handshake per file in bulk downloads from one server.
    max_keepalive_connections: int = 0

    # Retry settings (using tenacity)
    max_retries: int = 3  # Maximum number of retry attempts
    retry_wait_min: float = 1.0  # Minimum wait between retries (seconds)
    retry_wait_max: float = 10.0  # Maximum wait between retries (seconds)
    retry_multiplier: float = 2.0  # Exponential backoff multiplier
    retry_after_max: float = 300.0  # Longest Retry-After (seconds) honoured from a 429/503

    # Download settings
    use_dzi: bool = True  # Use DeepZoom/IIIF tiles
    file_ext: str = ".jpg"
    quality: int = 80  # JPEG quality for non-IIIF downloads

    # IIIF Image API parameters
    iiif_quality: str = "default"  # IIIF quality: default, color, gray, bitonal
    iiif_format: str = "jpg"  # IIIF format: jpg, png, webp, tif
    iiif_region: str = "full"  # IIIF region parameter (usually 'full')
    iiif_rotation: str = "0"  # IIIF rotation parameter (usually '0')

    # Rate limiting
    sleep_interval: int = 0  # Seconds between downloads
    # Request rate limits shared by every HTTP client created from this config, as
    # (requests, seconds) windows that all apply at once, e.g. [(10, 1), (80, 10), (400, 60)]
    # allows at most 10 requests per second, 80 per 10 seconds and 400 per minute.
    # None means unlimited. Enforced by pyrate-limiter (see pybookget.http.ratelimit).
    rate_limits: list[tuple[int, float]] | None = None

    # Downloader mode
    downloader_mode: int = 0  # 0=default, 1=batch image, 2=IIIF

    # Progress display
    show_progress: bool = True

    # Download control flags
    skip_images: bool = False  # Skip image downloads (metadata always downloaded)
    skip_ocr: bool = False  # Skip OCR downloads (metadata always downloaded)

    # One shared limiter per event loop, created on first use (asyncio locks are bound to a loop)
    _limiters: "weakref.WeakKeyDictionary" = field(
        default_factory=weakref.WeakKeyDictionary, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        """Initialize and validate configuration."""
        if self.rate_limits is not None:
            from pybookget.http.ratelimit import to_rates  # validates; raises ValueError

            self.rate_limits = [(int(n), float(s)) for n, s in self.rate_limits]
            to_rates(self.rate_limits)

        # Parse page range if provided
        if self.page_range:
            self._parse_page_range()

        # Parse volume range if provided
        if self.volume_range:
            self._parse_volume_range()

    def _parse_page_range(self) -> None:
        """Parse page range from format '4:434' to start and end integers."""
        if not self.page_range:
            return

        parts = self.page_range.split(':')
        if len(parts) == 2:
            try:
                self.page_start = int(parts[0])
                self.page_end = int(parts[1])
            except ValueError:
                raise ValueError(f"Invalid page range format: {self.page_range}")

    def _parse_volume_range(self) -> None:
        """Parse volume range to start and end integers."""
        if not self.volume_range:
            return

        parts = self.volume_range.split(':')
        if len(parts) == 2:
            try:
                self.volume_start = int(parts[0])
                self.volume_end = int(parts[1])
            except ValueError:
                raise ValueError(f"Invalid volume range format: {self.volume_range}")
        elif len(parts) == 1:
            try:
                vol = int(parts[0])
                self.volume_start = vol
                self.volume_end = vol
            except ValueError:
                raise ValueError(f"Invalid volume format: {self.volume_range}")

    def is_page_in_range(self, page_num: int) -> bool:
        """Check if a page number is within the configured range.

        Args:
            page_num: The page number to check

        Returns:
            True if page is in range or no range is set
        """
        if self.page_start is None or self.page_end is None:
            return True
        return self.page_start <= page_num <= self.page_end

    def is_volume_in_range(self, volume_num: int) -> bool:
        """Check if a volume number is within the configured range.

        Args:
            volume_num: The volume number to check

        Returns:
            True if volume is in range or no range is set
        """
        if self.volume_start is None or self.volume_end is None:
            return True
        return self.volume_start <= volume_num <= self.volume_end

    @classmethod
    def get_home_dir(cls) -> Path:
        """Get the pybookget home directory (~/.pybookget)."""
        home = Path.home() / ".pybookget"
        home.mkdir(parents=True, exist_ok=True)
        return home

    @classmethod
    def get_cache_dir(cls) -> Path:
        """Get the cache directory (~/.pybookget/cache)."""
        cache = cls.get_home_dir() / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        return cache
