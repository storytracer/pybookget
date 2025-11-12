"""Configuration management for pybookget."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class Config:
    """Configuration for pybookget downloader.

    This class manages all configuration options including download paths,
    concurrency settings, authentication, and page/volume ranges.
    """

    # Download paths
    download_dir: str = "./downloads"
    cookie_file: Optional[str] = None
    header_file: Optional[str] = None

    # Page and volume ranges
    page_range: Optional[str] = None  # Format: "4:434"
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    volume_range: Optional[str] = None
    volume_start: Optional[int] = None
    volume_end: Optional[int] = None

    # Concurrency settings
    max_concurrent_tasks: int = 16  # Number of concurrent book downloads
    threads_per_task: int = 1  # Threads per image download

    # HTTP settings
    timeout: int = 300  # seconds
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    proxy: Optional[str] = None
    verify_ssl: bool = False  # Match Go's InsecureSkipVerify

    # Retry settings (using tenacity)
    max_retries: int = 3  # Maximum number of retry attempts
    retry_wait_min: float = 1.0  # Minimum wait between retries (seconds)
    retry_wait_max: float = 10.0  # Maximum wait between retries (seconds)
    retry_multiplier: float = 2.0  # Exponential backoff multiplier

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

    # Downloader mode
    downloader_mode: int = 0  # 0=default, 1=batch image, 2=IIIF

    # Progress display
    show_progress: bool = True

    def __post_init__(self):
        """Initialize and validate configuration."""
        # Parse page range if provided
        if self.page_range:
            self._parse_page_range()

        # Parse volume range if provided
        if self.volume_range:
            self._parse_volume_range()

        # Setup proxy from environment if not specified
        if not self.proxy:
            self.proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')

        # Ensure download directory exists
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

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
