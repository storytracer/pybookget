"""Site-specific download handlers.

This package contains handlers for digital libraries and cultural institutions.
Each handler implements site-specific logic for downloading content.

Currently only includes IIIF handler for any IIIF-compliant manifest.
Additional site-specific handlers can be added here as needed.
"""

# Import handlers to trigger their registration
# This ensures handlers are registered when the module is imported
from pybookget.handlers import iiif

__all__ = ["iiif"]
