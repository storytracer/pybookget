"""
e-rara.ch specific data models.

This module provides data models for e-rara.ch digital books, combining
IIIF, METS, and OCR data.
"""

from dataclasses import dataclass, field
from typing import Optional

from pybookget.models.mets import METSDocument


@dataclass
class ERaraPage:
    """Represents a page in an e-rara book with all available resources."""
    order: int
    label: str
    page_id: str  # Numeric page ID (e.g., "24224396")

    # IIIF
    iiif_image_url: Optional[str] = None
    iiif_fallback_url: Optional[str] = None

    # OCR
    alto_url: Optional[str] = None
    plain_text_url: Optional[str] = None


@dataclass
class ERaraBook:
    """
    Represents a complete e-rara book with all metadata and resources.

    Combines IIIF manifest data, METS metadata, and OCR information.
    """
    book_id: str  # e.g., "24224395"
    title: str

    # Optional metadata from METS
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    doi: Optional[str] = None
    license: Optional[str] = None

    # Pages with all resources
    pages: list[ERaraPage] = field(default_factory=list)

    # Source documents
    mets_document: Optional[METSDocument] = None


def create_erara_book_from_mets(book_id: str, mets_doc: METSDocument) -> ERaraBook:
    """
    Create an ERaraBook from a METS document.

    Args:
        book_id: The e-rara book identifier
        mets_doc: Parsed METS document

    Returns:
        ERaraBook with metadata and page structure
    """
    metadata = mets_doc.metadata

    book = ERaraBook(
        book_id=book_id,
        title=metadata.title or f"Book {book_id}",
        subtitle=metadata.subtitle,
        author=metadata.author,
        publisher=metadata.publisher,
        date=metadata.date,
        language=metadata.language,
        doi=metadata.doi,
        license=metadata.license,
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
        Modifies book.pages in place
    """
    # Match IIIF URLs to pages by order/index
    for i, page in enumerate(book.pages):
        if i < len(iiif_image_urls):
            primary_url, fallback_url = iiif_image_urls[i]
            page.iiif_image_url = primary_url
            page.iiif_fallback_url = fallback_url
