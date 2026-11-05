"""
METS (Metadata Encoding and Transmission Standard) format parser.

This module provides parsing capabilities for METS XML documents, commonly
used by digital libraries and archives for structural metadata.

Supports MODS metadata extraction and physical structure parsing.
"""

from xml.etree import ElementTree as ET

from pybookget.formats.base import MetadataParser
from pybookget.models.mets import (
    METS_NAMESPACES,
    METSDocument,
    METSFile,
    METSMetadata,
    METSName,
    METSPage,
)


class METSParser(MetadataParser[str, METSDocument]):
    """Parser for METS XML documents.

    This parser extracts:
    - MODS metadata (title, author, publisher, etc.)
    - File references (images, OCR files, etc.)
    - Physical structure (pages and their associated files)

    Example:
        >>> parser = METSParser()
        >>> doc = parser.parse(xml_string)
        >>> print(doc.metadata.title)
        "Example Book Title"
        >>> print(len(doc.pages))
        100
    """

    def parse(self, data: str | bytes) -> METSDocument:
        """Parse METS XML into structured data model.

        Args:
            data: Raw XML content (a METS document, or an OAI-PMH response wrapping one)

        Returns:
            METSDocument with metadata, pages, and file references

        Raises:
            ValueError: If XML is malformed or not valid METS
        """
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e
        return self.parse_element(root)

    def parse_element(self, root: ET.Element) -> METSDocument:
        """Parse an already parsed METS element (or OAI-PMH response) into a METSDocument.

        Raises:
            ValueError: If the element cannot be read as METS
        """
        try:
            # Handle OAI wrapper if present
            oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)
            if oai_record is not None:
                root = oai_record

            files, groups = self._parse_file_section(root)
            owner = root.find('.//dv:rights/dv:owner', METS_NAMESPACES)
            owner_license = root.find('.//dv:rights/dv:license', METS_NAMESPACES)

            return METSDocument(
                metadata=self._parse_mods_metadata(root),
                pages=self._parse_physical_structure(root),
                files=files,
                obj_id=root.get('OBJID') or None,
                file_groups=groups,
                owner=_text(owner),
                owner_license=_text(owner_license),
            )
        except Exception as e:
            raise ValueError(f"Failed to parse METS: {e}") from e

    def validate(self, data: str) -> bool:
        """Validate METS XML structure.

        Args:
            data: Raw XML string to validate

        Returns:
            True if valid METS XML, False otherwise
        """
        try:
            root = ET.fromstring(data)

            # Check for METS namespace
            if 'mets' not in root.tag and 'METS' not in root.tag:
                # Check if wrapped in OAI
                oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)
                if oai_record is None:
                    return False

            # Check for required METS sections
            # At minimum, should have metsHdr, fileSec, or structMap
            if root.find('.//mets:metsHdr', METS_NAMESPACES) is None:
                if root.find('.//mets:fileSec', METS_NAMESPACES) is None:
                    if root.find('.//mets:structMap', METS_NAMESPACES) is None:
                        return False

            return True
        except ET.ParseError:
            return False
        except Exception:
            return False

    @property
    def format_name(self) -> str:
        """Return format name."""
        return "METS (Metadata Encoding and Transmission Standard)"

    @property
    def mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return [
            "application/xml",
            "text/xml",
            "application/mets+xml",
        ]

    def parse_with_oai_wrapper(self, data: str | bytes) -> METSDocument:
        """Parse METS document wrapped in OAI-PMH response.

        Args:
            data: Raw OAI-PMH XML response containing METS

        Returns:
            METSDocument extracted from OAI wrapper

        Raises:
            ValueError: If not a valid OAI-PMH response with METS
        """
        try:
            root = ET.fromstring(data)
            oai_record = root.find('.//oai:record/oai:metadata/mets:mets', METS_NAMESPACES)

            if oai_record is None:
                raise ValueError("No METS document found in OAI-PMH response")

            return self.parse_element(oai_record)

        except ET.ParseError as e:
            raise ValueError(f"Invalid OAI-PMH XML: {e}") from e

    def _find_mods(self, root: ET.Element) -> ET.Element | None:
        """The item's MODS record.

        The dmdSec referenced (DMDID) by the first div of the logical structMap that has one
        (the top div; for a volume of a multi-volume work, the volume's div below the anchor),
        else the first dmdSec with MODS, else any MODS element.
        """
        dmd_secs = {sec.get('ID'): sec for sec in root.findall('mets:dmdSec', METS_NAMESPACES)}
        for struct_map in root.findall('mets:structMap', METS_NAMESPACES):
            if (struct_map.get('TYPE') or '').upper() != 'LOGICAL':
                continue
            for div in struct_map.iter(f"{{{METS_NAMESPACES['mets']}}}div"):
                for dmd_id in (div.get('DMDID') or '').split():
                    sec = dmd_secs.get(dmd_id)
                    mods = sec.find('.//mods:mods', METS_NAMESPACES) if sec is not None else None
                    if mods is not None:
                        return mods
                if div.get('DMDID'):
                    break
        for sec in dmd_secs.values():
            mods = sec.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                return mods
        return root.find('.//mods:mods', METS_NAMESPACES)

    def _parse_mods_metadata(self, root: ET.Element) -> METSMetadata:
        """Extract MODS metadata from METS root (top-level MODS elements only, not relatedItem)."""
        metadata = METSMetadata()

        mods = self._find_mods(root)
        if mods is None:
            return metadata
        ns = METS_NAMESPACES

        # Title: the main titleInfo (no type, or not an alternative/translated/... one)
        title_infos = mods.findall('mods:titleInfo', ns)
        title_info = next((t for t in title_infos if not t.get('type')), None)
        if title_info is None and title_infos:
            title_info = title_infos[0]
        if title_info is not None:
            metadata.title = _text(title_info.find('mods:title', ns))
            metadata.subtitle = _text(title_info.find('mods:subTitle', ns))
            metadata.non_sort = _text(title_info.find('mods:nonSort', ns))

        # Names and their roles
        for name_elem in mods.findall('mods:name', ns):
            name = _name_text(name_elem)
            if name:
                metadata.names.append(METSName(name, _role(name_elem), name_elem.get('type')))
        metadata.author = next((n.name for n in metadata.names if n.type == 'personal'), None)

        # Origin: the first originInfo that is not the digitisation's
        origin = next((o for o in mods.findall('mods:originInfo', ns) if not _is_digitization(o)),
                      None)
        if origin is not None:
            metadata.publisher = _join(_text(e) for e in origin.findall('mods:publisher', ns))
            metadata.date = (_date(origin.findall('mods:dateIssued', ns))
                             or _date(origin.findall('mods:dateCreated', ns)))
            places = []
            for place in origin.findall('mods:place', ns):
                terms = place.findall('mods:placeTerm', ns)
                term = next((t for t in terms if t.get('type') == 'text'), terms[0] if terms else None)
                places.append(_text(term))
            metadata.place = _join(places)

        # Languages: codes where given, else text
        for language in mods.findall('mods:language', ns):
            terms = language.findall('mods:languageTerm', ns)
            term = next((t for t in terms if t.get('type') == 'code'), terms[0] if terms else None)
            language_code = _text(term)
            if language_code and language_code not in metadata.languages:
                metadata.languages.append(language_code)
        metadata.language = metadata.languages[0] if metadata.languages else None

        metadata.extent = _join(_text(e) for e in mods.findall('mods:physicalDescription/mods:extent', ns))

        # Identifiers by type, and the record identifier
        for identifier in mods.findall('mods:identifier', ns):
            id_type, value = (identifier.get('type') or '').strip().lower(), _text(identifier)
            if id_type and value:
                metadata.identifiers.setdefault(id_type, value)
        metadata.doi = metadata.identifiers.get('doi')
        metadata.record_identifier = _text(mods.find('mods:recordInfo/mods:recordIdentifier', ns))

        metadata.license = _access_condition(mods.findall('mods:accessCondition', ns))

        return metadata

    def _parse_file_section(self, root: ET.Element) -> tuple[dict[str, METSFile], list[str]]:
        """The files of the file section by ID, and the file groups' USE in document order."""
        files: dict[str, METSFile] = {}
        groups: list[str] = []

        file_sec = root.find('.//mets:fileSec', METS_NAMESPACES)
        if file_sec is None:
            return files, groups

        for file_grp in file_sec.findall('.//mets:fileGrp', METS_NAMESPACES):
            use = file_grp.get('USE')
            if use and use not in groups:
                groups.append(use)

            for file_elem in file_grp.findall('.//mets:file', METS_NAMESPACES):
                file_id = file_elem.get('ID')
                mimetype = file_elem.get('MIMETYPE', '')

                # Prefer a URL location over others (e.g. a local path)
                flocats = file_elem.findall('mets:FLocat', METS_NAMESPACES)
                flocat = next((f for f in flocats if (f.get('LOCTYPE') or '').upper() == 'URL'),
                              flocats[0] if flocats else None)
                if flocat is not None:
                    href = flocat.get('{http://www.w3.org/1999/xlink}href', '')

                    if file_id:
                        files[file_id] = METSFile(
                            id=file_id,
                            mimetype=mimetype,
                            href=href,
                            use=use
                        )

        return files, groups

    def _parse_physical_structure(self, root: ET.Element) -> list[METSPage]:
        """The page divs of the physical structure map, sorted by ORDER if every page has one."""
        pages: list[METSPage] = []

        phys_struct = next(
            (m for m in root.findall('.//mets:structMap', METS_NAMESPACES)
             if (m.get('TYPE') or '').upper() == 'PHYSICAL'),
            None,
        )
        if phys_struct is None:
            return pages

        all_ordered = True
        for div in phys_struct.iter(f"{{{METS_NAMESPACES['mets']}}}div"):
            if (div.get('TYPE') or '').lower() != 'page':
                continue
            try:
                order = int(div.get('ORDER', ''))
            except ValueError:
                order, all_ordered = 0, False

            # File pointers: fptr/@FILEID, and areas inside fptr (also within seq/par)
            file_ids: list[str] = []
            for fptr in div.findall('mets:fptr', METS_NAMESPACES):
                ids = [fptr.get('FILEID')]
                ids += [area.get('FILEID') for area in fptr.findall('.//mets:area', METS_NAMESPACES)]
                file_ids += [i for i in ids if i and i not in file_ids]

            pages.append(METSPage(
                id=div.get('ID', ''),
                label=div.get('LABEL', ''),
                order=order,
                file_ids=file_ids,
                order_label=div.get('ORDERLABEL') or None,
            ))

        if all_ordered:
            pages.sort(key=lambda page: page.order)
        return pages


