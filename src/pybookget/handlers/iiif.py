"""Generic IIIF (International Image Interoperability Framework) handler.

This handler supports any IIIF-compliant manifest (v2 or v3).
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from pybookget.config import Config
from pybookget.models.iiif import parse_iiif_manifest, IIIFCanvas
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

    async def run(self) -> Dict[str, any]:
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
            manifest = parse_iiif_manifest(manifest_data)

            # Extract metadata
            self.book_id = self.get_book_id()
            self.title = self._extract_title(manifest)

            logger.info(f"Book: {self.title} (ID: {self.book_id})")
            logger.info(f"Total pages: {len(manifest.canvases)}")

            # Extract image URLs from canvases (with fallbacks)
            image_url_pairs = self._extract_image_urls(manifest.canvases)

            if not image_url_pairs:
                logger.warning("No images found in manifest")
                return self._create_result(0, 0)

            # Download images
            save_dir = self.get_save_dir()
            downloaded = await self._download_images_with_fallback(image_url_pairs, save_dir)

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

    def _extract_image_urls(self, canvases: List[IIIFCanvas]) -> List[tuple]:
        """Extract image URLs from IIIF canvases with fallback URLs.

        Args:
            canvases: List of IIIF canvas objects

        Returns:
            List of tuples: (primary_url, fallback_url or None)
        """
        image_url_pairs = []

        for canvas in canvases:
            if not canvas.images:
                continue

            # Get first image from canvas
            image = canvas.images[0]

            # Build image URL with fallback
            url_pair = self._build_image_url_with_fallback(image)
            if url_pair:
                image_url_pairs.append(url_pair)

        return image_url_pairs

    def _build_image_url_with_fallback(self, image) -> tuple:
        """Build IIIF image URL with fallback for better compatibility.

        Returns:
            Tuple of (primary_url, fallback_url)
            - primary_url: Optimized IIIF Image API URL with sizing
            - fallback_url: Direct image URL (used if IIIF params not supported)
        """
        # If image has a service, build IIIF URL with fallback
        if image.service:
            primary_url = self._build_image_url(image)
            # Fallback to direct image ID if IIIF parameters fail
            fallback_url = image.id if image.id else None
            return (primary_url, fallback_url)

        # No service - only direct URL available
        return (image.id, None)

    def _build_image_url(self, image) -> str:
        """Build optimized IIIF image URL with smart sizing.

        Uses IIIF Image API parameters to request appropriately-sized images
        based on configuration and image dimensions. Falls back to direct
        image URL if no IIIF service is available.

        Args:
            image: IIIF image object

        Returns:
            Optimized image URL
        """
        # If image has a service, use IIIF Image API
        if image.service:
            service_id = image.service.id.rstrip('/')

            # Calculate optimal size parameter
            size_param = self._calculate_size_parameter(image)

            # Build IIIF Image API URL
            # Format: {scheme}://{server}{/prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
            iiif_url = (
                f"{service_id}/"
                f"{self.config.iiif_region}/"
                f"{size_param}/"
                f"{self.config.iiif_rotation}/"
                f"{self.config.iiif_quality}.{self.config.iiif_format}"
            )

            logger.debug(f"Generated IIIF URL: {iiif_url}")
            return iiif_url

        # Otherwise use direct image ID (no IIIF service)
        logger.debug(f"No IIIF service, using direct URL: {image.id}")
        return image.id

    def _calculate_size_parameter(self, image) -> str:
        """Calculate optimal IIIF size parameter based on image dimensions.

        Implements smart size negotiation:
        - If no max_size configured: request full size
        - If image dimensions unknown: request max_size constraint
        - If image fits within max_size: request full size
        - If image exceeds max_size: request constrained size based on orientation

        Args:
            image: IIIF image object with optional width/height

        Returns:
            IIIF size parameter (e.g., "full", "2000,", ",1500", "!2000,2000")
        """
        # No size limit configured - request full resolution
        if not self.config.iiif_max_size:
            return "full"

        max_size = self.config.iiif_max_size

        # Image dimensions unknown - use safe constraint
        if not image.width or not image.height:
            logger.debug(f"Unknown dimensions, using max constraint: {max_size},")
            return f"{max_size},"

        # Check if image fits within max dimensions
        if image.width <= max_size and image.height <= max_size:
            logger.debug(f"Image ({image.width}x{image.height}) within limit, using full size")
            return "full"

        # Image exceeds max - constrain by larger dimension
        if image.width > image.height:
            # Landscape: constrain width
            logger.debug(f"Landscape image, constraining width to {max_size}")
            return f"{max_size},"
        else:
            # Portrait or square: constrain height
            logger.debug(f"Portrait/square image, constraining height to {max_size}")
            return f",{max_size}"

    async def _download_images_with_fallback(
        self,
        image_url_pairs: List[tuple],
        save_dir: Path,
        extension: Optional[str] = None,
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
