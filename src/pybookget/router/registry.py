"""Handler registry for manual handler selection."""

import logging
from typing import Dict, Optional, Type

from pybookget.config import Config
from pybookget.router.base import BaseHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Registry for storing available handlers by name.

    Handlers must be explicitly selected by name - no automatic URL matching.
    """

    _handlers: Dict[str, Type[BaseHandler]] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, name: str, handler_class: Type[BaseHandler]):
        """Register a handler with a given name.

        Args:
            name: Handler name (e.g., "iiif", "custom")
            handler_class: Handler class to register
        """
        cls._handlers[name] = handler_class
        logger.debug(f"Registered handler '{name}': {handler_class.__name__}")

    @classmethod
    def get_handler(
        cls,
        handler_name: str,
        url: str,
        config: Config,
    ) -> Optional[BaseHandler]:
        """Get handler by name.

        Args:
            handler_name: Name of handler to use (e.g., "iiif")
            url: URL to download from
            config: Configuration object

        Returns:
            Handler instance or None if handler not found
        """
        # Lazy initialization of handlers
        if not cls._initialized:
            cls._initialize_handlers()

        handler_class = cls._handlers.get(handler_name)
        if not handler_class:
            logger.error(f"Handler '{handler_name}' not found. Available: {list(cls._handlers.keys())}")
            return None

        return handler_class(url, config)

    @classmethod
    def _initialize_handlers(cls):
        """Initialize all handlers by importing handler modules.

        This is called lazily on first use to avoid circular imports.
        """
        if cls._initialized:
            return

        try:
            # Import all handler modules to trigger their registration
            from pybookget.handlers import (
                iiif,
                # Additional site-specific handlers can be imported here
            )
        except ImportError as e:
            logger.warning(f"Failed to import some handlers: {e}")

        cls._initialized = True
        logger.info(f"Initialized handler registry with {len(cls._handlers)} handlers")

    @classmethod
    def list_available_handlers(cls) -> list[str]:
        """List all available handler names.

        Returns:
            List of handler names
        """
        if not cls._initialized:
            cls._initialize_handlers()

        return sorted(cls._handlers.keys())


def register_handler(name: str):
    """Decorator for registering handler classes.

    Usage:
        @register_handler("iiif")
        class IIIFHandler(BaseHandler):
            ...

    Args:
        name: Handler name to register (e.g., "iiif", "custom")
    """
    def decorator(handler_class: Type[BaseHandler]):
        HandlerRegistry.register(name, handler_class)
        return handler_class
    return decorator


async def download_from_url(
    url: str,
    config: Optional[Config] = None,
    handler: str = "iiif",
) -> Optional[Dict]:
    """Download from URL using specified handler.

    This is the main entry point for library usage.

    Args:
        url: URL to download from
        config: Configuration object (creates default if None)
        handler: Handler name to use (default: "iiif")

    Returns:
        Dictionary with download results or None if failed

    Example:
        >>> import asyncio
        >>> from pybookget import download_from_url, Config
        >>> config = Config(download_dir="./books")
        >>> result = asyncio.run(download_from_url(
        ...     "https://iiif.lib.harvard.edu/manifests/...",
        ...     config,
        ...     handler="iiif"
        ... ))
        >>> print(f"Downloaded {result['downloaded']} pages")
    """
    if config is None:
        config = Config()

    # Get handler by name
    handler_instance = HandlerRegistry.get_handler(handler, url, config)

    if not handler_instance:
        logger.error(f"Handler '{handler}' not available. Use list_available_handlers() to see options.")
        return None

    # Execute download
    try:
        async with handler_instance:
            result = await handler_instance.run()
            return result
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        return None
