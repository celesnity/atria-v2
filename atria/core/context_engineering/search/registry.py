"""Provider registry and modules-directory discovery."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from atria.core.context_engineering.search.provider import SearchProvider

logger = logging.getLogger(__name__)


class SearchProviderRegistry:
    """Name-keyed collection of SearchProviders."""

    def __init__(self) -> None:
        self._providers: dict[str, SearchProvider] = {}

    def register(self, provider: SearchProvider) -> None:
        """Register a search provider by name.

        Args:
            provider: The SearchProvider instance to register.
        """
        self._providers[provider.name] = provider

    def get(self, name: str) -> SearchProvider | None:
        """Get a registered provider by name.

        Args:
            name: The provider name.

        Returns:
            The SearchProvider or None if not found.
        """
        return self._providers.get(name)

    def all(self) -> list[SearchProvider]:
        """Get all registered providers.

        Returns:
            List of all SearchProvider instances.
        """
        return list(self._providers.values())


def discover_module_providers(modules_root: Path) -> SearchProviderRegistry:
    """Import every modules/*/search_provider.py and register its provider.

    A module opts in by shipping a `search_provider.py` exposing
    `get_provider() -> SearchProvider`. Broken providers are logged and
    skipped; discovery never raises.

    Args:
        modules_root: Path to the modules directory root.

    Returns:
        A SearchProviderRegistry containing all successfully loaded
        providers.
    """
    registry = SearchProviderRegistry()
    if not modules_root.is_dir():
        return registry
    for provider_file in sorted(modules_root.glob("*/search_provider.py")):
        module_name = f"atria_search_providers.{provider_file.parent.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, provider_file)
            if spec is None or spec.loader is None:
                logger.warning(
                    "skipping search provider %s: could not build import spec",
                    provider_file,
                )
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            provider = module.get_provider()
            registry.register(provider)
            logger.info("registered search provider %r from %s", provider.name, provider_file)
        except Exception as exc:  # noqa: BLE001 — one bad provider must not block others
            logger.warning("skipping search provider %s: %s", provider_file, exc)
    return registry