def _text(elem: ET.Element | None) -> str | None:
    """The stripped text of an element, or None."""
    if elem is None or not elem.text or not elem.text.strip():
        return None
    return elem.text.strip()


def _join(values) -> str | None:
    """The distinct non-empty values joined with "; ", or None."""
    distinct = list(dict.fromkeys(v for v in values if v))
    return "; ".join(distinct) or None


def _name_text(name: ET.Element) -> str | None:
    """A MODS name as text: displayForm, else "family, given", else the untyped nameParts."""
    ns = METS_NAMESPACES
    display = _text(name.find('mods:displayForm', ns))
    if display:
        return display
    parts: dict[str, list[str]] = {}
    for part in name.findall('mods:namePart', ns):
        text = _text(part)
        if text:
            parts.setdefault(part.get('type') or '', []).append(text)
    family, given = " ".join(parts.get('family', [])), " ".join(parts.get('given', []))
    if family or given:
        return ", ".join(p for p in (family, given) if p)
    return " ".join(parts.get('', [])) or None


def _role(name: ET.Element) -> str | None:
    """A MODS name's role: the first roleTerm code, else its text."""
    terms = name.findall('mods:role/mods:roleTerm', METS_NAMESPACES)
    term = next((t for t in terms if t.get('type') == 'code'), terms[0] if terms else None)
    return _text(term)


