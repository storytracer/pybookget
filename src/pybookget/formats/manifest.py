"""
Manifests independent of their format: an item's pages and their files, in reading order.

Two formats are read: IIIF Presentation API manifests (v2 and v3, see ``formats/iiif.py``) and
METS documents with MODS (see ``formats/mets.py``), plain or in an OAI-PMH response.
``read_manifest()`` returns a ``ManifestItem`` either way:

    >>> item = read_manifest(response.content, Config())
    >>> [(page.index, page.url, page.ocr_url) for page in item.pages]

A IIIF Collection lists manifests (and other collections); ``read_collection()`` returns one level
of it, a ``CollectionEntry`` per member:

    >>> [(entry.kind, entry.id) for entry in read_collection(response.content)]

Only the core install is needed (no CLI dependencies).
"""

import codecs
import json
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from pybookget.config import Config
from pybookget.formats.iiif import canvas_images, parse_iiif_manifest
from pybookget.formats.mets import METSParser
from pybookget.models.iiif import IIIFCanvas, label_text
from pybookget.models.mets import METS_NAMESPACES, METSDocument, METSFile, METSPage

__all__ = ["CollectionEntry", "ManifestItem", "ManifestPage", "detect_format", "read_collection", "read_manifest"]

METS_ROOT = f"{{{METS_NAMESPACES['mets']}}}mets"

# METS file groups never used for page images (thumbnails, small previews, local paths)
METS_EXCLUDED_IMAGE_GROUPS = frozenset(
    {"THUMBS", "THUMB", "THUMBNAIL", "THUMBNAILS", "MIN", "LOCAL", "TEASER", "PREVIEW"}
)


@dataclass(frozen=True)
class ManifestPage:
    """One page of an item, with the image to download and its existing OCR, if any.

    ``index`` is the page's position (from 1) among the item's pages that have an image, in
    reading order. ``id`` is the IIIF canvas id or the METS physical div ID; ``label`` the
    canvas label or the div's LABEL (else ORDERLABEL). ``fallback_url`` is tried when ``url``
    returns 404: for IIIF the image's own URL, for METS the page's file in the next image group.
    ``ocr_format`` is "alto" or "hocr", None when there is no ``ocr_url``.
    """

    index: int
    id: str | None
    label: str | None
    url: str
    fallback_url: str | None = None
    ocr_url: str | None = None
    ocr_format: str | None = None


@dataclass(frozen=True)
class ManifestItem:
    """An item (a book, a volume) as a manifest describes it.

    ``format`` is "iiif" or "mets". ``id``: the IIIF manifest id, or the MODS recordIdentifier
    (else mets@OBJID). ``label``: the IIIF label, or the MODS title ("Title : Subtitle").
    ``rights``: IIIF rights/license, or the MODS accessCondition. ``required_statement``: IIIF
    requiredStatement/attribution, or the DFG-viewer owner (dv:owner). ``identifiers``: MODS
    identifiers by type (lower case) and "recordIdentifier"; empty for IIIF. ``metadata``:
    JSON-serialisable descriptive extras (IIIF: the manifest's metadata pairs; METS: creators,
    date, publisher, place, language, extent).
    """

    format: str
    id: str | None
    label: str | None
    rights: str | None
    required_statement: str | None
    identifiers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: list[ManifestPage] = field(default_factory=list)


@dataclass(frozen=True)
class CollectionEntry:
    """One member of a IIIF Collection: its ``id`` (the URL to read it from), its ``label``, and
    its ``kind``, "manifest" or "collection" (a collection listed in the collection)."""

    id: str
    label: str | None
    kind: str


def detect_format(data: bytes | str | dict) -> str:
    """The format of a manifest: "iiif", "mets", or "iiif-collection" for a IIIF Collection.

    "iiif" for JSON (or a dict) with a IIIF Presentation context, type Manifest or sequences;
    "iiif-collection" for JSON of type Collection (v3) or sc:Collection (v2);
    "mets" for XML whose root is mets:mets, or an OAI-PMH response with a mets:mets record.

    Raises:
        ValueError: If the data is neither
    """
    return _detect(_load(data))


