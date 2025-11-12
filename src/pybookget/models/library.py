"""
Base models for library-specific handlers.

This module provides generic base classes for library handlers that support
metadata, OCR, and image downloads. These models can be extended by specific
library implementations (e-rara, Gallica, Internet Archive, etc.).

Metadata follows Dublin Core standard with required fields: creator, title, date.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class LibraryMetadata:
    """Base class for library book metadata following Dublin Core standard.

    Required fields (Dublin Core):
        creator: Creator(s) of the resource (author, artist, etc.)
        title: Title of the resource
        date: Date of publication or creation

    Optional fields (Dublin Core):
        contributor: Additional contributors (optional)
        publisher: Publisher name (optional)
        type: Resource type (optional, e.g., "Book", "Manuscript")
        format: Media type or format (optional)
        identifier: Unique identifier (DOI, ISBN, etc.) (optional)
        source: Related resource from which this is derived (optional)
        language: Language code (ISO 639) (optional)
        relation: Related resource (optional)
        coverage: Spatial or temporal coverage (optional)
        rights: License or rights statement (optional)
        description: Description or abstract (optional)
        subject: Subject/keywords (optional)

    Subclasses can add additional metadata fields specific to their library.
    """
    # Required fields (Dublin Core)
    creator: str  # dc:creator (author, artist, etc.)
    title: str    # dc:title
    date: str     # dc:date (publication date)

    # Optional fields (Dublin Core)
    contributor: Optional[str] = None      # dc:contributor
    publisher: Optional[str] = None        # dc:publisher
    type: Optional[str] = None             # dc:type
    format: Optional[str] = None           # dc:format
    identifier: Optional[str] = None       # dc:identifier
    source: Optional[str] = None           # dc:source
    language: Optional[str] = None         # dc:language
    relation: Optional[str] = None         # dc:relation
    coverage: Optional[str] = None         # dc:coverage
    rights: Optional[str] = None           # dc:rights (license)
    description: Optional[str] = None      # dc:description
    subject: Optional[List[str]] = None    # dc:subject


@dataclass
class LibraryPage:
    """Base class for a page/canvas in a library book.

    Attributes:
        order: Page order/sequence number (1-indexed)
        label: Page label (e.g., "Page 1", "Cover", "[1]")
        page_id: Unique identifier for this page (optional)
        image_url: Primary image URL (optional)
        image_fallback_url: Fallback image URL if primary fails (optional)
        alto_url: ALTO XML OCR URL (optional)
        plain_text_url: Plain text OCR URL (optional)

    Subclasses can add additional page-specific fields.
    """
    order: int
    label: str
    page_id: Optional[str] = None

    # Image URLs
    image_url: Optional[str] = None
    image_fallback_url: Optional[str] = None

    # OCR URLs
    alto_url: Optional[str] = None
    plain_text_url: Optional[str] = None


@dataclass
class LibraryBook:
    """Base class for a complete library book.

    Attributes:
        book_id: Unique identifier for this book (required)
        metadata: Book metadata (required)
        pages: List of pages in this book

    This model combines all resources (metadata, OCR, images) for a book.
    Subclasses can add library-specific fields and methods.
    """
    book_id: str
    metadata: LibraryMetadata
    pages: list[LibraryPage] = field(default_factory=list)

    @property
    def title(self) -> str:
        """Convenience property to access book title."""
        return self.metadata.title

    @property
    def total_pages(self) -> int:
        """Get total number of pages in this book."""
        return len(self.pages)

    def get_pages_in_range(
        self,
        start: Optional[int] = None,
        end: Optional[int] = None
    ) -> list[LibraryPage]:
        """Filter pages by range.

        Args:
            start: Start page number (inclusive, 1-indexed)
            end: End page number (inclusive, 1-indexed)

        Returns:
            List of pages within the specified range
        """
        if start is None and end is None:
            return self.pages

        filtered_pages = []
        for page in self.pages:
            if start is not None and page.order < start:
                continue
            if end is not None and page.order > end:
                continue
            filtered_pages.append(page)

        return filtered_pages
