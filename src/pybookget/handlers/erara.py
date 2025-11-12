"""
e-rara.ch handler with IIIF, METS metadata, and OCR support.

This handler extends the IIIF handler to support e-rara.ch's additional features:
- METS metadata (OAI-PMH)
- ALTO XML OCR files
- Plain text OCR files
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

from pybookget.config import Config
from pybookget.handlers.iiif import IIIFHandler
from pybookget.http.download import DownloadManager, DownloadTask
from pybookget.models.erara import (
    ERaraBook,
    add_iiif_urls_to_book,
    create_erara_book_from_mets,
)
from pybookget.models.iiif import parse_iiif_manifest
from pybookget.models.mets import parse_mets_xml
from pybookget.router.registry import register_handler

logger = logging.getLogger(__name__)


@register_handler("erara")
class ERaraHandler(IIIFHandler):
    """Handler for e-rara.ch digital books.

    Supports:
    - IIIF Presentation API (v2/v3) for images
    - METS metadata via OAI-PMH
    - ALTO XML OCR files
    - Plain text OCR files

    Download order: metadata → OCR → images
    """

    def __init__(self, url: str, config: Config):
        """Initialize e-rara handler.

        Args:
            url: e-rara.ch URL (web page, IIIF manifest, or METS URL)
            config: Configuration object
        """
        super().__init__(url, config)
        self.erara_book: Optional[ERaraBook] = None

    async def run(self) -> Dict[str, any]:
        """Execute e-rara book download.

        Downloads in order:
        1. Metadata (IIIF manifest + METS)
        2. OCR files (ALTO XML + plain text)
        3. Images (IIIF)

        Returns:
            Dictionary with download results
        """
        logger.info(f"Processing e-rara book: {self.url}")

        try:
            # Extract book ID from URL
            self.book_id = self._extract_erara_id()
            if not self.book_id:
                raise ValueError(f"Could not extract e-rara book ID from URL: {self.url}")

            logger.info(f"e-rara book ID: {self.book_id}")

            # Build URLs for IIIF and METS
            iiif_url = self._build_iiif_url()
            mets_url = self._build_mets_url()

            # Phase 1: Fetch and save metadata
            logger.info("Phase 1: Fetching metadata...")
            iiif_data, mets_data = await self._fetch_metadata(iiif_url, mets_url)

            # Parse manifests
            iiif_manifest = parse_iiif_manifest(iiif_data)
            mets_document = parse_mets_xml(mets_data)

            # Create combined book model
            self.erara_book = create_erara_book_from_mets(self.book_id, mets_document)
            self.title = self.erara_book.title

            logger.info(f"Book: {self.title}")
            logger.info(f"Total pages: {len(self.erara_book.pages)}")

            # Extract IIIF image URLs and add to book model
            image_url_pairs = self._extract_image_urls(iiif_manifest.canvases)
            add_iiif_urls_to_book(self.erara_book, image_url_pairs)

            # Save metadata files
            await self._save_metadata_files(iiif_data, mets_data)

            # Phase 2: Download OCR files
            logger.info("Phase 2: Downloading OCR files...")
            ocr_downloaded = await self._download_ocr_files()

            # Phase 3: Download images
            logger.info("Phase 3: Downloading images...")
            images_dir = self.get_images_dir()
            images_downloaded = await self._download_images_with_fallback(
                image_url_pairs, images_dir
            )

            logger.info(
                f"Download complete: {images_downloaded}/{len(image_url_pairs)} images, "
                f"{ocr_downloaded} OCR files"
            )

            return self._create_result(
                len(image_url_pairs),
                images_downloaded,
                ocr_downloaded=ocr_downloaded,
            )

        except Exception as e:
            logger.error(f"Failed to process e-rara book: {e}", exc_info=True)
            return self._create_result(0, 0, error=str(e))

    def _extract_erara_id(self) -> Optional[str]:
        """Extract e-rara book ID from URL.

        Supports multiple URL formats:
        - Web page: https://www.e-rara.ch/stp/content/titleinfo/24224395
        - IIIF manifest: https://www.e-rara.ch/i3f/v20/24224395/manifest
        - METS: https://www.e-rara.ch/oai?verb=GetRecord&...&identifier=24224395

        Returns:
            Book ID string or None
        """
        # Try numeric ID patterns
        patterns = [
            r'/titleinfo/(\d+)',  # Web page URL
            r'/v20/(\d+)',  # IIIF URL
            r'identifier=(\d+)',  # METS URL
            r'/(\d+)/',  # Generic numeric ID
            r'/(\d+)$',  # Trailing numeric ID
        ]

        for pattern in patterns:
            match = re.search(pattern, self.url)
            if match:
                return match.group(1)

        return None

    def _build_iiif_url(self) -> str:
        """Build IIIF manifest URL from book ID.

        Returns:
            IIIF manifest URL
        """
        return f"https://www.e-rara.ch/i3f/v20/{self.book_id}/manifest"

    def _build_mets_url(self) -> str:
        """Build METS URL from book ID.

        Returns:
            METS OAI-PMH URL
        """
        return (
            f"https://www.e-rara.ch/oai"
            f"?verb=GetRecord&metadataPrefix=mets&identifier={self.book_id}"
        )

    async def _fetch_metadata(self, iiif_url: str, mets_url: str) -> tuple[dict, str]:
        """Fetch IIIF manifest and METS metadata.

        Args:
            iiif_url: IIIF manifest URL
            mets_url: METS OAI-PMH URL

        Returns:
            Tuple of (iiif_data, mets_xml_string)
        """
        client = self._ensure_client()

        # Fetch IIIF manifest
        logger.debug(f"Fetching IIIF manifest: {iiif_url}")
        iiif_response = await client.get(iiif_url)
        iiif_response.raise_for_status()
        iiif_data = iiif_response.json()

        # Fetch METS
        logger.debug(f"Fetching METS metadata: {mets_url}")
        mets_response = await client.get(mets_url)
        mets_response.raise_for_status()
        mets_data = mets_response.text

        return iiif_data, mets_data

    async def _save_metadata_files(self, iiif_data: dict, mets_data: str) -> None:
        """Save metadata files to disk.

        Saves:
        - manifest.json (IIIF manifest)
        - mets.xml (METS metadata)
        - book_info.json (combined metadata from e-rara model)

        Args:
            iiif_data: IIIF manifest as dictionary
            mets_data: METS XML as string
        """
        metadata_dir = self.get_metadata_dir()

        try:
            # Save IIIF manifest
            manifest_path = metadata_dir / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(iiif_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved IIIF manifest to {manifest_path}")

            # Save METS
            mets_path = metadata_dir / "mets.xml"
            with open(mets_path, 'w', encoding='utf-8') as f:
                f.write(mets_data)
            logger.info(f"Saved METS to {mets_path}")

            # Save combined book info
            if self.erara_book:
                book_info_path = metadata_dir / "book_info.json"
                book_info = {
                    "book_id": self.erara_book.book_id,
                    "title": self.erara_book.title,
                    "subtitle": self.erara_book.subtitle,
                    "author": self.erara_book.author,
                    "publisher": self.erara_book.publisher,
                    "date": self.erara_book.date,
                    "language": self.erara_book.language,
                    "doi": self.erara_book.doi,
                    "license": self.erara_book.license,
                    "total_pages": len(self.erara_book.pages),
                }
                with open(book_info_path, 'w', encoding='utf-8') as f:
                    json.dump(book_info, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved book info to {book_info_path}")

        except Exception as e:
            logger.error(f"Failed to save metadata files: {e}")

    async def _download_ocr_files(self) -> int:
        """Download OCR files (ALTO XML and plain text).

        Downloads both ALTO and plain text versions for each page.
        Uses the same concurrent download manager as images.

        Returns:
            Number of successfully downloaded OCR files
        """
        if not self.erara_book or not self.erara_book.pages:
            logger.warning("No pages to download OCR for")
            return 0

        ocr_dir = self.get_ocr_dir()
        alto_dir = ocr_dir / "alto"
        text_dir = ocr_dir / "text"

        # Create subdirectories
        alto_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)

        # Create download tasks for OCR files
        tasks = []

        for page in self.erara_book.pages:
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

        if not tasks:
            logger.warning("No OCR files to download (possibly filtered by page range)")
            return 0

        logger.info(f"Downloading {len(tasks)} OCR files...")

        # Execute downloads with same concurrency control as images
        dm = DownloadManager(self.config)
        dm.add_tasks(tasks)
        successful = await dm.execute()

        return successful

    def _create_result(
        self,
        total_pages: int,
        downloaded: int,
        error: Optional[str] = None,
        ocr_downloaded: int = 0,
    ) -> Dict[str, any]:
        """Create standardized result dictionary.

        Args:
            total_pages: Total number of pages/images
            downloaded: Number of images successfully downloaded
            error: Optional error message
            ocr_downloaded: Number of OCR files downloaded

        Returns:
            Result dictionary
        """
        result = super()._create_result(total_pages, downloaded, error)
        result["ocr_files"] = ocr_downloaded
        result["type"] = "erara"
        return result