def _is_digitization(origin: ET.Element) -> bool:
    """Whether an originInfo describes the digitisation (DFG: eventType or "[Electronic ed.]")."""
    if (origin.get('eventType') or '').lower() == 'digitization':
        return True
    edition = _text(origin.find('mods:edition', METS_NAMESPACES)) or ''
    return 'electronic ed' in edition.lower()


def _date(dates: list[ET.Element]) -> str | None:
    """The key date of several (keyDate="yes"), else a start-end range, else the first."""
    dates = [d for d in dates if _text(d)]
    if not dates:
        return None
    key = next((d for d in dates if d.get('keyDate') == 'yes' and not d.get('point')), None)
    if key is not None:
        return _text(key)
    start = next((d for d in dates if d.get('point') == 'start'), None)
    end = next((d for d in dates if d.get('point') == 'end'), None)
    if start is not None and end is not None and _text(start) != _text(end):
        return f"{_text(start)}/{_text(end)}"
    return _text(start if start is not None else dates[0])


def _access_condition(conditions: list[ET.Element]) -> str | None:
    """The rights of MODS accessConditions: a license URI (xlink:href), else the text of the
    "use and reproduction" one, else the first text."""
    href = '{http://www.w3.org/1999/xlink}href'
    use = [c for c in conditions if (c.get('type') or '').lower() == 'use and reproduction']
    for condition in use + conditions:
        uri = (condition.get(href) or '').strip()
        if uri:
            return uri
    for condition in use + conditions:
        if _text(condition):
            return _text(condition)
    return None