def read_manifest(data: bytes | str | dict, config: Config, format: str | None = None) -> ManifestItem:
    """Read a IIIF or METS manifest (``format``: "iiif", "mets", or None to detect it).

    Raises:
        ValueError: If the data cannot be read as a manifest of that format
    """
    loaded = _load(data)
    format = format or _detect(loaded)
    if format == "iiif-collection":
        raise ValueError("A IIIF Collection, not a manifest: read its members with read_collection()")
    if format == "iiif":
        if not isinstance(loaded, dict):
            raise ValueError("A IIIF manifest must be a JSON object")
        return _read_iiif(loaded, config)
    if format == "mets":
        if not isinstance(loaded, ET.Element):
            raise ValueError("A METS document must be XML")
        return _read_mets(_mets_root(loaded), config)
    raise ValueError(f"Unknown manifest format: {format!r} (expected 'iiif' or 'mets')")


# --- loading and detection ----------------------------------------------------------------


def _load(data: bytes | str | dict) -> dict | list | ET.Element:
    """JSON data as parsed by json, XML as an Element."""
    if isinstance(data, dict):
        return data
    if isinstance(data, bytes):
        start = data.removeprefix(codecs.BOM_UTF8).lstrip()[:1]
    elif isinstance(data, str):
        data = data.lstrip("﻿")
        start = data.lstrip()[:1].encode()
    else:
        # ValueError, not TypeError: read_manifest raises ValueError for anything unreadable
        raise ValueError(f"Cannot read a manifest from {type(data).__name__}")  # noqa: TRY004
    if start in (b"{", b"["):
        try:
            loaded: dict | list = json.loads(data)
            return loaded
        except ValueError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
    if start == b"<":
        try:
            return ET.fromstring(data.lstrip() if isinstance(data, str) else data)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e
    raise ValueError("Neither JSON nor XML")


def read_collection(data: bytes | str | dict) -> list[CollectionEntry]:
    """The members of a IIIF Collection (v2 or v3), one level, in their order: the manifests and
    the collections it lists (v3 ``items``; v2 ``members``, else ``collections`` then
    ``manifests``). A listed collection is an entry of kind "collection"; its members are read by
    reading it in turn.

    Raises:
        ValueError: If the data is not a IIIF Collection, or a member has no id
        NotImplementedError: For a paged collection (``first``/``next``) or a collection that
            embeds a nested collection's members, neither read yet
    """
    loaded = _load(data)
    if not isinstance(loaded, dict) or _detect(loaded) != "iiif-collection":
        raise ValueError("Not a IIIF Collection")
    if any(key in loaded for key in ("first", "next")):
        raise NotImplementedError("Paged IIIF Collections (first/next) are not read yet; read each page "
                                  "as a collection of its own")
    if "items" in loaded:
        members = [(m, None) for m in loaded["items"] or []]
    elif "members" in loaded:
        members = [(m, None) for m in loaded["members"] or []]
    else:
        members = [*((m, "collection") for m in loaded.get("collections") or []),
                   *((m, "manifest") for m in loaded.get("manifests") or [])]
    entries = []
    for member, listed_as in members:
        if isinstance(member, str):      # v2 allows bare URIs in collections and manifests
            member = {"@id": member}
        if not isinstance(member, dict):
            continue
        entry_id = member.get("id") or member.get("@id")
        if not entry_id:
            raise ValueError(f"A IIIF Collection member without an id: {member!r}"[:200])
        kind = listed_as or ("collection" if (member.get("type") or member.get("@type"))
                             in ("Collection", "sc:Collection") else "manifest")
        if kind == "collection" and any(k in member for k in ("items", "members", "collections", "manifests")):
            raise NotImplementedError(f"The IIIF Collection embeds the members of a nested collection "
                                      f"({entry_id}); nested collections are not read yet")
        entries.append(CollectionEntry(str(entry_id), label_text(member.get("label")), kind))
    return entries


