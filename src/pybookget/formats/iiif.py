"""
IIIF (International Image Interoperability Framework) format parser.

This module provides parsing capabilities for IIIF Presentation API manifests,
supporting both version 2 and version 3 of the specification.

The parser auto-detects the version and returns the appropriate data model.
``canvas_images()`` turns a parsed manifest into the URLs of its page images.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pybookget.config import Config
from pybookget.formats.base import VersionedParser
from pybookget.models.iiif import (
    IIIFCanvas,
    IIIFImage,
    IIIFManifestV2,
    IIIFManifestV3,
    IIIFService,
)

logger = logging.getLogger(__name__)


class IIIFParser(VersionedParser[dict[str, Any], IIIFManifestV2 | IIIFManifestV3]):
    """Parser for IIIF Presentation API manifests (v2 and v3).

    This parser automatically detects the IIIF version and returns the
    appropriate data model (IIIFManifestV2 or IIIFManifestV3).

    Example:
        >>> parser = IIIFParser()
        >>> manifest = parser.parse(manifest_json)
        >>> print(f"Version: {parser.detect_version(manifest_json)}")
        Version: 3.0
    """

    def parse(self, data: dict[str, Any]) -> IIIFManifestV2 | IIIFManifestV3:
        """Parse IIIF manifest JSON into structured data model.

        Args:
            data: Raw IIIF manifest as dictionary (parsed JSON)

        Returns:
            IIIFManifestV2 or IIIFManifestV3 depending on detected version

        Raises:
            ValueError: If manifest format is not recognized or invalid
        """
        # Check for v3 indicators
        if 'type' in data and data.get('type') == 'Manifest':
            return IIIFManifestV3.from_dict(data)
        # Check for v2 indicators
        elif '@context' in data or 'sequences' in data:
            return IIIFManifestV2.from_dict(data)
        else:
            raise ValueError("Unable to determine IIIF manifest version")

    def validate(self, data: dict[str, Any]) -> bool:
        """Validate IIIF manifest structure.

        Args:
            data: Raw IIIF manifest dictionary

        Returns:
            True if valid IIIF manifest, False otherwise
        """
        if not isinstance(data, dict):
            return False

        # Check for required fields based on version
        version = self.detect_version(data)
        if version == "3.0":
            # IIIF v3 requires: @context, id, type
            return (
                '@context' in data or 'context' in data
            ) and 'id' in data and data.get('type') == 'Manifest'
        elif version == "2.1":
            # IIIF v2 requires: @context, @id, @type or sequences
            return (
                '@context' in data or 'context' in data
            ) and ('@id' in data or 'id' in data)

        return False

    def detect_version(self, data: dict[str, Any]) -> str | None:
        """Detect IIIF Presentation API version from manifest.

        Args:
            data: Raw IIIF manifest dictionary

        Returns:
            Version string ('2.1' or '3.0') or None if cannot be determined
        """
        if not isinstance(data, dict):
            return None

        # Check for v3 indicators
        if 'type' in data and data.get('type') == 'Manifest':
            return "3.0"

        # Check for v2 indicators
        if '@context' in data or 'sequences' in data:
            # Try to extract version from context
            context = data.get('@context', '')
            if isinstance(context, str):
                if '/context/2/' in context or 'iiif.io/api/presentation/2' in context:
                    return "2.1"
                elif '/context/3/' in context or 'iiif.io/api/presentation/3' in context:
                    return "3.0"
            return "2.1"  # Default to 2.1 if has @context

        return None

    def supported_versions(self) -> list[str]:
        """Return list of supported IIIF versions.

        Returns:
            List of version strings
        """
        return ["2.1", "3.0"]

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "IIIF Presentation API"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return [
            "application/json",
            "application/ld+json",
            "application/iiif+json",
        ]


class IIIFParserV2(VersionedParser[dict[str, Any], IIIFManifestV2]):
    """Parser specifically for IIIF Presentation API v2 manifests.

    Use this when you know you're working with v2 manifests and want
    type safety guarantees.
    """

    def parse(self, data: dict[str, Any]) -> IIIFManifestV2:
        """Parse IIIF v2 manifest.

        Args:
            data: Raw IIIF v2 manifest dictionary

        Returns:
            IIIFManifestV2 object

        Raises:
            ValueError: If not a valid IIIF v2 manifest
        """
        if not self.validate(data):
            raise ValueError("Invalid IIIF v2 manifest")
        return IIIFManifestV2.from_dict(data)

    def validate(self, data: dict[str, Any]) -> bool:
        """Validate IIIF v2 manifest."""
        return isinstance(data, dict) and (
            '@context' in data or 'context' in data
        ) and 'sequences' in data

    def detect_version(self, data: dict[str, Any]) -> str | None:
        """Always returns '2.1' for this parser."""
        return "2.1" if self.validate(data) else None

    def supported_versions(self) -> list[str]:
        """Return supported versions."""
        return ["2.1", "2.0"]

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "IIIF Presentation API v2"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return ["application/json", "application/ld+json"]


class IIIFParserV3(VersionedParser[dict[str, Any], IIIFManifestV3]):
    """Parser specifically for IIIF Presentation API v3 manifests.

    Use this when you know you're working with v3 manifests and want
    type safety guarantees.
    """

    def parse(self, data: dict[str, Any]) -> IIIFManifestV3:
        """Parse IIIF v3 manifest.

        Args:
            data: Raw IIIF v3 manifest dictionary

        Returns:
            IIIFManifestV3 object

        Raises:
            ValueError: If not a valid IIIF v3 manifest
        """
        if not self.validate(data):
            raise ValueError("Invalid IIIF v3 manifest")
        return IIIFManifestV3.from_dict(data)

    def validate(self, data: dict[str, Any]) -> bool:
        """Validate IIIF v3 manifest."""
        return (
            isinstance(data, dict)
            and data.get('type') == 'Manifest'
            and 'id' in data
        )

    def detect_version(self, data: dict[str, Any]) -> str | None:
        """Always returns '3.0' for this parser."""
        return "3.0" if self.validate(data) else None

    def supported_versions(self) -> list[str]:
        """Return supported versions."""
        return ["3.0"]

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "IIIF Presentation API v3"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return ["application/ld+json", "application/iiif+json"]


# Convenience function for backward compatibility
def parse_iiif_manifest(data: dict[str, Any]) -> IIIFManifestV2 | IIIFManifestV3:
    """Parse IIIF manifest with automatic version detection.

    This is a convenience function that wraps IIIFParser for easy use.

    Args:
        data: Raw IIIF manifest as dictionary

    Returns:
        IIIFManifestV2 or IIIFManifestV3 depending on version

    Raises:
        ValueError: If manifest format is not recognized
    """
    parser = IIIFParser()
    return parser.parse(data)


# --- page images --------------------------------------------------------------------------


@dataclass(frozen=True)
class CanvasImage:
    """The image of one canvas, as pybookget downloads it.

    ``url`` is the IIIF Image API request for the full image (or the image's own
    URL when it has no image service); ``fallback_url`` is the image's own URL,
    tried when the Image API request returns 404. ``index`` counts the canvases
    that have an image, from 1, as the handlers number the files they save.
    """

    index: int
    canvas: IIIFCanvas
    image: IIIFImage
    url: str
    fallback_url: str | None = None


def image_api_version(service: IIIFService | None) -> int:
    """The IIIF Image API version (2 or 3) of an image service; 2 when unknown."""
    if not service:
        return 2
    if service.type:
        if "ImageService3" in service.type:
            return 3
        if "ImageService2" in service.type:
            return 2
    if service.context:
        if "/image/3/" in service.context:
            return 3
        if "/image/2/" in service.context:
            return 2
    if service.profile:
        profile = service.profile if isinstance(service.profile, str) else str(service.profile)
        if "/image/3/" in profile:
            return 3
        if "/image/2/" in profile or "/image/1/" in profile:
            return 2
    logger.debug("Unable to detect IIIF Image API version, defaulting to v2")
    return 2


def full_size_parameter(service: IIIFService | None) -> str:
    """The canonical full-size parameter: ``max`` for Image API v3, ``full`` for v2."""
    return "max" if image_api_version(service) == 3 else "full"


def image_url(image: IIIFImage, config: Config) -> tuple[str, str | None]:
    """The (primary, fallback) URLs for downloading an image at full size.

    With an image service, the primary URL is the Image API request
    ``{service}/{region}/{size}/{rotation}/{quality}.{format}`` built from the
    config's ``iiif_*`` parameters, and the fallback is the image's own URL.
    Without a service, the image's own URL is the only one.
    """
    if not image.service:
        return image.id, None
    url = (
        f"{image.service.id.rstrip('/')}/"
        f"{config.iiif_region}/"
        f"{full_size_parameter(image.service)}/"
        f"{config.iiif_rotation}/"
        f"{config.iiif_quality}.{config.iiif_format}"
    )
    return url, image.id or None


def canvas_images(manifest: IIIFManifestV2 | IIIFManifestV3, config: Config) -> list[CanvasImage]:
    """One CanvasImage per canvas that has an image (its first one), in manifest order."""
    images = []
    for canvas in manifest.canvases:
        if not canvas.images:
            continue
        image = canvas.images[0]
        url, fallback = image_url(image, config)
        if url:
            images.append(CanvasImage(len(images) + 1, canvas, image, url, fallback))
    return images
