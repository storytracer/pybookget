"""
METS (Metadata Encoding and Transmission Standard) format parser.

This module provides parsing capabilities for METS XML documents, commonly
used by digital libraries and archives for structural metadata.

Supports MODS metadata extraction and physical structure parsing.
"""

from typing import Optional
from xml.etree import ElementTree as ET

from pybookget.formats.base import MetadataParser
from pybookget.models.mets import (
    METS_NAMESPACES,
    METSDocument,
    METSFile,
    METSPage,
    METSMetadata,
)


class METSParser(MetadataParser[str, METSDocument]):
    """Parser for METS XML documents.

    This parser extracts:
    - MODS metadata (title, author, publisher, etc.)
    - File references (images, OCR files, etc.)
    - Physical structure (pages and their associated files)

    Example:
        >>> parser = METSParser()
        >>> doc = parser.parse(xml_string)
        >>> print(doc.metadata.title)
        "Example Book Title"
        >>> print(len(doc.pages))
        100
    """

    def parse(self, data: str) -> METSDocument:
        """Parse METS XML into structured data model.

        Args:
            data: Raw XML string content

        Returns:
            METSDocument with metadata, pages, and file references

        Raises:
            ValueError: If XML is malformed or not valid METS
        """
        try:
            root = ET.fromstring(data)

            # Handle OAI wrapper if present
            oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)
            if oai_record is not None:
                root = oai_record

            # Parse metadata (MODS)
            metadata = self._parse_mods_metadata(root)

            # Parse file section
            files = self._parse_file_section(root)

            # Parse physical structure
            pages = self._parse_physical_structure(root)

            return METSDocument(
                metadata=metadata,
                pages=pages,
                files=files
            )
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to parse METS: {e}") from e

    def validate(self, data: str) -> bool:
        """Validate METS XML structure.

        Args:
            data: Raw XML string to validate

        Returns:
            True if valid METS XML, False otherwise
        """
        try:
            root = ET.fromstring(data)

            # Check for METS namespace
            if 'mets' not in root.tag and 'METS' not in root.tag:
                # Check if wrapped in OAI
                oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)
                if oai_record is None:
                    return False

            # Check for required METS sections
            # At minimum, should have metsHdr, fileSec, or structMap
            if root.find('.//mets:metsHdr', METS_NAMESPACES) is None:
                if root.find('.//mets:fileSec', METS_NAMESPACES) is None:
                    if root.find('.//mets:structMap', METS_NAMESPACES) is None:
                        return False

            return True
        except ET.ParseError:
            return False
        except Exception:
            return False

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "METS (Metadata Encoding and Transmission Standard)"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return [
            "application/xml",
            "text/xml",
            "application/mets+xml",
        ]

    def parse_with_oai_wrapper(self, data: str) -> METSDocument:
        """Parse METS document wrapped in OAI-PMH response.

        Args:
            data: Raw OAI-PMH XML response containing METS

        Returns:
            METSDocument extracted from OAI wrapper

        Raises:
            ValueError: If not a valid OAI-PMH response with METS
        """
        try:
            root = ET.fromstring(data)
            oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)

            if oai_record is None:
                raise ValueError("No METS document found in OAI-PMH response")

            # Convert the METS element back to string for parsing
            mets_xml = ET.tostring(oai_record, encoding='unicode')
            return self.parse(mets_xml)

        except ET.ParseError as e:
            raise ValueError(f"Invalid OAI-PMH XML: {e}") from e

    def _parse_mods_metadata(self, root: ET.Element) -> METSMetadata:
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

    def _parse_file_section(self, root: ET.Element) -> dict[str, METSFile]:
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

    def _parse_physical_structure(self, root: ET.Element) -> list[METSPage]:
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


class MODSExtractor:
    """Utility class for extracting MODS metadata from METS documents.

    MODS (Metadata Object Description Schema) is commonly embedded in METS
    for descriptive metadata.
    """

    @staticmethod
    def extract_title(mets_xml: str) -> Optional[str]:
        """Extract title from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Title string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                title_elem = mods.find('.//mods:titleInfo/mods:title', METS_NAMESPACES)
                if title_elem is not None and title_elem.text:
                    return title_elem.text.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def extract_author(mets_xml: str) -> Optional[str]:
        """Extract author from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Author string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                author_elem = mods.find(
                    './/mods:name[@type="personal"]/mods:namePart',
                    METS_NAMESPACES
                )
                if author_elem is not None and author_elem.text:
                    return author_elem.text.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def extract_date(mets_xml: str) -> Optional[str]:
        """Extract publication date from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Date string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                date_elem = mods.find(
                    './/mods:originInfo/mods:dateIssued',
                    METS_NAMESPACES
                )
                if date_elem is not None and date_elem.text:
                    return date_elem.text.strip()
        except Exception:
            pass
        return None


# Convenience function for backward compatibility
def parse_mets_xml(xml_content: str) -> METSDocument:
    """Parse METS XML content into a METSDocument.

    This is a convenience function that wraps METSParser for easy use.

    Args:
        xml_content: Raw XML string content

    Returns:
        Parsed METSDocument with metadata, pages, and files

    Raises:
        ValueError: If XML is malformed or not valid METS
    """
    parser = METSParser()
    return parser.parse(xml_content)
