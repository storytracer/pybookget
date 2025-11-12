"""
Base handler for library-specific downloads with metadata, OCR, and image support.

This module provides a base class for handlers that need to download:
1. Metadata (always downloaded, serialized as RO-Crate)
2. OCR files (optional, controlled by --skip-ocr flag)
3. Images (optional, controlled by --skip-images flag)

Subclasses should implement the abstract methods to provide library-specific logic.
Metadata follows Dublin Core standard and is serialized using RO-Crate v1.2.
"""

import json
import logging
from abc import abstractmethod
from pathlib import Path
from typing import Dict, Optional

from pybookget.config import Config
from pybookget.formats.rocrate import ROCrateWriter
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.models.library import LibraryBook, LibraryPage
from pybookget.router.base import BaseHandler

logger = logging.getLogger(__name__)


class LibraryHandler(BaseHandler):
    """Base handler for library-specific downloads.

    This handler provides a standardized workflow for downloading digital books
    from libraries that provide metadata, OCR, and images.

    Standard workflow:
    1. Fetch and save metadata (always done)
    2. Download OCR files (skipped if config.skip_ocr is True)
    3. Download images (skipped if config.skip_images is True)
    4. Write RO-Crate metadata with hasPart relationships (automatic)

    Subclasses must implement:
    - fetch_and_save_metadata(): Fetch metadata and return LibraryBook

    Subclasses can override:
    - save_rocrate_metadata(): Customize RO-Crate metadata generation
    - download_ocr(): Customize OCR download logic
    - download_images_from_book(): Customize image download logic
    - get_ocr_tasks(): Customize OCR task creation
    - get_image_tasks(): Customize image task creation
    """

    def __init__(self, url: str, config: Config):
        """Initialize library handler.

        Args:
            url: URL to download from
            config: Configuration object
        """
        super().__init__(url, config)
        self.library_book: Optional[LibraryBook] = None

    async def run(self) -> Dict[str, any]:
        """Execute library book download with standard workflow.

        Workflow:
        1. Fetch and save metadata (always)
        2. Download OCR files (if not skipped)
        3. Download images (if not skipped)

        Returns:
            Dictionary with download results including:
            - success: bool
            - title: str
            - total_pages: int
            - images_downloaded: int
            - ocr_files_downloaded: int
            - save_path: str
        """
        logger.info(f"Processing library book: {self.url}")

        try:
            # Phase 1: Fetch and save metadata (always done)
            logger.info("Phase 1: Fetching and saving metadata...")
            self.library_book = await self.fetch_and_save_metadata()

            if not self.library_book:
                raise ValueError("Failed to fetch metadata")

            # Set title and book_id for BaseHandler
            self.title = self.library_book.title
            self.book_id = self.library_book.book_id

            logger.info(f"Book: {self.title}")
            logger.info(f"Total pages: {self.library_book.total_pages}")

            # Track download counts
            images_downloaded = 0
            ocr_files_downloaded = 0

            # Phase 2: Download OCR files (if not skipped)
            if not self.config.skip_ocr:
                logger.info("Phase 2: Downloading OCR files...")
                ocr_files_downloaded = await self.download_ocr(self.library_book)
                logger.info(f"Downloaded {ocr_files_downloaded} OCR files")
            else:
                logger.info("Phase 2: Skipping OCR downloads (--skip-ocr flag set)")

            # Phase 3: Download images (if not skipped)
            if not self.config.skip_images:
                logger.info("Phase 3: Downloading images...")
                images_downloaded = await self.download_images_from_book(self.library_book)
                logger.info(f"Downloaded {images_downloaded} images")
            else:
                logger.info("Phase 3: Skipping image downloads (--skip-images flag set)")

            # Phase 4: Write RO-Crate metadata (after downloads complete)
            logger.info("Phase 4: Writing RO-Crate metadata...")
            await self.save_rocrate_metadata()

            logger.info(
                f"Download complete: {images_downloaded}/{self.library_book.total_pages} images, "
                f"{ocr_files_downloaded} OCR files"
            )

            return self._create_library_result(
                total_pages=self.library_book.total_pages,
                images_downloaded=images_downloaded,
                ocr_files_downloaded=ocr_files_downloaded,
            )

        except Exception as e:
            logger.error(f"Failed to process library book: {e}", exc_info=True)
            return self._create_library_result(0, 0, 0, error=str(e))

    @abstractmethod
    async def fetch_and_save_metadata(self) -> LibraryBook:
        """Fetch metadata and return a LibraryBook object.

        This method should:
        1. Fetch all necessary metadata (IIIF, METS, API responses, etc.)
        2. Parse the metadata
        3. Create and return a LibraryBook object with pages
        4. Optionally save library-specific metadata files (manifest.json, mets.xml, etc.)
           to the metadata/ subdirectory

        Note: RO-Crate metadata is written automatically after downloads complete.

        Returns:
            LibraryBook object with metadata and pages populated

        Raises:
            Exception if metadata cannot be fetched or parsed
        """
        pass

    async def save_rocrate_metadata(self, **kwargs) -> None:
        """Write RO-Crate metadata to the root directory.

        This method is called automatically after all downloads complete.
        It creates an RO-Crate metadata file following the Dublin Core standard,
        including hasPart relationships to all downloaded images and OCR files.

        Uses the ROCrateWriter from the formats module for standardized
        RO-Crate generation.

        Args:
            **kwargs: Library-specific metadata to save
        """
        if not self.library_book:
            logger.warning("No library book available to save metadata")
            return

        save_dir = self.get_save_dir()
        images_dir = self.get_images_dir()
        ocr_dir = self.get_ocr_dir()

        try:
            # Use ROCrateWriter to generate RO-Crate metadata
            writer = ROCrateWriter(include_files=True)
            writer.write(
                self.library_book,
                save_dir,
                images_dir=images_dir,
                ocr_dir=ocr_dir
            )
            logger.info(f"Saved RO-Crate metadata to {save_dir / 'ro-crate-metadata.json'}")

        except Exception as e:
            logger.error(f"Failed to save RO-Crate metadata: {e}", exc_info=True)

    async def download_ocr(self, book: LibraryBook) -> int:
        """Download OCR files for the book.

        Default implementation:
        1. Gets OCR tasks from get_ocr_tasks()
        2. Applies page range filtering
        3. Downloads using DownloadManager

        Args:
            book: LibraryBook object with pages containing OCR URLs

        Returns:
            Number of successfully downloaded OCR files
        """
        tasks = await self.get_ocr_tasks(book)

        if not tasks:
            logger.warning("No OCR tasks to download")
            return 0

        logger.info(f"Downloading {len(tasks)} OCR files...")

        # Execute downloads
        dm = DownloadManager(self.config)
        dm.add_tasks(tasks)
        successful = await dm.execute()

        return successful

    async def get_ocr_tasks(self, book: LibraryBook) -> list[DownloadTask]:
        """Create download tasks for OCR files.

        Default implementation creates tasks for ALTO XML and plain text files
        from pages that have OCR URLs. Applies page range filtering.

        Subclasses can override to customize OCR task creation.

        Args:
            book: LibraryBook object with pages

        Returns:
            List of DownloadTask objects for OCR files
        """
        ocr_dir = self.get_ocr_dir()
        alto_dir = ocr_dir / "alto"
        text_dir = ocr_dir / "text"

        # Create subdirectories
        alto_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)

        tasks = []

        for page in book.pages:
            # Apply page range filter
            if not self.config.is_page_in_range(page.order):
                continue

            page_num_str = str(page.order).zfill(4)

            # Add ALTO XML task
            if page.alto_url:
                alto_path = alto_dir / f"{page_num_str}.xml"
                tasks.append(
                    DownloadTask(
                        url=page.alto_url,
                        save_path=alto_path,
                        book_id=self.book_id or "unknown",
                        title=self.title,
                    )
                )

            # Add plain text task
            if page.plain_text_url:
                text_path = text_dir / f"{page_num_str}.txt"
                tasks.append(
                    DownloadTask(
                        url=page.plain_text_url,
                        save_path=text_path,
                        book_id=self.book_id or "unknown",
                        title=self.title,
                    )
                )

        return tasks

    async def download_images_from_book(self, book: LibraryBook) -> int:
        """Download images for the book.

        Default implementation:
        1. Gets image tasks from get_image_tasks()
        2. Applies page range filtering
        3. Downloads using DownloadManager

        Args:
            book: LibraryBook object with pages containing image URLs

        Returns:
            Number of successfully downloaded images
        """
        tasks = await self.get_image_tasks(book)

        if not tasks:
            logger.warning("No image tasks to download")
            return 0

        logger.info(f"Downloading {len(tasks)} images...")

        # Execute downloads
        dm = DownloadManager(self.config)
        dm.add_tasks(tasks)
        successful = await dm.execute()

        return successful

    async def get_image_tasks(self, book: LibraryBook) -> list[DownloadTask]:
        """Create download tasks for images.

        Default implementation creates tasks from pages with image URLs,
        supporting primary and fallback URLs. Applies page range filtering.

        Subclasses can override to customize image task creation.

        Args:
            book: LibraryBook object with pages

        Returns:
            List of DownloadTask objects for images
        """
        images_dir = self.get_images_dir()
        tasks = []

        for page in book.pages:
            # Apply page range filter
            if not self.config.is_page_in_range(page.order):
                continue

            if not page.image_url:
                continue

            page_num_str = str(page.order).zfill(4)
            image_path = images_dir / f"{page_num_str}{self.config.file_ext}"

            tasks.append(
                DownloadTask(
                    url=page.image_url,
                    save_path=image_path,
                    fallback_url=page.image_fallback_url,
                    book_id=self.book_id or "unknown",
                    title=self.title,
                )
            )

        return tasks

    def _create_library_result(
        self,
        total_pages: int,
        images_downloaded: int,
        ocr_files_downloaded: int,
        error: Optional[str] = None,
    ) -> Dict[str, any]:
        """Create standardized result dictionary for library handlers.

        Args:
            total_pages: Total number of pages in the book
            images_downloaded: Number of images successfully downloaded
            ocr_files_downloaded: Number of OCR files successfully downloaded
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
            "images_downloaded": images_downloaded,
            "ocr_files_downloaded": ocr_files_downloaded,
            "save_path": str(self.get_save_dir()) if images_downloaded > 0 or ocr_files_downloaded > 0 else None,
            "success": (images_downloaded > 0 or ocr_files_downloaded > 0) and error is None,
        }

        if error:
            result["error"] = error

        # For backwards compatibility, include 'downloaded' key
        result["downloaded"] = images_downloaded

        return result
