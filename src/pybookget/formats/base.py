"""
Abstract base classes for metadata format parsers and writers.

This module defines the interfaces that all format handlers must implement.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar


# Type variables for generic parsers/writers
T = TypeVar('T')  # Input type (e.g., str, dict, bytes)
R = TypeVar('R')  # Result type (e.g., parsed data model)


class MetadataParser(ABC, Generic[T, R]):
    """Abstract base class for metadata format parsers.

    Parsers convert raw metadata (XML, JSON, etc.) into structured data models.

    Type Parameters:
        T: Input type (e.g., str for XML, dict for JSON)
        R: Result type (e.g., METSDocument, IIIFManifest)

    Example:
        class IIIFParser(MetadataParser[Dict[str, Any], IIIFManifest]):
            def parse(self, data: Dict[str, Any]) -> IIIFManifest:
                # Implementation
                pass
    """

    @abstractmethod
    def parse(self, data: T) -> R:
        """Parse raw metadata into structured format.

        Args:
            data: Raw input data (format depends on parser type)

        Returns:
            Parsed and structured metadata object

        Raises:
            ValueError: If data format is invalid or cannot be parsed
        """
        pass

    @abstractmethod
    def validate(self, data: T) -> bool:
        """Validate that data conforms to expected format.

        Args:
            data: Raw input data to validate

        Returns:
            True if data is valid, False otherwise
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return human-readable name of the format (e.g., 'IIIF v2', 'METS')."""
        pass

    @property
    @abstractmethod
    def mime_types(self) -> list[str]:
        """Return supported MIME types for this format."""
        pass


class MetadataWriter(ABC, Generic[T]):
    """Abstract base class for metadata format writers.

    Writers serialize structured data into standard metadata formats.

    Type Parameters:
        T: Input data type (e.g., LibraryBook, Dict[str, Any])

    Example:
        class ROCrateWriter(MetadataWriter[LibraryBook]):
            def write(self, data: LibraryBook, output_path: Path) -> None:
                # Implementation
                pass
    """

    @abstractmethod
    def write(self, data: T, output_path: Path, **options) -> None:
        """Write structured data to file in target format.

        Args:
            data: Structured data to write
            output_path: Path where file should be written
            **options: Format-specific options

        Raises:
            IOError: If file cannot be written
            ValueError: If data cannot be serialized
        """
        pass

    @abstractmethod
    def to_string(self, data: T, **options) -> str:
        """Serialize structured data to string representation.

        Args:
            data: Structured data to serialize
            **options: Format-specific options

        Returns:
            String representation in target format

        Raises:
            ValueError: If data cannot be serialized
        """
        pass

    @abstractmethod
    def validate_output(self, data: T) -> bool:
        """Validate that data can be written in target format.

        Args:
            data: Data to validate

        Returns:
            True if data is valid for this format, False otherwise
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return human-readable name of the format (e.g., 'RO-Crate', 'Dublin Core')."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return default file extension for this format (e.g., '.json', '.xml')."""
        pass


class VersionedParser(MetadataParser[T, R]):
    """Base class for parsers that handle multiple format versions.

    Examples: IIIF (v2/v3), ALTO (v1/v2/v3/v4)
    """

    @abstractmethod
    def detect_version(self, data: T) -> Optional[str]:
        """Detect the version of the format from raw data.

        Args:
            data: Raw input data

        Returns:
            Version string (e.g., '2.1', '3.0') or None if cannot be determined
        """
        pass

    @abstractmethod
    def supported_versions(self) -> list[str]:
        """Return list of supported format versions.

        Returns:
            List of version strings (e.g., ['2.1', '3.0'])
        """
        pass