def _detect(loaded: dict | list | ET.Element) -> str:
    if isinstance(loaded, dict):
        if (loaded.get("type") or loaded.get("@type")) in ("Collection", "sc:Collection"):
            return "iiif-collection"
        context = loaded.get("@context") or loaded.get("context") or ""
        contexts = context if isinstance(context, list) else [context]
        if (
            loaded.get("type") == "Manifest"
            or loaded.get("@type") == "sc:Manifest"
            or "sequences" in loaded
            or any(isinstance(c, str) and "iiif.io/api/presentation" in c for c in contexts)
        ):
            return "iiif"
        raise ValueError("JSON, but not a IIIF Presentation manifest")
    if isinstance(loaded, ET.Element):
        _mets_root(loaded)
        return "mets"
    raise ValueError("JSON, but not a IIIF Presentation manifest")


def _mets_root(root: ET.Element) -> ET.Element:
    """The mets:mets element: the root, or the one record of an OAI-PMH response."""
    if root.tag == METS_ROOT:
        return root
    records = root.findall(".//oai:record/oai:metadata/mets:mets", METS_NAMESPACES)
    if len(records) == 1:
        return records[0]
    if len(records) > 1:
        raise ValueError(f"OAI-PMH response with {len(records)} METS records, expected one")
    raise ValueError(f"XML, but neither METS nor an OAI-PMH response with METS ({root.tag})")


# --- IIIF ---------------------------------------------------------------------------------


def _read_iiif(data: dict[str, Any], config: Config) -> ManifestItem:
    kind = data.get("type") or data.get("@type")
    if kind in ("Collection", "sc:Collection"):
        raise ValueError("A IIIF collection, not a manifest")
    try:
        manifest = parse_iiif_manifest(data)
        images = canvas_images(manifest, config)
    except (AttributeError, KeyError, TypeError) as e:
        raise ValueError(f"Invalid IIIF manifest: {e}") from e

    metadata: dict[str, Any] = {}
    for pair in manifest.metadata if isinstance(manifest.metadata, list) else []:
        if not isinstance(pair, dict):
            continue
        key, value = label_text(pair.get("label")), label_text(pair.get("value"))
        if key and value:
            metadata[key] = f"{metadata[key]}; {value}" if key in metadata else value

    pages = []
    for image in images:
        ocr_url, ocr_format = _iiif_ocr(image.canvas)
        pages.append(ManifestPage(
            index=image.index,
            id=image.canvas.id or None,
            label=image.canvas.label or None,
            url=image.url,
            fallback_url=image.fallback_url,
            ocr_url=ocr_url,
            ocr_format=ocr_format,
        ))
    return ManifestItem(
        format="iiif",
        id=manifest.id or None,
        label=label_text(manifest.label),
        rights=manifest.rights or None,
        required_statement=manifest.required_statement or None,
        identifiers={},
        metadata=metadata,
        pages=pages,
    )


def _ocr_kind(entry: dict[str, Any]) -> str | None:
    """"alto" or "hocr" when a seeAlso/rendering entry links OCR of that kind (by its format
    or profile), else None."""
    profile = entry.get("profile") or ""
    profile = " ".join(map(str, profile)) if isinstance(profile, list) else str(profile)
    hints = f"{entry.get('format') or ''} {profile}".lower()
    if "alto" in hints:
        return "alto"
    if "hocr" in hints:
        return "hocr"
    return None


def _iiif_ocr(canvas: IIIFCanvas) -> tuple[str | None, str | None]:
    """The canvas's OCR link (ALTO preferred over hOCR; seeAlso before rendering)."""
    found: dict[str, str] = {}
    for entry in canvas.see_also + canvas.rendering:
        kind, url = _ocr_kind(entry), entry.get("@id") or entry.get("id")
        if kind and isinstance(url, str) and url:
            found.setdefault(kind, url)
    for kind in ("alto", "hocr"):
        if kind in found:
            return found[kind], kind
    return None, None


