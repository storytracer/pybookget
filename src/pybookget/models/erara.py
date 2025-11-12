"""
e-rara.ch specific data models.

This module provides data models for e-rara.ch digital books, combining
IIIF, METS, and OCR data.

These models extend the base library models with e-rara-specific fields.
"""

from dataclasses import dataclass, field
from typing import Optional

from pybookget.models.library import LibraryBook, LibraryMetadata, LibraryPage
from pybookget.models.mets import METSDocument


@dataclass
class ERaraMetadata(LibraryMetadata):
    """e-rara specific metadata extending base LibraryMetadata.

    Inherits Dublin Core required fields: creator, title, date
    Inherits Dublin Core optional fields from LibraryMetadata

    Additional e-rara specific fields:
        extent: Physical extent information (e.g., "265 p.")

    Note: DOI is stored in the identifier field (Dublin Core dc:identifier)
    """
    extent: Optional[str] = None  # Physical description


@dataclass
class ERaraPage(LibraryPage):
    """e-rara page extending base LibraryPage.

    Inherits all fields from LibraryPage. The page_id in e-rara
    is a numeric string (e.g., "24224396").
    """
    pass  # All functionality inherited from LibraryPage


@dataclass
class ERaraBook(LibraryBook):
    """e-rara book extending base LibraryBook.

    Additional fields:
        mets_document: Parsed METS document for advanced use cases
    """
    # Override to use ERaraMetadata type hint
    metadata: ERaraMetadata = field(default_factory=lambda: ERaraMetadata(title="unknown"))

    # Override to use ERaraPage type hint
    pages: list[ERaraPage] = field(default_factory=list)

    # e-rara specific: store original METS document
    mets_document: Optional[METSDocument] = None

    # Backwards compatibility properties
    @property
    def doi(self) -> Optional[str]:
        """Convenience property for DOI (stored in identifier field)."""
        return self.metadata.identifier

    @property
    def author(self) -> Optional[str]:
        """Convenience property for author (Dublin Core creator)."""
        return self.metadata.creator

    @property
    def date(self) -> str:
        """Convenience property for date."""
        return self.metadata.date

    @property
    def publisher(self) -> Optional[str]:
        """Convenience property for publisher."""
        return self.metadata.publisher

    @property
    def language(self) -> Optional[str]:
        """Convenience property for language."""
        return self.metadata.language

    @property
    def license(self) -> Optional[str]:
        """Convenience property for license (Dublin Core rights)."""
        return self.metadata.rights

    @property
    def subtitle(self) -> Optional[str]:
        """Convenience property for subtitle (stored in description)."""
        return self.metadata.description


def create_erara_book_from_mets(book_id: str, mets_doc: METSDocument) -> ERaraBook:
    """
    Create an ERaraBook from a METS document.

    Args:
        book_id: The e-rara book identifier
        mets_doc: Parsed METS document

    Returns:
        ERaraBook with metadata and page structure following Dublin Core
    """
    mets_metadata = mets_doc.metadata

    # Create ERaraMetadata from METS metadata following Dublin Core
    # Required fields: creator, title, date
    metadata = ERaraMetadata(
        # Required Dublin Core fields
        creator=mets_metadata.author or "Unknown",  # dc:creator (required)
        title=mets_metadata.title or f"Book {book_id}",  # dc:title (required)
        date=mets_metadata.date or "Unknown",  # dc:date (required)

        # Optional Dublin Core fields
        publisher=mets_metadata.publisher,  # dc:publisher
        identifier=mets_metadata.doi,  # dc:identifier (DOI)
        language=mets_metadata.language,  # dc:language
        rights=mets_metadata.license,  # dc:rights (license)
        description=mets_metadata.subtitle,  # dc:description (subtitle)
        type="Book",  # dc:type

        # e-rara specific
        extent=mets_metadata.extent,
    )

    # Create book with metadata
    book = ERaraBook(
        book_id=book_id,
        metadata=metadata,
        mets_document=mets_doc
    )

    # Extract pages with ALTO URLs from METS
    for mets_page in mets_doc.pages:
        # Extract numeric page ID from file references
        page_id = _extract_page_id_from_mets_page(mets_page, mets_doc.files)

        if not page_id:
            continue

        # Get ALTO URL if available
        alto_url = _get_alto_url_for_page(mets_page, mets_doc.files)

        # Generate plain text URL from ALTO URL pattern
        plain_text_url = None
        if alto_url:
            plain_text_url = alto_url.replace('/alto3/', '/plain/')

        page = ERaraPage(
            order=mets_page.order,
            label=mets_page.label,
            page_id=page_id,
            alto_url=alto_url,
            plain_text_url=plain_text_url
        )

        book.pages.append(page)

    return book


def _extract_page_id_from_mets_page(mets_page, files: dict) -> Optional[str]:
    """
    Extract numeric page ID from METS page file references.

    Args:
        mets_page: METSPage object
        files: Dictionary of file_id -> METSFile

    Returns:
        Numeric page ID string or None
    """
    # Try to extract from ALTO file ID (e.g., "ALTO24224396" -> "24224396")
    for file_id in mets_page.file_ids:
        if file_id.startswith('ALTO'):
            return file_id.replace('ALTO', '')

    # Fallback: try to extract from any file ID
    for file_id in mets_page.file_ids:
        # Extract numeric suffix
        numeric_part = ''.join(c for c in file_id if c.isdigit())
        if numeric_part:
            return numeric_part

    return None


def _get_alto_url_for_page(mets_page, files: dict) -> Optional[str]:
    """
    Get ALTO URL for a METS page.

    Args:
        mets_page: METSPage object
        files: Dictionary of file_id -> METSFile

    Returns:
        ALTO URL string or None
    """
    for file_id in mets_page.file_ids:
        if file_id.startswith('ALTO'):
            file_obj = files.get(file_id)
            if file_obj and file_obj.href:
                return file_obj.href

    return None


def add_iiif_urls_to_book(book: ERaraBook, iiif_image_urls: list[tuple[str, Optional[str]]]) -> None:
    """
    Add IIIF image URLs to book pages.

    Args:
        book: ERaraBook to update
        iiif_image_urls: List of (primary_url, fallback_url) tuples from IIIF handler

    Note:
        Modifies book.pages in place, setting image_url and image_fallback_url
    """
    # Match IIIF URLs to pages by order/index
    for i, page in enumerate(book.pages):
        if i < len(iiif_image_urls):
            primary_url, fallback_url = iiif_image_urls[i]
            page.image_url = primary_url
            page.image_fallback_url = fallback_url
