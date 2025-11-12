# Formats Module

The `formats` module provides a modular, extensible architecture for parsing and writing various metadata and manifest formats used in digital libraries.

## Architecture Overview

The module is organized around abstract base classes that define common interfaces for format handlers:

```
formats/
├── __init__.py           # Public API and exports
├── README.md            # This file
├── base.py              # Abstract base classes
├── iiif.py              # IIIF Presentation API parser
├── mets.py              # METS XML parser
├── alto.py              # ALTO OCR XML parser
└── rocrate.py           # RO-Crate metadata writer
```

## Design Principles

### 1. Abstract Base Classes

All parsers implement `MetadataParser[T, R]` where:
- `T` is the input type (e.g., `str` for XML, `Dict[str, Any]` for JSON)
- `R` is the result type (e.g., `METSDocument`, `IIIFManifest`)

All writers implement `MetadataWriter[T]` where:
- `T` is the input data type to be serialized

### 2. Lazy Imports

Parsers and writers are imported on-demand to minimize startup time and memory usage:

```python
# Only imports base classes initially
from pybookget.formats import MetadataParser, MetadataWriter

# Import specific parsers when needed
from pybookget.formats.iiif import IIIFParser
from pybookget.formats.mets import METSParser
```

### 3. Version Detection

Formats with multiple versions (IIIF, ALTO) extend `VersionedParser` which provides:
- Automatic version detection from raw data
- Version-specific parsing logic
- Support for multiple format versions

## Usage Examples

### Parsing IIIF Manifests

```python
from pybookget.formats.iiif import IIIFParser

parser = IIIFParser()

# Auto-detect version and parse
manifest = parser.parse(manifest_json)

# Check version
version = parser.detect_version(manifest_json)
print(f"IIIF version: {version}")  # "2.1" or "3.0"

# Validate before parsing
if parser.validate(manifest_json):
    manifest = parser.parse(manifest_json)
```

### Parsing METS Documents

```python
from pybookget.formats.mets import METSParser, MODSExtractor

parser = METSParser()

# Parse METS XML
doc = parser.parse(xml_string)
print(f"Title: {doc.metadata.title}")
print(f"Pages: {len(doc.pages)}")

# Extract specific metadata
extractor = MODSExtractor()
title = extractor.extract_title(xml_string)
author = extractor.extract_author(xml_string)
```

### Parsing ALTO OCR Files

```python
from pybookget.formats.alto import ALTOParser

parser = ALTOParser()

# Parse full ALTO document
doc = parser.parse(alto_xml)
print(f"Version: {doc.version}")
print(f"Text: {doc.get_text()}")

# Quick text extraction (faster)
text = parser.extract_text_only(alto_xml)
```

### Writing RO-Crate Metadata

```python
from pybookget.formats.rocrate import ROCrateWriter
from pybookget.models.library import LibraryBook

writer = ROCrateWriter(include_files=True)

# Write RO-Crate metadata
writer.write(
    library_book,
    output_path=Path("./output"),
    images_dir=Path("./output/images"),
    ocr_dir=Path("./output/ocr")
)

# Or get as JSON string
json_str = writer.to_string(library_book)
```

## Format Support Matrix

| Format | Parser | Writer | Versions | Auto-Detect |
|--------|--------|--------|----------|-------------|
| IIIF Presentation API | ✅ | ❌ | v2, v3 | ✅ |
| METS | ✅ | ❌ | All | ✅ |
| ALTO | ✅ | ❌ | v1-v4 | ✅ |
| RO-Crate | ❌ | ✅ | 1.1, 1.2 | N/A |

## Adding New Format Handlers

### 1. Create Parser Class

```python
from pybookget.formats.base import MetadataParser

class MyFormatParser(MetadataParser[str, MyDataModel]):
    def parse(self, data: str) -> MyDataModel:
        # Implement parsing logic
        pass

    def validate(self, data: str) -> bool:
        # Implement validation
        pass

    @property
    def format_name(self) -> str:
        return "My Format"

    @property
    def mime_types(self) -> list[str]:
        return ["application/myformat+xml"]
```

### 2. Add Version Support (Optional)

```python
from pybookget.formats.base import VersionedParser

class MyFormatParser(VersionedParser[str, MyDataModel]):
    def detect_version(self, data: str) -> Optional[str]:
        # Implement version detection
        pass

    def supported_versions(self) -> list[str]:
        return ["1.0", "2.0"]
```

### 3. Export in __init__.py

```python
# formats/__init__.py
__all__ = [
    "MetadataParser",
    "MetadataWriter",
    "MyFormatParser",
]
```

## Testing

Each format handler should have comprehensive tests:

```python
def test_parse_valid_document():
    parser = MyFormatParser()
    result = parser.parse(valid_data)
    assert result is not None

def test_validate_invalid_document():
    parser = MyFormatParser()
    assert not parser.validate(invalid_data)

def test_version_detection():
    parser = MyFormatParser()
    assert parser.detect_version(v2_data) == "2.0"
```

## Performance Considerations

### Lazy Loading

Parsers are imported only when needed:

```python
# ❌ Don't do this (imports all parsers)
from pybookget.formats import *

# ✅ Do this (imports only what you need)
from pybookget.formats.iiif import IIIFParser
```

### Efficient Parsing

Use specialized methods when you don't need full structure:

```python
# Full parsing (slower, complete structure)
doc = parser.parse(xml_data)

# Text extraction only (faster, text only)
text = parser.extract_text_only(xml_data)
```

## Dublin Core Mapping

The RO-Crate writer includes a `DublinCoreMapper` utility for mapping Dublin Core metadata to Schema.org properties:

```python
from pybookget.formats.rocrate import DublinCoreMapper

# Map individual properties
schema_prop = DublinCoreMapper.map_property("creator")  # "creator"

# Get all mappings
mappings = DublinCoreMapper.get_all_mappings()
```

### Dublin Core to Schema.org Mappings

| Dublin Core | Schema.org | Notes |
|-------------|-----------|-------|
| title | name | |
| creator | creator | Person entity |
| subject | keywords | |
| description | description | |
| publisher | publisher | Organization entity |
| contributor | contributor | Person entity |
| date | datePublished | |
| type | additionalType | Not `@type` |
| format | encodingFormat | |
| identifier | identifier | |
| source | isBasedOn | |
| language | inLanguage | ISO 639 code |
| relation | relatedLink | |
| coverage | spatialCoverage | |
| rights | license | |

## Benefits of Refactored Architecture

1. **Modularity**: Each format handler is self-contained
2. **Extensibility**: Easy to add new formats without modifying core code
3. **Testability**: Abstract interfaces make testing easier
4. **Performance**: Lazy imports reduce memory footprint
5. **Type Safety**: Generic types provide better IDE support
6. **Separation of Concerns**: Data models separate from parsing logic
7. **Reusability**: Format handlers can be used in other projects

## See Also

- [IIIF Presentation API Specification](https://iiif.io/api/presentation/)
- [METS Standard](https://www.loc.gov/standards/mets/)
- [ALTO Standard](https://www.loc.gov/standards/alto/)
- [RO-Crate Specification](https://www.researchobject.org/ro-crate/)
- [Dublin Core Metadata Initiative](https://www.dublincore.org/)
- [Schema.org Vocabulary](https://schema.org/)
