"""
RO-Crate (Research Object Crate) metadata writer.

This module provides writing capabilities for RO-Crate metadata files,
conforming to the RO-Crate 1.1/1.2 specification.

RO-Crate is a community effort to establish a lightweight approach to
packaging research data with their metadata.
"""

import json
from pathlib import Path
from typing import List, Optional

from rocrate.model.contextentity import ContextEntity
from rocrate.model.person import Person
from rocrate.rocrate import ROCrate

from pybookget.formats.base import MetadataWriter
from pybookget.models.library import LibraryBook


class ROCrateWriter(MetadataWriter[LibraryBook]):
    """Writer for RO-Crate metadata files.

    This writer creates RO-Crate metadata from LibraryBook objects,
    following the RO-Crate specification and mapping Dublin Core
    metadata to Schema.org properties.

    The RO-Crate includes:
    - Root dataset with book metadata (Dublin Core)
    - Person entities for creators/contributors
    - Organization entities for publishers
    - hasPart relationships to images and OCR files

    Example:
        >>> writer = ROCrateWriter()
        >>> writer.write(library_book, output_dir)
        # Creates output_dir/ro-crate-metadata.json
    """

    def __init__(self, include_files: bool = True):
        """Initialize RO-Crate writer.

        Args:
            include_files: Whether to include hasPart relationships for files
        """
        self.include_files = include_files

    def write(
        self,
        data: LibraryBook,
        output_path: Path,
        images_dir: Optional[Path] = None,
        ocr_dir: Optional[Path] = None,
        **options
    ) -> None:
        """Write LibraryBook as RO-Crate metadata to file.

        Args:
            data: LibraryBook object to serialize
            output_path: Directory where ro-crate-metadata.json should be written
            images_dir: Optional path to images directory (for hasPart)
            ocr_dir: Optional path to OCR directory (for hasPart)
            **options: Additional options (unused)

        Raises:
            IOError: If file cannot be written
            ValueError: If data is invalid
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create RO-Crate
        crate = self._create_crate(data, output_path, images_dir, ocr_dir)

        # Write to file
        crate.metadata.write(output_path)

    def to_string(self, data: LibraryBook, **options) -> str:
        """Serialize LibraryBook to RO-Crate JSON string.

        Args:
            data: LibraryBook object to serialize
            **options: Additional options (unused)

        Returns:
            JSON string representation of RO-Crate

        Raises:
            ValueError: If data cannot be serialized
        """
        # Create a temporary crate
        crate = self._create_crate(data, None, None, None)

        # Extract the JSON-LD graph
        graph = crate.metadata._jsonld.get("@graph", [])
        rocrate_dict = {
            "@context": crate.metadata._jsonld.get("@context"),
            "@graph": graph
        }

        return json.dumps(rocrate_dict, indent=2, ensure_ascii=False)

    def validate_output(self, data: LibraryBook) -> bool:
        """Validate that LibraryBook can be written as RO-Crate.

        Args:
            data: LibraryBook to validate

        Returns:
            True if data is valid for RO-Crate, False otherwise
        """
        if not isinstance(data, LibraryBook):
            return False

        # Check required fields
        metadata = data.metadata
        if not metadata.title or not metadata.creator or not metadata.date:
            return False

        return True

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "RO-Crate"

    @property
    def file_extension(self) -> str:
        """Return file extension."""
        return ".json"

    def _create_crate(
        self,
        data: LibraryBook,
        base_path: Optional[Path],
        images_dir: Optional[Path],
        ocr_dir: Optional[Path]
    ) -> ROCrate:
        """Create ROCrate object from LibraryBook.

        Args:
            data: LibraryBook to convert
            base_path: Base path for resolving relative file paths
            images_dir: Path to images directory
            ocr_dir: Path to OCR directory

        Returns:
            ROCrate object
        """
        crate = ROCrate()
        root = crate.root_dataset
        metadata = data.metadata

        # Required Dublin Core fields
        root["name"] = metadata.title  # dc:title
        root["datePublished"] = metadata.date  # dc:date

        # Creator (dc:creator) - create Person entity
        creator = Person(crate, identifier=f"#{metadata.creator.replace(' ', '_')}")
        creator["name"] = metadata.creator
        crate.add(creator)
        root["creator"] = creator

        # Optional Dublin Core fields
        if metadata.contributor:
            contributor = Person(
                crate,
                identifier=f"#{metadata.contributor.replace(' ', '_')}_contributor"
            )
            contributor["name"] = metadata.contributor
            crate.add(contributor)
            root["contributor"] = contributor

        if metadata.publisher:
            publisher = ContextEntity(
                crate,
                identifier=f"#{metadata.publisher.replace(' ', '_')}",
                properties={
                    "@type": "Organization",
                    "name": metadata.publisher
                }
            )
            crate.add(publisher)
            root["publisher"] = publisher

        if metadata.type:
            root["additionalType"] = metadata.type  # dc:type -> Schema.org additionalType

        if metadata.format:
            root["encodingFormat"] = metadata.format  # dc:format

        if metadata.identifier:
            root["identifier"] = metadata.identifier  # dc:identifier

        if metadata.source:
            root["isBasedOn"] = metadata.source  # dc:source

        if metadata.language:
            root["inLanguage"] = metadata.language  # dc:language

        if metadata.relation:
            root["relatedLink"] = metadata.relation  # dc:relation

        if metadata.coverage:
            root["spatialCoverage"] = metadata.coverage  # dc:coverage

        if metadata.rights:
            root["license"] = metadata.rights  # dc:rights

        if metadata.description:
            root["description"] = metadata.description  # dc:description

        if metadata.subject:
            root["keywords"] = metadata.subject  # dc:subject

        # Add book-specific metadata
        root["numberOfPages"] = data.total_pages
        root["bookId"] = data.book_id

        # Add hasPart relationships to images and OCR files
        if self.include_files and base_path:
            parts = self._collect_file_parts(base_path, images_dir, ocr_dir)
            if parts:
                root["hasPart"] = [{"@id": part} for part in parts]

        return crate

    def _collect_file_parts(
        self,
        base_path: Path,
        images_dir: Optional[Path],
        ocr_dir: Optional[Path]
    ) -> List[str]:
        """Collect file paths for hasPart relationships.

        Args:
            base_path: Base directory for relative path calculation
            images_dir: Images directory path
            ocr_dir: OCR directory path

        Returns:
            List of relative file paths
        """
        parts = []

        # Add image files
        if images_dir and images_dir.exists():
            for img_file in sorted(images_dir.glob("*")):
                if img_file.is_file():
                    rel_path = img_file.relative_to(base_path)
                    parts.append(str(rel_path))

        # Add OCR files
        if ocr_dir and ocr_dir.exists():
            for ocr_file in sorted(ocr_dir.rglob("*")):
                if ocr_file.is_file():
                    rel_path = ocr_file.relative_to(base_path)
                    parts.append(str(rel_path))

        return parts


class DublinCoreMapper:
    """Utility class for mapping Dublin Core metadata to Schema.org/RO-Crate.

    Dublin Core is a widely-used metadata standard, and RO-Crate uses
    Schema.org vocabulary. This mapper provides the canonical mappings.
    """

    # Dublin Core to Schema.org property mappings
    MAPPINGS = {
        "title": "name",
        "creator": "creator",
        "subject": "keywords",
        "description": "description",
        "publisher": "publisher",
        "contributor": "contributor",
        "date": "datePublished",
        "type": "additionalType",
        "format": "encodingFormat",
        "identifier": "identifier",
        "source": "isBasedOn",
        "language": "inLanguage",
        "relation": "relatedLink",
        "coverage": "spatialCoverage",
        "rights": "license",
    }

    @classmethod
    def map_property(cls, dc_property: str) -> str:
        """Map Dublin Core property to Schema.org property.

        Args:
            dc_property: Dublin Core property name

        Returns:
            Schema.org property name

        Raises:
            KeyError: If property has no mapping
        """
        return cls.MAPPINGS[dc_property]

    @classmethod
    def get_all_mappings(cls) -> dict:
        """Get all Dublin Core to Schema.org mappings.

        Returns:
            Dictionary of mappings
        """
        return cls.MAPPINGS.copy()


# Convenience function for quick usage
def write_rocrate_metadata(
    book: LibraryBook,
    output_dir: Path,
    images_dir: Optional[Path] = None,
    ocr_dir: Optional[Path] = None
) -> None:
    """Write RO-Crate metadata for a LibraryBook.

    This is a convenience function that wraps ROCrateWriter for easy use.

    Args:
        book: LibraryBook object to serialize
        output_dir: Directory where ro-crate-metadata.json should be written
        images_dir: Optional path to images directory
        ocr_dir: Optional path to OCR directory
    """
    writer = ROCrateWriter()
    writer.write(book, output_dir, images_dir=images_dir, ocr_dir=ocr_dir)
