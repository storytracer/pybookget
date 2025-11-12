"""
e-rara.ch handler with IIIF, METS metadata, and OCR support.

This handler extends the LibraryHandler to support e-rara.ch's features:
- METS metadata (OAI-PMH)
- IIIF Presentation API (v2/v3) for images
- ALTO XML OCR files
- Plain text OCR files
"""

import json
import logging
import re
from typing import Optional

from pybookget.config import Config
from pybookget.handlers.iiif import IIIFHandler
from pybookget.handlers.library import LibraryHandler
from pybookget.models.erara import (
    ERaraBook,
    add_iiif_urls_to_book,
    create_erara_book_from_mets,
)
from pybookget.models.iiif import parse_iiif_manifest
from pybookget.models.library import LibraryBook
from pybookget.models.mets import parse_mets_xml
from pybookget.router.registry import register_handler

logger = logging.getLogger(__name__)


@register_handler("erara")
class ERaraHandler(LibraryHandler):
    """Handler for e-rara.ch digital books.

    Supports:
    - IIIF Presentation API (v2/v3) for images
    - METS metadata via OAI-PMH
    - ALTO XML OCR files
    - Plain text OCR files

    Download order: metadata → OCR → images
    Each phase can be skipped using config flags (except metadata).
    """

    def __init__(self, url: str, config: Config):
        """Initialize e-rara handler.

        Args:
            url: e-rara.ch URL (web page, IIIF manifest, or METS URL)
            config: Configuration object
        """
        super().__init__(url, config)
        self.iiif_helper = IIIFHandler(url, config)

    async def fetch_and_save_metadata(self) -> LibraryBook:
        """Fetch and save e-rara metadata (IIIF + METS).

        Returns:
            ERaraBook with metadata and pages populated

        Raises:
            ValueError: If book ID cannot be extracted
            Exception: If metadata cannot be fetched or parsed
        """
        # Extract book ID from URL
        book_id = self._extract_erara_id()
        if not book_id:
            raise ValueError(f"Could not extract e-rara book ID from URL: {self.url}")

        self.book_id = book_id
        logger.info(f"e-rara book ID: {book_id}")

        # Build URLs for IIIF and METS
        iiif_url = self._build_iiif_url(book_id)
        mets_url = self._build_mets_url(book_id)

        # Fetch metadata
        logger.info("Fetching IIIF manifest and METS metadata...")
        iiif_data, mets_data = await self._fetch_metadata(iiif_url, mets_url)

        # Parse manifests
        iiif_manifest = parse_iiif_manifest(iiif_data)
        mets_document = parse_mets_xml(mets_data)

        # Create combined book model from METS
        erara_book = create_erara_book_from_mets(book_id, mets_document)

        # Extract IIIF image URLs and add to book model
        image_url_pairs = self.iiif_helper._extract_image_urls(iiif_manifest.canvases)
        add_iiif_urls_to_book(erara_book, image_url_pairs)

        # Save library-specific metadata files (manifest.json, mets.xml)
        await self._save_library_metadata(
            iiif_data=iiif_data,
            mets_data=mets_data,
        )

        return erara_book

    async def _save_library_metadata(self, iiif_data: dict, mets_data: str) -> None:
        """Save e-rara library-specific metadata files.

        Saves to metadata/ subdirectory:
        - manifest.json (IIIF manifest)
        - mets.xml (METS metadata)

        Note: RO-Crate metadata is written automatically after downloads complete.

        Args:
            iiif_data: IIIF manifest as dictionary
            mets_data: METS XML as string
        """
        metadata_dir = self.get_metadata_dir()

        try:
            # Save IIIF manifest (library-specific format)
            manifest_path = metadata_dir / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(iiif_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved IIIF manifest to {manifest_path}")

            # Save METS (library-specific format)
            mets_path = metadata_dir / "mets.xml"
            with open(mets_path, 'w', encoding='utf-8') as f:
                f.write(mets_data)
            logger.info(f"Saved METS to {mets_path}")

        except Exception as e:
            logger.error(f"Failed to save library metadata files: {e}")

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

    def _build_iiif_url(self, book_id: str) -> str:
        """Build IIIF manifest URL from book ID.

        Args:
            book_id: e-rara book identifier

        Returns:
            IIIF manifest URL
        """
        return f"https://www.e-rara.ch/i3f/v20/{book_id}/manifest"

    def _build_mets_url(self, book_id: str) -> str:
        """Build METS URL from book ID.

        Args:
            book_id: e-rara book identifier

        Returns:
            METS OAI-PMH URL
        """
        return (
            f"https://www.e-rara.ch/oai"
            f"?verb=GetRecord&metadataPrefix=mets&identifier={book_id}"
        )

    async def _fetch_metadata(self, iiif_url: str, mets_url: str) -> tuple[dict, str]:
        """Fetch IIIF manifest and METS metadata.

        Args:
            iiif_url: IIIF manifest URL
            mets_url: METS OAI-PMH URL

        Returns:
            Tuple of (iiif_data, mets_xml_string)

        Raises:
            httpx.HTTPError: If requests fail
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
