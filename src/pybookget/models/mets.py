"""
METS (Metadata Encoding and Transmission Standard) data models.

This module provides data models for parsing METS XML documents commonly used
by digital libraries and archives for structural metadata.
"""

from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree as ET


# METS namespace mapping
METS_NAMESPACES = {
    'mets': 'http://www.loc.gov/METS/',
    'mods': 'http://www.loc.gov/mods/v3',
    'xlink': 'http://www.w3.org/1999/xlink',
    'oai': 'http://www.openarchives.org/OAI/2.0/',
}


@dataclass
class METSFile:
    """Represents a file reference in METS."""
    id: str
    mimetype: str
    href: str
    use: Optional[str] = None  # e.g., "FULLTEXT", "DEFAULT", "THUMBS"


@dataclass
class METSPage:
    """Represents a page in METS physical structure."""
    id: str
    label: str
    order: int
    file_ids: list[str] = field(default_factory=list)


@dataclass
class METSMetadata:
    """MODS metadata extracted from METS."""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    extent: Optional[str] = None
    doi: Optional[str] = None
    license: Optional[str] = None


@dataclass
class METSDocument:
    """Represents a parsed METS document."""
    metadata: METSMetadata
    pages: list[METSPage] = field(default_factory=list)
    files: dict[str, METSFile] = field(default_factory=dict)  # file_id -> METSFile


def parse_mets_xml(xml_content: str) -> METSDocument:
    """
    Parse METS XML content into a METSDocument.

    Args:
        xml_content: Raw XML string content

    Returns:
        Parsed METSDocument with metadata, pages, and files
    """
    root = ET.fromstring(xml_content)

    # Handle OAI wrapper if present
    oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)
    if oai_record is not None:
        root = oai_record

    # Parse metadata (MODS)
    metadata = _parse_mods_metadata(root)

    # Parse file section
    files = _parse_file_section(root)

    # Parse physical structure
    pages = _parse_physical_structure(root)

    return METSDocument(
        metadata=metadata,
        pages=pages,
        files=files
    )


def _parse_mods_metadata(root: ET.Element) -> METSMetadata:
    """Extract MODS metadata from METS root."""
    metadata = METSMetadata()

    # Find MODS section
    mods = root.find('.//mods:mods', METS_NAMESPACES)
    if mods is None:
        return metadata

    # Title
    title_elem = mods.find('.//mods:titleInfo/mods:title', METS_NAMESPACES)
    if title_elem is not None and title_elem.text:
        metadata.title = title_elem.text.strip()

    # Subtitle
    subtitle_elem = mods.find('.//mods:titleInfo/mods:subTitle', METS_NAMESPACES)
    if subtitle_elem is not None and subtitle_elem.text:
        metadata.subtitle = subtitle_elem.text.strip()

    # Author
    author_elem = mods.find('.//mods:name[@type="personal"]/mods:namePart', METS_NAMESPACES)
    if author_elem is not None and author_elem.text:
        metadata.author = author_elem.text.strip()

    # Publisher
    publisher_elem = mods.find('.//mods:originInfo/mods:publisher', METS_NAMESPACES)
    if publisher_elem is not None and publisher_elem.text:
        metadata.publisher = publisher_elem.text.strip()

    # Date
    date_elem = mods.find('.//mods:originInfo/mods:dateIssued', METS_NAMESPACES)
    if date_elem is not None and date_elem.text:
        metadata.date = date_elem.text.strip()

    # Language
    lang_elem = mods.find('.//mods:language/mods:languageTerm', METS_NAMESPACES)
    if lang_elem is not None and lang_elem.text:
        metadata.language = lang_elem.text.strip()

    # Extent
    extent_elem = mods.find('.//mods:physicalDescription/mods:extent', METS_NAMESPACES)
    if extent_elem is not None and extent_elem.text:
        metadata.extent = extent_elem.text.strip()

    # DOI
    doi_elem = mods.find('.//mods:identifier[@type="doi"]', METS_NAMESPACES)
    if doi_elem is not None and doi_elem.text:
        metadata.doi = doi_elem.text.strip()

    # License
    license_elem = mods.find('.//mods:accessCondition', METS_NAMESPACES)
    if license_elem is not None and license_elem.text:
        metadata.license = license_elem.text.strip()

    return metadata


def _parse_file_section(root: ET.Element) -> dict[str, METSFile]:
    """Parse file section to extract file references."""
    files = {}

    file_sec = root.find('.//mets:fileSec', METS_NAMESPACES)
    if file_sec is None:
        return files

    for file_grp in file_sec.findall('.//mets:fileGrp', METS_NAMESPACES):
        use = file_grp.get('USE')

        for file_elem in file_grp.findall('.//mets:file', METS_NAMESPACES):
            file_id = file_elem.get('ID')
            mimetype = file_elem.get('MIMETYPE', '')

            flocat = file_elem.find('.//mets:FLocat', METS_NAMESPACES)
            if flocat is not None:
                href = flocat.get('{http://www.w3.org/1999/xlink}href', '')

                if file_id:
                    files[file_id] = METSFile(
                        id=file_id,
                        mimetype=mimetype,
                        href=href,
                        use=use
                    )

    return files


def _parse_physical_structure(root: ET.Element) -> list[METSPage]:
    """Parse physical structure map to extract page information."""
    pages = []

    phys_struct = root.find('.//mets:structMap[@TYPE="PHYSICAL"]', METS_NAMESPACES)
    if phys_struct is None:
        return pages

    for div in phys_struct.findall('.//mets:div[@TYPE="page"]', METS_NAMESPACES):
        page_id = div.get('ID', '')
        label = div.get('LABEL', '')
        order_str = div.get('ORDER', '0')

        try:
            order = int(order_str)
        except (ValueError, TypeError):
            order = 0

        # Extract file pointers
        file_ids = []
        for fptr in div.findall('.//mets:fptr', METS_NAMESPACES):
            file_id = fptr.get('FILEID')
            if file_id:
                file_ids.append(file_id)

        pages.append(METSPage(
            id=page_id,
            label=label,
            order=order,
            file_ids=file_ids
        ))

    return pages
