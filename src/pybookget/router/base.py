"""Base handler class for all site-specific handlers (async-only)."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from pybookget.config import Config
from pybookget.http.client import create_client
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.utils.text import extract_id_from_url, get_domain, url_to_slug

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Base class for all site-specific download handlers (async-only).

    Each handler implements site-specific logic for:
    - Extracting book IDs from URLs
    - Fetching manifests or API responses
    - Parsing image URLs
    - Managing downloads

    Attributes:
        url: The URL to download from
        config: Configuration object
        client: httpx.AsyncClient for making requests
        book_id: Extracted book identifier
        title: Book title
    """

    def __init__(self, url: str, config: Config):
        """Initialize handler.

        Args:
            url: URL to download from
            config: Configuration object
        """
        self.url = url
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.book_id: Optional[str] = None
        self.title: str = "unknown"
        self.volume_id: Optional[str] = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure httpx client is created (lazy initialization).

        Returns:
            httpx.AsyncClient instance
        """
        if self.client is None:
            self.client = create_client(self.config)
        return self.client

    @abstractmethod
    async def run(self) -> Dict[str, any]:
        """Execute the download process.

        This is the main entry point for each handler. It should:
        1. Extract book ID from URL
        2. Fetch manifest/API data
        3. Parse image URLs
        4. Download images

        Returns:
            Dictionary with download results:
            {
                "type": "iiif" | "api" | "generic",
                "url": original_url,
                "book_id": extracted_book_id,
                "title": book_title,
                "total_pages": number_of_pages,
                "downloaded": number_downloaded,
                "save_path": Path_to_downloads,
            }
        """
        pass

    def get_book_id(self, pattern: Optional[str] = None) -> str:
        """Extract book ID from URL.

        Args:
            pattern: Optional regex pattern for extraction

        Returns:
            Extracted book ID
        """
        book_id = extract_id_from_url(self.url, pattern)
        if book_id:
            self.book_id = book_id
        return book_id or "unknown"

    def get_save_dir(self) -> Path:
        """Get the save directory for this book.

        Uses base64-encoded URL slug as the directory name.
        The slug is deterministic, reversible, and works universally
        with any IIIF manifest URL.

        Creates three subdirectories:
        - images/: For downloaded image files
        - metadata/: For manifest.json and other metadata
        - ocr/: For OCR text files (created but initially empty)

        Returns:
            Path object for base save directory
        """
        domain = get_domain(self.url)

        # Create reversible slug from URL (base64url-encoded)
        url_slug = url_to_slug(self.url)

        # Create directory structure: downloads/domain/slug/
        # Format: downloads/www.loc.gov/aHR0cHM6Ly93d3cubG9jLmdvdi9pdGVtL2x0ZjkwMDA3NTQ3L21hbmlmZXN0Lmpzb24/
        save_dir = Path(self.config.download_dir) / domain / url_slug
        save_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (save_dir / "images").mkdir(exist_ok=True)
        (save_dir / "metadata").mkdir(exist_ok=True)
        (save_dir / "ocr").mkdir(exist_ok=True)

        return save_dir

    def get_images_dir(self) -> Path:
        """Get the images subdirectory.

        Returns:
            Path object for images directory
        """
        return self.get_save_dir() / "images"

    def get_metadata_dir(self) -> Path:
        """Get the metadata subdirectory.

        Returns:
            Path object for metadata directory
        """
        return self.get_save_dir() / "metadata"

    def get_ocr_dir(self) -> Path:
        """Get the OCR subdirectory.

        Returns:
            Path object for OCR directory
        """
        return self.get_save_dir() / "ocr"

    def create_download_tasks(
        self,
        image_urls: List[str],
        save_dir: Optional[Path] = None,
        extension: Optional[str] = None,
        start_index: int = 1,
    ) -> List[DownloadTask]:
        """Create download tasks from list of image URLs.

        Args:
            image_urls: List of image URLs to download
            save_dir: Directory to save files (defaults to images/ subdirectory)
            extension: File extension (defaults to config.file_ext)
            start_index: Starting index for filenames

        Returns:
            List of DownloadTask objects
        """
        if save_dir is None:
            save_dir = self.get_images_dir()

        if extension is None:
            extension = self.config.file_ext

        tasks = []
        for idx, url in enumerate(image_urls, start=start_index):
            # Apply page range filter if configured
            if not self.config.is_page_in_range(idx):
                continue

            # Generate filename with zero-padding
            filename = f"{str(idx).zfill(4)}{extension}"
            save_path = save_dir / filename

            task = DownloadTask(
                url=url,
                save_path=save_path,
                book_id=self.book_id or "unknown",
                title=self.title,
                volume_id=self.volume_id or "",
            )
            tasks.append(task)

        return tasks

    async def download_images(
        self,
        image_urls: List[str],
        save_dir: Optional[Path] = None,
        extension: Optional[str] = None,
        start_index: int = 1,
    ) -> int:
        """Download images using the download manager.

        Args:
            image_urls: List of image URLs to download
            save_dir: Directory to save files (defaults to images/ subdirectory)
            extension: File extension
            start_index: Starting index for filenames

        Returns:
            Number of successfully downloaded files
        """
        logger.info(f"Downloading {len(image_urls)} images...")

        # Create download tasks
        tasks = self.create_download_tasks(
            image_urls=image_urls,
            save_dir=save_dir,
            extension=extension,
            start_index=start_index,
        )

        if not tasks:
            logger.warning("No tasks to download (possibly filtered by page range)")
            return 0

        # Execute downloads
        dm = DownloadManager(self.config)
        dm.add_tasks(tasks)
        successful = await dm.execute()

        return successful

    async def close(self):
        """Close httpx client if it was created."""
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _create_result(
        self,
        total_pages: int,
        downloaded: int,
        error: Optional[str] = None,
    ) -> Dict[str, any]:
        """Create standardized result dictionary.

        Args:
            total_pages: Total number of pages/images
            downloaded: Number successfully downloaded
            error: Optional error message

        Returns:
            Result dictionary
        """
        result = {
            "type": self.__class__.__name__.replace("Handler", "").lower(),
            "url": self.url,
            "book_id": self.book_id or "unknown",
            "title": self.title,
            "total_pages": total_pages,
            "downloaded": downloaded,
            "save_path": str(self.get_save_dir()) if downloaded > 0 else None,
            "success": downloaded > 0 and error is None,
        }

        if error:
            result["error"] = error

        return result