# --- METS ---------------------------------------------------------------------------------


def _read_mets(root: ET.Element, config: Config) -> ManifestItem:
    doc = METSParser().parse_element(root)
    mods = doc.metadata

    label = mods.title
    if label and mods.non_sort:
        separator = "" if mods.non_sort.endswith(("'", "’", "-")) else " "
        label = f"{mods.non_sort}{separator}{label}"
    if label and mods.subtitle:
        label = f"{label} : {mods.subtitle}"

    identifiers = dict(mods.identifiers)
    if mods.record_identifier:
        identifiers["recordIdentifier"] = mods.record_identifier

    metadata: dict[str, Any] = {}
    if mods.names:
        metadata["creators"] = [{"name": n.name, "role": n.role, "type": n.type} for n in mods.names]
    for key, value in (
        ("date", mods.date),
        ("publisher", mods.publisher),
        ("place", mods.place),
        ("language", list(mods.languages)),
        ("extent", mods.extent),
    ):
        if value:
            metadata[key] = value

    image_groups = _mets_image_groups(doc, config)
    ocr_groups = [g.upper() for g in config.mets_ocr_groups]
    pages: list[ManifestPage] = []
    for page in doc.pages:
        images = _mets_page_images(page, doc, image_groups)
        if not images:
            continue
        ocr = _page_file(page, doc, ocr_groups)
        ocr_format = None
        if ocr is not None:
            mimetype = ocr.mimetype.lower()
            ocr_format = "hocr" if "hocr" in mimetype or "html" in mimetype else "alto"
        fallback = images[1].href if len(images) > 1 and images[1].href != images[0].href else None
        pages.append(ManifestPage(
            index=len(pages) + 1,
            id=page.id or None,
            label=page.label or page.order_label or None,
            url=images[0].href,
            fallback_url=fallback,
            ocr_url=ocr.href if ocr is not None else None,
            ocr_format=ocr_format,
        ))

    return ManifestItem(
        format="mets",
        id=mods.record_identifier or doc.obj_id,
        label=label,
        rights=mods.license or doc.owner_license,
        required_statement=doc.owner,
        identifiers=identifiers,
        metadata=metadata,
        pages=pages,
    )


def _mets_image_groups(doc: METSDocument, config: Config) -> list[tuple[str, bool]]:
    """The image file groups by priority, as (USE, whether its files must be image/*): the
    configured groups, then the document's other groups (except thumbnails and OCR)."""
    preferred = [g.upper() for g in config.mets_image_groups]
    excluded = METS_EXCLUDED_IMAGE_GROUPS | {g.upper() for g in config.mets_ocr_groups}
    others = [
        g.upper() for g in doc.file_groups
        if g.upper() not in preferred and g.upper() not in excluded
    ]
    return [(g, False) for g in preferred] + [(g, True) for g in dict.fromkeys(others)]


def _mets_page_images(
    page: METSPage, doc: METSDocument, groups: list[tuple[str, bool]]
) -> list[METSFile]:
    """The page's image files, one per group that has one, by group priority."""
    images = []
    for group, must_be_image in groups:
        file = _page_file(page, doc, [group])
        if file is None or not file.href:
            continue
        mimetype = file.mimetype.lower()
        if mimetype.startswith("image/") or (not must_be_image and not mimetype):
            images.append(file)
    return images


def _page_file(page: METSPage, doc: METSDocument, groups: list[str]) -> METSFile | None:
    """The page's file in the first of the groups (USE, upper case) that has one."""
    for group in groups:
        for file_id in page.file_ids:
            file = doc.files.get(file_id)
            if file is not None and (file.use or "").upper() == group and file.href:
                return file
    return None
