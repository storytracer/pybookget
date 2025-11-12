"""
ALTO (Analyzed Layout and Text Object) format parser.

ALTO is an XML schema for describing the layout and content of physical text
sources, commonly used for OCR output by digital libraries.

This parser supports ALTO versions 1-4 with automatic version detection.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from xml.etree import ElementTree as ET

from pybookget.formats.base import VersionedParser


# ALTO namespace mapping for different versions
ALTO_NAMESPACES = {
    "alto": "http://www.loc.gov/standards/alto/ns-v4#",
    "alto3": "http://www.loc.gov/standards/alto/ns-v3#",
    "alto2": "http://www.loc.gov/standards/alto/ns-v2#",
    "xlink": "http://www.w3.org/1999/xlink",
}


@dataclass
class ALTOString:
    """Represents a word/string in ALTO."""
    content: str
    confidence: Optional[float] = None
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ALTOTextLine:
    """Represents a text line in ALTO."""
    strings: List[ALTOString] = field(default_factory=list)
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def get_text(self) -> str:
        """Get concatenated text of all strings in this line.

        Returns:
            Space-separated text content
        """
        return " ".join(s.content for s in self.strings)


@dataclass
class ALTOTextBlock:
    """Represents a text block in ALTO."""
    lines: List[ALTOTextLine] = field(default_factory=list)
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def get_text(self) -> str:
        """Get concatenated text of all lines in this block.

        Returns:
            Newline-separated text content
        """
        return "\n".join(line.get_text() for line in self.lines)


@dataclass
class ALTOPage:
    """Represents a page in ALTO."""
    width: int
    height: int
    blocks: List[ALTOTextBlock] = field(default_factory=list)
    physical_img_nr: Optional[int] = None
    page_id: Optional[str] = None

    def get_text(self) -> str:
        """Get full text content of the page.

        Returns:
            Double-newline-separated text content from all blocks
        """
        return "\n\n".join(block.get_text() for block in self.blocks)


@dataclass
class ALTODocument:
    """Represents a parsed ALTO document."""
    version: Optional[str] = None
    page: Optional[ALTOPage] = None
    metadata: dict = field(default_factory=dict)

    def get_text(self) -> str:
        """Get full text content of the document.

        Returns:
            Complete text content
        """
        return self.page.get_text() if self.page else ""


class ALTOParser(VersionedParser[str, ALTODocument]):
    """Parser for ALTO XML documents.

    This parser supports ALTO versions 1-4 and automatically detects
    the version from the XML namespace.

    Example:
        >>> parser = ALTOParser()
        >>> doc = parser.parse(alto_xml)
        >>> print(doc.page.get_text())
        "Extracted text from OCR..."
        >>> print(f"Version: {doc.version}")
        Version: 4.0
    """

    def parse(self, data: str) -> ALTODocument:
        """Parse ALTO XML into structured data model.

        Args:
            data: Raw XML string content

        Returns:
            ALTODocument with layout and text information

        Raises:
            ValueError: If XML is malformed or not valid ALTO
        """
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e

        version = self.detect_version(data)
        namespace = self._get_namespace(root)

        # Parse Layout section
        layout = root.find(f".//{{{namespace}}}Layout")
        if layout is None:
            raise ValueError("No Layout section found in ALTO document")

        page = self._parse_page(layout, namespace)

        # Extract basic metadata
        metadata = self._parse_metadata(root, namespace)

        return ALTODocument(
            version=version,
            page=page,
            metadata=metadata
        )

    def validate(self, data: str) -> bool:
        """Validate ALTO XML structure.

        Args:
            data: Raw XML string to validate

        Returns:
            True if valid ALTO XML, False otherwise
        """
        try:
            root = ET.fromstring(data)

            # Check for ALTO namespace
            namespace = self._get_namespace(root)
            if not namespace or "alto" not in namespace.lower():
                return False

            # Check for required Layout section
            layout = root.find(f".//{{{namespace}}}Layout")
            return layout is not None

        except ET.ParseError:
            return False
        except Exception:
            return False

    def detect_version(self, data: str) -> Optional[str]:
        """Detect ALTO version from XML namespace.

        Args:
            data: Raw ALTO XML string

        Returns:
            Version string (e.g., '4.0', '3.0') or None if cannot be determined
        """
        try:
            root = ET.fromstring(data)
            namespace = self._get_namespace(root)

            if not namespace:
                return None

            # Extract version from namespace
            if "ns-v4" in namespace:
                return "4.0"
            elif "ns-v3" in namespace:
                return "3.0"
            elif "ns-v2" in namespace:
                return "2.0"
            elif "ns-v1" in namespace:
                return "1.0"

            return None

        except Exception:
            return None

    def supported_versions(self) -> list[str]:
        """Return list of supported ALTO versions.

        Returns:
            List of version strings
        """
        return ["1.0", "2.0", "2.1", "3.0", "3.1", "4.0", "4.1", "4.2"]

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "ALTO (Analyzed Layout and Text Object)"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return [
            "application/xml",
            "text/xml",
            "application/alto+xml",
        ]

    def extract_text_only(self, data: str) -> str:
        """Extract plain text content from ALTO XML without parsing full structure.

        This is a faster method when you only need the text content.

        Args:
            data: Raw ALTO XML string

        Returns:
            Plain text content

        Raises:
            ValueError: If XML is malformed
        """
        try:
            root = ET.fromstring(data)
            namespace = self._get_namespace(root)

            # Find all String elements and extract content
            strings = []
            for string_elem in root.findall(f".//{{{namespace}}}String"):
                content = string_elem.get("CONTENT")
                if content:
                    strings.append(content)

            return " ".join(strings)

        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e

    def _get_namespace(self, root: ET.Element) -> Optional[str]:
        """Extract namespace from root element.

        Args:
            root: Root XML element

        Returns:
            Namespace URI or None
        """
        tag = root.tag
        if tag.startswith('{'):
            return tag[1:tag.index('}')]
        return None

    def _parse_page(self, layout: ET.Element, namespace: str) -> ALTOPage:
        """Parse Page element from Layout.

        Args:
            layout: Layout XML element
            namespace: ALTO namespace URI

        Returns:
            ALTOPage object
        """
        page_elem = layout.find(f"{{{namespace}}}Page")
        if page_elem is None:
            raise ValueError("No Page element found in Layout")

        width = int(page_elem.get("WIDTH", "0"))
        height = int(page_elem.get("HEIGHT", "0"))
        physical_img_nr = page_elem.get("PHYSICAL_IMG_NR")
        page_id = page_elem.get("ID")

        # Parse print space (contains text blocks)
        print_space = page_elem.find(f"{{{namespace}}}PrintSpace")
        blocks = []

        if print_space is not None:
            for text_block_elem in print_space.findall(f"{{{namespace}}}TextBlock"):
                block = self._parse_text_block(text_block_elem, namespace)
                blocks.append(block)

        return ALTOPage(
            width=width,
            height=height,
            blocks=blocks,
            physical_img_nr=int(physical_img_nr) if physical_img_nr else None,
            page_id=page_id
        )

    def _parse_text_block(self, block_elem: ET.Element, namespace: str) -> ALTOTextBlock:
        """Parse TextBlock element.

        Args:
            block_elem: TextBlock XML element
            namespace: ALTO namespace URI

        Returns:
            ALTOTextBlock object
        """
        lines = []
        for line_elem in block_elem.findall(f"{{{namespace}}}TextLine"):
            line = self._parse_text_line(line_elem, namespace)
            lines.append(line)

        return ALTOTextBlock(
            lines=lines,
            x=int(block_elem.get("HPOS", "0")),
            y=int(block_elem.get("VPOS", "0")),
            width=int(block_elem.get("WIDTH", "0")),
            height=int(block_elem.get("HEIGHT", "0"))
        )

    def _parse_text_line(self, line_elem: ET.Element, namespace: str) -> ALTOTextLine:
        """Parse TextLine element.

        Args:
            line_elem: TextLine XML element
            namespace: ALTO namespace URI

        Returns:
            ALTOTextLine object
        """
        strings = []
        for string_elem in line_elem.findall(f"{{{namespace}}}String"):
            content = string_elem.get("CONTENT", "")
            wc = string_elem.get("WC")  # Word Confidence

            string_obj = ALTOString(
                content=content,
                confidence=float(wc) if wc else None,
                x=int(string_elem.get("HPOS", "0")),
                y=int(string_elem.get("VPOS", "0")),
                width=int(string_elem.get("WIDTH", "0")),
                height=int(string_elem.get("HEIGHT", "0"))
            )
            strings.append(string_obj)

        return ALTOTextLine(
            strings=strings,
            x=int(line_elem.get("HPOS", "0")),
            y=int(line_elem.get("VPOS", "0")),
            width=int(line_elem.get("WIDTH", "0")),
            height=int(line_elem.get("HEIGHT", "0"))
        )

    def _parse_metadata(self, root: ET.Element, namespace: str) -> dict:
        """Extract basic metadata from Description section.

        Args:
            root: Root XML element
            namespace: ALTO namespace URI

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        description = root.find(f"{{{namespace}}}Description")
        if description is not None:
            # Extract measurement unit
            measurement_unit = description.find(f"{{{namespace}}}MeasurementUnit")
            if measurement_unit is not None:
                metadata["measurement_unit"] = measurement_unit.text

            # Extract OCR processing info
            ocr_processing = description.find(f".//{{{namespace}}}OCRProcessing")
            if ocr_processing is not None:
                ocr_processing_id = ocr_processing.get("ID")
                if ocr_processing_id:
                    metadata["ocr_processing_id"] = ocr_processing_id

        return metadata


# Convenience function for backward compatibility
def parse_alto_xml(xml_content: str) -> ALTODocument:
    """Parse ALTO XML content into an ALTODocument.

    This is a convenience function that wraps ALTOParser for easy use.

    Args:
        xml_content: Raw XML string content

    Returns:
        Parsed ALTODocument with layout and text information

    Raises:
        ValueError: If XML is malformed or not valid ALTO
    """
    parser = ALTOParser()
    return parser.parse(xml_content)


def extract_text_from_alto(xml_content: str) -> str:
    """Extract plain text from ALTO XML quickly.

    Args:
        xml_content: Raw ALTO XML string

    Returns:
        Plain text content
    """
    parser = ALTOParser()
    return parser.extract_text_only(xml_content)
