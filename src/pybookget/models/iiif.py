"""IIIF (International Image Interoperability Framework) data models.

These models represent IIIF Presentation API v2 and v3 manifests.

For parsing IIIF manifests, use pybookget.formats.iiif.IIIFParser.
"""

from dataclasses import dataclass, field
from typing import Any


def label_text(value: Any) -> str | None:
    """The text of a IIIF label or value in any of its shapes, or None.

    v2: a string, a ``{"@value": ..., "@language": ...}`` object or a list of either;
    v3: a language map ``{"en": [...], "none": [...]}``. Prefers English, then
    ``none``, then any language; several values are joined with "; ".
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        texts = [t for t in (label_text(v) for v in value) if t]
        return "; ".join(texts) or None
    if isinstance(value, dict):
        if "@value" in value:
            return label_text(value["@value"])
        for lang in ("en", "none", *value):
            if value.get(lang):
                return label_text(value[lang])
    return None


def _entries(value: Any) -> list[dict[str, Any]]:
    """A IIIF property that may be one entry or a list of them, as a list of dicts."""
    if value is None:
        return []
    entries = value if isinstance(value, list) else [value]
    return [e if isinstance(e, dict) else {"id": e} for e in entries if isinstance(e, dict | str)]


@dataclass
class IIIFService:
    """IIIF Image Service information."""

    id: str
    type: str | None = None
    profile: str | None = None
    context: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IIIFService":
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
    type: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    service: IIIFService | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IIIFImage":
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
    label: str | None = None
    width: int | None = None
    height: int | None = None
    images: list[IIIFImage] = field(default_factory=list)
    # The canvas's "seeAlso" and "rendering" entries as given (a string becomes {"id": ...}),
    # e.g. links to the page's OCR (ALTO, hOCR)
    see_also: list[dict[str, Any]] = field(default_factory=list)
    rendering: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict_v2(cls, data: dict[str, Any]) -> "IIIFCanvas":
        """Create IIIFCanvas from IIIF v2 dictionary."""
        images = []
        for img_data in data.get('images', []):
            resource = img_data.get('resource', {})
            if resource:
                images.append(IIIFImage.from_dict(resource))

        return cls(
            id=data.get('@id', ''),
            label=label_text(data.get('label')) or '',
            width=data.get('width'),
            height=data.get('height'),
            images=images,
            see_also=_entries(data.get('seeAlso')),
            rendering=_entries(data.get('rendering')),
        )

    @classmethod
    def from_dict_v3(cls, data: dict[str, Any]) -> "IIIFCanvas":
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
            label=label_text(data.get('label')) or '',
            width=data.get('width'),
            height=data.get('height'),
            images=images,
            see_also=_entries(data.get('seeAlso')),
            rendering=_entries(data.get('rendering')),
        )


@dataclass
class IIIFManifestV2:
    """IIIF Presentation API v2 Manifest."""

    id: str
    label: str | None = None
    description: str | None = None
    metadata: list[dict[str, Any]] = field(default_factory=list)
    canvases: list[IIIFCanvas] = field(default_factory=list)
    rights: str | None = None  # v2 "license"
    required_statement: str | None = None  # v2 "attribution"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IIIFManifestV2":
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
            rights=label_text(data.get('license')),
            required_statement=label_text(data.get('attribution')),
        )


@dataclass
class IIIFManifestV3:
    """IIIF Presentation API v3 Manifest."""

    id: str
    type: str
    label: dict[str, list[str]] | None = None
    summary: dict[str, list[str]] | None = None
    metadata: list[dict[str, Any]] = field(default_factory=list)
    items: list[IIIFCanvas] = field(default_factory=list)
    rights: str | None = None
    required_statement: str | None = None  # the value of "requiredStatement"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IIIFManifestV3":
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
            rights=data.get('rights'),
            required_statement=label_text((data.get('requiredStatement') or {}).get('value')),
        )

    @property
    def canvases(self) -> list[IIIFCanvas]:
        """Alias for items to match v2 API."""
        return self.items