class MODSExtractor:
    """Utility class for extracting MODS metadata from METS documents.

    MODS (Metadata Object Description Schema) is commonly embedded in METS
    for descriptive metadata.
    """

    @staticmethod
    def extract_title(mets_xml: str) -> str | None:
        """Extract title from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Title string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                title_elem = mods.find('.//mods:titleInfo/mods:title', METS_NAMESPACES)
                if title_elem is not None and title_elem.text:
                    return title_elem.text.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def extract_author(mets_xml: str) -> str | None:
        """Extract author from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Author string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                author_elem = mods.find(
                    './/mods:name[@type="personal"]/mods:namePart',
                    METS_NAMESPACES
                )
                if author_elem is not None and author_elem.text:
                    return author_elem.text.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def extract_date(mets_xml: str) -> str | None:
        """Extract publication date from METS/MODS.

        Args:
            mets_xml: Raw METS XML string

        Returns:
            Date string or None if not found
        """
        try:
            root = ET.fromstring(mets_xml)
            mods = root.find('.//mods:mods', METS_NAMESPACES)
            if mods is not None:
                date_elem = mods.find(
                    './/mods:originInfo/mods:dateIssued',
                    METS_NAMESPACES
                )
                if date_elem is not None and date_elem.text:
                    return date_elem.text.strip()
        except Exception:
            pass
        return None


# Convenience function for backward compatibility
def parse_mets_xml(xml_content: str) -> METSDocument:
    """Parse METS XML content into a METSDocument.

    This is a convenience function that wraps METSParser for easy use.

    Args:
        xml_content: Raw XML string content

    Returns:
        Parsed METSDocument with metadata, pages, and files

    Raises:
        ValueError: If XML is malformed or not valid METS
    """
    parser = METSParser()
    return parser.parse(xml_content)
