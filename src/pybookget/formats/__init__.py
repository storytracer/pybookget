"""
Format parsers and writers for various metadata and manifest formats.

This module provides abstract base classes and concrete implementations for
parsing and writing different metadata formats used in digital libraries:

- IIIF Presentation API (v2/v3)
- METS (Metadata Encoding and Transmission Standard)
- ALTO (Analyzed Layout and Text Object)
- RO-Crate (Research Object Crate)

All parsers and writers are imported lazily on demand for better performance.

Usage:
    from pybookget.formats.iiif import IIIFParser
    from pybookget.formats.mets import METSParser
    from pybookget.formats.alto import ALTOParser
    from pybookget.formats.rocrate import ROCrateWriter

    parser = IIIFParser()
    manifest = parser.parse(manifest_json)
"""

from pybookget.formats.base import MetadataParser, MetadataWriter, VersionedParser

__all__ = [
    "MetadataParser",
    "MetadataWriter",
    "VersionedParser",
]
