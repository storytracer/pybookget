"""Generic IIIF (International Image Interoperability Framework) handler.

This handler supports any IIIF-compliant manifest (v2 or v3).
"""

import json
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

    def _detect_image_api_version(self, service) -> int:
        """Detect IIIF Image API version from service information.

        Args:
            service: IIIFService object

        Returns:
            API version as integer (2 or 3), defaults to 2 if unknown
        """
        if not service:
            return 2

        # Check type field (v3 uses "ImageService3", "ImageService2")
        if service.type:
            if "ImageService3" in service.type or "ImageService3" == service.type:
                return 3
            elif "ImageService2" in service.type or "ImageService2" == service.type:
                return 2

        # Check context field
        if service.context:
            if "/image/3/" in service.context or "image/3/context" in service.context:
                return 3
            elif "/image/2/" in service.context or "image/2/context" in service.context:
                return 2

        # Check profile field
        if service.profile:
            profile_str = service.profile if isinstance(service.profile, str) else str(service.profile)
            if "/image/3/" in profile_str:
                return 3
            elif "/image/2/" in profile_str or "/image/1/" in profile_str:
                return 2

        # Default to v2 for backwards compatibility
        logger.debug("Unable to detect IIIF Image API version, defaulting to v2")
        return 2

    def _calculate_size_parameter(self, image) -> str:
        """Calculate IIIF size parameter based on Image API version.

        Always requests full resolution images using the version-appropriate parameter:
        - IIIF Image API v3: "max" (canonical)
        - IIIF Image API v2: "full" (canonical)

        Args:
            image: IIIF image object with service information

        Returns:
            IIIF size parameter ("max" for v3, "full" for v2)
        """
        # Detect Image API version
        api_version = self._detect_image_api_version(image.service)

        # Determine canonical full-size parameter based on API version
        # v3: "max" (full is deprecated)
        # v2: "full" (canonical form)
        full_size_param = "max" if api_version == 3 else "full"

        logger.debug(f"Requesting full size using '{full_size_param}' (Image API v{api_version})")
        return full_size_param

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
