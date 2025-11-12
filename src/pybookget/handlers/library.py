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

from rocrate.rocrate import ROCrate
from rocrate.model.person import Person
from rocrate.model.contextentity import ContextEntity

from pybookget.config import Config
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

    Subclasses must implement:
    - fetch_and_save_metadata(): Fetch metadata and return LibraryBook
    - get_ocr_tasks(): Create download tasks for OCR files
    - get_image_tasks(): Create download tasks for images

    Subclasses can override:
    - save_metadata_files(): Customize metadata file saving
    - download_ocr(): Customize OCR download logic
    - download_images_from_book(): Customize image download logic
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
        4. Call save_metadata_files() to save raw metadata

        Returns:
            LibraryBook object with metadata and pages populated

        Raises:
            Exception if metadata cannot be fetched or parsed
        """
        pass

    async def save_metadata_files(self, **kwargs) -> None:
        """Save metadata files to disk using RO-Crate format.

        Default implementation creates RO-Crate metadata following Dublin Core standard.
        Subclasses should override this to save additional library-specific metadata files
        (manifest.json, mets.xml, etc.) and can call this method to generate RO-Crate.

        The RO-Crate includes:
        - Root dataset with book metadata (Dublin Core)
        - hasPart references to images and OCR files
        - Person entities for creators

        Args:
            **kwargs: Library-specific metadata to save
        """
        if not self.library_book:
            logger.warning("No library book available to save metadata")
            return

        metadata_dir = self.get_metadata_dir()

        try:
            # Create RO-Crate
            crate = ROCrate()

            # Set root dataset metadata (the book itself)
            root = crate.root_dataset
            metadata = self.library_book.metadata

            # Required Dublin Core fields
            root["name"] = metadata.title  # dc:title
            root["datePublished"] = metadata.date  # dc:date

            # Creator (dc:creator) - create Person entity
            creator = Person(crate, identifier=f"#{metadata.creator.replace(' ', '_')}")
            creator["name"] = metadata.creator
            crate.add(creator)
            root["creator"] = creator

            # Optional Dublin Core fields
            if metadata.contributor:
                contributor = Person(crate, identifier=f"#{metadata.contributor.replace(' ', '_')}_contributor")
                contributor["name"] = metadata.contributor
                crate.add(contributor)
                root["contributor"] = contributor

            if metadata.publisher:
                publisher = ContextEntity(
                    crate,
                    identifier=f"#{metadata.publisher.replace(' ', '_')}",
                    properties={
                        "@type": "Organization",
                        "name": metadata.publisher
                    }
                )
                crate.add(publisher)
                root["publisher"] = publisher

            if metadata.type:
                root["@type"] = ["Dataset", metadata.type]  # dc:type

            if metadata.format:
                root["encodingFormat"] = metadata.format  # dc:format

            if metadata.identifier:
                root["identifier"] = metadata.identifier  # dc:identifier

            if metadata.source:
                root["isBasedOn"] = metadata.source  # dc:source

            if metadata.language:
                root["inLanguage"] = metadata.language  # dc:language

            if metadata.relation:
                root["relatedLink"] = metadata.relation  # dc:relation

            if metadata.coverage:
                root["spatialCoverage"] = metadata.coverage  # dc:coverage

            if metadata.rights:
                root["license"] = metadata.rights  # dc:rights

            if metadata.description:
                root["description"] = metadata.description  # dc:description

            if metadata.subject:
                root["keywords"] = metadata.subject  # dc:subject

            # Add book-specific metadata
            root["numberOfPages"] = self.library_book.total_pages
            root["bookId"] = self.library_book.book_id

            # Add hasPart relationships to images and OCR files
            parts = []

            # Add image files
            images_dir = self.get_images_dir()
            if images_dir.exists():
                for img_file in sorted(images_dir.glob("*")):
                    if img_file.is_file():
                        rel_path = img_file.relative_to(self.get_save_dir())
                        parts.append(str(rel_path))

            # Add OCR files
            ocr_dir = self.get_ocr_dir()
            if ocr_dir.exists():
                for ocr_file in sorted(ocr_dir.rglob("*")):
                    if ocr_file.is_file():
                        rel_path = ocr_file.relative_to(self.get_save_dir())
                        parts.append(str(rel_path))

            if parts:
                root["hasPart"] = [{"@id": part} for part in parts]

            # Write RO-Crate metadata
            crate.metadata.write(metadata_dir)
            logger.info(f"Saved RO-Crate metadata to {metadata_dir / 'ro-crate-metadata.json'}")

        except Exception as e:
            logger.error(f"Failed to save metadata files: {e}", exc_info=True)

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
