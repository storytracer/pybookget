"""IIIF (International Image Interoperability Framework) data models.

These models represent IIIF Presentation API v2 and v3 manifests.

For parsing IIIF manifests, use pybookget.formats.iiif.IIIFParser.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class IIIFService:
    """IIIF Image Service information."""

    id: str
    type: Optional[str] = None
    profile: Optional[str] = None
    context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IIIFService":
        """Create IIIFService from dictionary."""
        return cls(
            id=data.get('@id') or data.get('id', ''),
            type=data.get('@type') or data.get('type'),
            profile=data.get('profile'),
            context=data.get('@context') or data.get('context'),
        )


@dataclass
class IIIFImage:
    """IIIF Image resource."""

    id: str
    type: Optional[str] = None
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    service: Optional[IIIFService] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IIIFImage":
        """Create IIIFImage from dictionary."""
        # Handle service - can be dict or list
        service_data = data.get('service')
        service = None
        if service_data:
            if isinstance(service_data, list) and service_data:
                service = IIIFService.from_dict(service_data[0])
            elif isinstance(service_data, dict):
                service = IIIFService.from_dict(service_data)

        return cls(
            id=data.get('@id') or data.get('id', ''),
            type=data.get('@type') or data.get('type'),
            format=data.get('format'),
            width=data.get('width'),
            height=data.get('height'),
            service=service,
        )


@dataclass
class IIIFCanvas:
    """IIIF Canvas (page) information."""

    id: str
    label: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    images: List[IIIFImage] = field(default_factory=list)

    @classmethod
    def from_dict_v2(cls, data: Dict[str, Any]) -> "IIIFCanvas":
        """Create IIIFCanvas from IIIF v2 dictionary."""
        images = []
        for img_data in data.get('images', []):
            resource = img_data.get('resource', {})
            if resource:
                images.append(IIIFImage.from_dict(resource))

        return cls(
            id=data.get('@id', ''),
            label=data.get('label', ''),
            width=data.get('width'),
            height=data.get('height'),
            images=images,
        )

    @classmethod
    def from_dict_v3(cls, data: Dict[str, Any]) -> "IIIFCanvas":
        """Create IIIFCanvas from IIIF v3 dictionary."""
        images = []
        # V3 structure: canvas.items[].items[].body
        for item in data.get('items', []):
            for annotation in item.get('items', []):
                body = annotation.get('body', {})
                if body:
                    images.append(IIIFImage.from_dict(body))

        return cls(
            id=data.get('id', ''),
            label=data.get('label', {}).get('en', [''])[0] if isinstance(data.get('label', {}), dict) else data.get('label', ''),
            width=data.get('width'),
            height=data.get('height'),
            images=images,
        )


@dataclass
class IIIFManifestV2:
    """IIIF Presentation API v2 Manifest."""

    id: str
    label: Optional[str] = None
    description: Optional[str] = None
    metadata: List[Dict[str, Any]] = field(default_factory=list)
    canvases: List[IIIFCanvas] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IIIFManifestV2":
        """Create IIIFManifestV2 from dictionary."""
        canvases = []
        for sequence in data.get('sequences', []):
            for canvas_data in sequence.get('canvases', []):
                canvases.append(IIIFCanvas.from_dict_v2(canvas_data))

        return cls(
            id=data.get('@id', ''),
            label=data.get('label', ''),
            description=data.get('description', ''),
            metadata=data.get('metadata', []),
            canvases=canvases,
        )


@dataclass
class IIIFManifestV3:
    """IIIF Presentation API v3 Manifest."""

    id: str
    type: str
    label: Optional[Dict[str, List[str]]] = None
    summary: Optional[Dict[str, List[str]]] = None
    metadata: List[Dict[str, Any]] = field(default_factory=list)
    items: List[IIIFCanvas] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IIIFManifestV3":
        """Create IIIFManifestV3 from dictionary."""
        items = []
        for canvas_data in data.get('items', []):
            items.append(IIIFCanvas.from_dict_v3(canvas_data))

        return cls(
            id=data.get('id', ''),
            type=data.get('type', ''),
            label=data.get('label'),
            summary=data.get('summary'),
            metadata=data.get('metadata', []),
            items=items,
        )

    @property
    def canvases(self) -> List[IIIFCanvas]:
        """Alias for items to match v2 API."""
        return self.items


