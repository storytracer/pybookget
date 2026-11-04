"""Generic IIIF (International Image Interoperability Framework) handler.

This handler supports any IIIF-compliant manifest (v2 or v3).
"""

import json
import logging
from pathlib import Path

from pybookget.formats.iiif import IIIFParser, image_url
from pybookget.models.iiif import IIIFCanvas
from pybookget.router.base import BaseHandler
from pybookget.router.registry import register_handler

logger = logging.getLogger(__name__)


@register_handler("iiif")
class IIIFHandler(BaseHandler):
    """Handler for IIIF manifests.

    Supports both IIIF Presentation API v2 and v3 manifests.
    Works with any institution that provides IIIF-compliant manifests.

    This is the default handler for pybookget.
    """

    async def run(self) -> dict[str, any]:
        """Execute IIIF manifest download.

        Returns:
            Dictionary with download results
        """
        logger.info(f"Processing IIIF manifest: {self.url}")

        try:
            # Fetch and parse manifest
            client = self._ensure_client()
            response = await client.get(self.url)
            response.raise_for_status()
            manifest_data = response.json()

            # Parse IIIF manifest using format parser
            parser = IIIFParser()
            manifest = parser.parse(manifest_data)

            # Extract metadata
            self.book_id = self.get_book_id()
            self.title = self._extract_title(manifest)

            logger.info(f"Book: {self.title} (ID: {self.book_id})")
            logger.info(f"Total pages: {len(manifest.canvases)}")

            # Save manifest.json to metadata directory
            await self._save_manifest(manifest_data)

            # Extract image URLs from canvases (with fallbacks)
            image_url_pairs = self._extract_image_urls(manifest.canvases)

            if not image_url_pairs:
                logger.warning("No images found in manifest")
                return self._create_result(0, 0)

            # Download images to images/ subdirectory
            images_dir = self.get_images_dir()
            downloaded = await self._download_images_with_fallback(image_url_pairs, images_dir)

            logger.info(f"Download complete: {downloaded}/{len(image_url_pairs)} images")

            return self._create_result(len(image_url_pairs), downloaded)

        except Exception as e:
            logger.error(f"Failed to process IIIF manifest: {e}", exc_info=True)
            return self._create_result(0, 0, error=str(e))

    def _extract_title(self, manifest) -> str:
        """Extract title from manifest.

        Args:
            manifest: IIIF manifest object (v2 or v3)

        Returns:
            Book title
        """
        if hasattr(manifest, 'label'):
            label = manifest.label

            # Handle v3 format (multilingual)
            if isinstance(label, dict):
                # Try English first, then any language
                if 'en' in label:
                    return label['en'][0] if label['en'] else 'unknown'
                for lang_values in label.values():
                    if lang_values:
                        return lang_values[0]

            # Handle v2 format (string)
            elif isinstance(label, str):
                return label

        return 'unknown'

    async def _save_manifest(self, manifest_data: dict) -> None:
        """Save manifest.json to metadata directory.

        Args:
            manifest_data: Raw manifest data as dictionary
        """
        metadata_dir = self.get_metadata_dir()
        manifest_path = metadata_dir / "manifest.json"

        try:
            # Write manifest with pretty formatting
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved manifest to {manifest_path}")
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")

    def _extract_image_urls(self, canvases: list[IIIFCanvas]) -> list[tuple]:
        """(primary_url, fallback_url or None) for each canvas with an image.

        See ``pybookget.formats.iiif.image_url``.
        """
        pairs = []
        for canvas in canvases:
            if canvas.images:
                url, fallback = image_url(canvas.images[0], self.config)
                if url:
                    pairs.append((url, fallback))
        return pairs

    async def _download_images_with_fallback(
        self,
        image_url_pairs: list[tuple],
        save_dir: Path,
        extension: str | None = None,
        start_index: int = 1,
    ) -> int:
        """Download images with fallback URL support.

        Args:
            image_url_pairs: List of (primary_url, fallback_url) tuples
            save_dir: Directory to save files
            extension: File extension
            start_index: Starting index for filenames

        Returns:
            Number of successfully downloaded files
        """
        from pybookget.http.download import DownloadManager, DownloadTask

        logger.info(f"Downloading {len(image_url_pairs)} images with fallback support...")

        if extension is None:
            extension = self.config.file_ext

        # Create download tasks with fallback URLs
        tasks = []
        for idx, (primary_url, fallback_url) in enumerate(image_url_pairs, start=start_index):
            # Apply page range filter if configured
            if not self.config.is_page_in_range(idx):
                continue

            # Generate filename with zero-padding
            filename = f"{str(idx).zfill(4)}{extension}"
            save_path = save_dir / filename

            task = DownloadTask(
                url=primary_url,
                save_path=save_path,
                book_id=self.book_id or "unknown",
                title=self.title,
                volume_id=self.volume_id or "",
                fallback_url=fallback_url,  # Add fallback URL
            )
            tasks.append(task)

        if not tasks:
            logger.warning("No tasks to download (possibly filtered by page range)")
            return 0

        # Execute downloads
        dm = DownloadManager(self.config)
        dm.add_tasks(tasks)
        successful = await dm.execute()

        return successful
