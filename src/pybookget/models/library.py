"""
Base models for library-specific handlers.

This module provides generic base classes for library handlers that support
metadata, OCR, and image downloads. These models can be extended by specific
library implementations (e-rara, Gallica, Internet Archive, etc.).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LibraryMetadata:
    """Base class for library book metadata.

    Attributes:
        title: Book title (required)
        subtitle: Book subtitle (optional)
        author: Author name(s) (optional)
        publisher: Publisher name (optional)
        date: Publication date (optional)
        language: Language code or name (optional)
        license: License information (optional)

    Subclasses can add additional metadata fields specific to their library.
    """
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    license: Optional[str] = None


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
