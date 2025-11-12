"""
METS (Metadata Encoding and Transmission Standard) data models.

This module provides data models for METS XML documents commonly used
by digital libraries and archives for structural metadata.

For parsing METS XML, use pybookget.formats.mets.METSParser.
"""

from dataclasses import dataclass, field
from typing import Optional


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
