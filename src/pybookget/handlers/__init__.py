"""Site-specific download handlers.

This package contains handlers for digital libraries and cultural institutions.
Each handler implements site-specific logic for downloading content.

Available handlers:
- iiif: Universal IIIF handler for any IIIF-compliant manifest
- erara: e-rara.ch handler with IIIF, METS metadata, and OCR support
"""

# Import handlers to trigger their registration
# This ensures handlers are registered when the module is imported
from pybookget.handlers import erara, iiif

__all__ = ["iiif", "erara"]
