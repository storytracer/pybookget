"""
METS (Metadata Encoding and Transmission Standard) data models.

This module provides data models for METS XML documents commonly used
by digital libraries and archives for structural metadata.

For parsing METS XML, use pybookget.formats.mets.METSParser.
"""

from dataclasses import dataclass, field

# METS namespace mapping
METS_NAMESPACES = {
    'mets': 'http://www.loc.gov/METS/',
    'mods': 'http://www.loc.gov/mods/v3',
    'xlink': 'http://www.w3.org/1999/xlink',
    'oai': 'http://www.openarchives.org/OAI/2.0/',
    'dv': 'http://dfg-viewer.de/',
}


@dataclass
class METSFile:
    """Represents a file reference in METS."""
    id: str
    mimetype: str
    href: str
    use: str | None = None  # e.g., "FULLTEXT", "DEFAULT", "THUMBS"


@dataclass
class METSPage:
    """Represents a page in METS physical structure."""
    id: str
    label: str
    order: int  # the div's ORDER, 0 when it has none
    file_ids: list[str] = field(default_factory=list)  # fptr/@FILEID and fptr//area/@FILEID
    order_label: str | None = None  # the div's ORDERLABEL (the printed page number)


@dataclass
class METSName:
    """A MODS name: who, and in what role (a MARC relator code such as "aut", or text)."""
    name: str
    role: str | None = None
    type: str | None = None  # "personal", "corporate", ...


@dataclass
class METSMetadata:
    """MODS metadata extracted from METS."""
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None  # the first personal name
    publisher: str | None = None
    date: str | None = None  # dateIssued, else dateCreated
    language: str | None = None  # the first language
    extent: str | None = None
    doi: str | None = None
    license: str | None = None  # accessCondition: its xlink:href, else its text
    non_sort: str | None = None  # titleInfo/nonSort, e.g. "Die"
    names: list[METSName] = field(default_factory=list)
    place: str | None = None
    languages: list[str] = field(default_factory=list)
    identifiers: dict[str, str] = field(default_factory=dict)  # identifier/@type (lower case) -> text
    record_identifier: str | None = None  # recordInfo/recordIdentifier


@dataclass
class METSDocument:
    """Represents a parsed METS document; ``pages`` are in reading order."""
    metadata: METSMetadata
    pages: list[METSPage] = field(default_factory=list)
    files: dict[str, METSFile] = field(default_factory=dict)  # file_id -> METSFile
    obj_id: str | None = None  # mets/@OBJID
    file_groups: list[str] = field(default_factory=list)  # fileGrp USE values, in document order
    owner: str | None = None  # DFG-viewer rights: dv:owner
    owner_license: str | None = None  # DFG-viewer rights: dv:license
