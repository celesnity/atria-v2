"""Tool schema builder for NORMAL mode agents.

This module contains the ToolSchemaBuilder which provides full tool access
for the main agent in NORMAL mode.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Sequence, Union

from .definitions import _BUILTIN_TOOL_SCHEMAS
from .disabled_tools import DEFAULT_DISABLED_TOOLS, load_disabled_tools
from minder.core.agents.components.schemas.schema_adapter import adapt_for_provider


# Backwards-compatible alias. The disabled set is now dynamic (read per build via
# load_disabled_tools()) so the web UI can toggle tools without a restart; this
# frozenset is only the seed default used until the UI writes an explicit list.
_DISABLED_TOOL_NAMES: frozenset[str] = DEFAULT_DISABLED_TOOLS


class ToolSchemaBuilder:
    """Assemble tool schemas for NORMAL mode agents."""

    def __init__(
        self,
        tool_registry: Union[Any, None],
        allowed_tools: Union[list[str], None] = None,
        provider: Union[str, None] = None,
        extra_schemas: Union[list[dict[str, Any]], None] = None,
    ) -> None:
        """Initialize the tool schema builder.

        Args:
            tool_registry: The tool registry for MCP and task tool schemas
            allowed_tools: Optional list of allowed tool names for filtering.
                          If None, all tools are allowed. Used to restrict the
                          available tool surface (e.g. plan mode).
            provider: LLM provider name for schema adaptation (e.g., "gemini", "xai").
            extra_schemas: Additional tool schemas appended to the builtin list
                          (used by skill-owned tools).
        """
        self._tool_registry = tool_registry
        self._allowed_tools = allowed_tools
        self._provider = provider
        self._extra_schemas = extra_schemas or []
        # Assembled-schema cache. Keyed by inputs that vary at runtime so a
        # repeat call with an unchanged tool surface skips the deepcopy+assembly.
        self._cache_key: tuple | None = None
        self._cached_schemas: list[dict[str, Any]] | None = None

    def build(self, thinking_visible: bool = True) -> list[dict[str, Any]]:
        """Return tool schema definitions including MCP and task tool extensions.

        Args:
            thinking_visible: Deprecated. Kept for API compatibility but no longer
                             affects schema generation.

        Returns:
            List of tool schemas. If allowed_tools was set, only returns
            schemas for tools in that list.
        """
        # Fast path: return the cached assembly when the runtime-varying inputs
        # (MCP-discovered set + disabled set) are unchanged. Avoids a full
        # deepcopy of every builtin schema on each call_llm.
        discovered = frozenset(
            self._tool_registry.get_discovered_mcp_tools()
            if self._tool_registry and hasattr(self._tool_registry, "get_discovered_mcp_tools")
            else ()
        )
        key = (thinking_visible, discovered, frozenset(load_disabled_tools()))
        if key == self._cache_key and self._cached_schemas is not None:
            return self._cached_schemas

        # Get all builtin tool schemas plus any skill-provided extras
        schemas: list[dict[str, Any]] = deepcopy(_BUILTIN_TOOL_SCHEMAS)
        if self._extra_schemas:
            schemas.extend(deepcopy(self._extra_schemas))

        # Filter to allowed tools if specified
        if self._allowed_tools is not None:
            schemas = [
                schema for schema in schemas if schema["function"]["name"] in self._allowed_tools
            ]

        # Add MCP tool schemas (only those matching allowed_tools)
        mcp_schemas = self._build_mcp_schemas()
        if mcp_schemas:
            if self._allowed_tools is not None:
                # Filter MCP schemas to only allowed tools
                allowed_set = set(self._allowed_tools)
                mcp_schemas = [
                    schema for schema in mcp_schemas if schema["function"]["name"] in allowed_set
                ]
            schemas.extend(mcp_schemas)

        # Apply provider-specific schema adaptations
        if self._provider:
            schemas = adapt_for_provider(schemas, self._provider)

        # Drop disabled tools last, so it also strips any MCP/task/extra schemas
        # that happen to share a disabled name. Read fresh each build so web-UI
        # toggles take effect on the next LLM call without a restart.
        disabled = load_disabled_tools()
        if disabled:
            schemas = [
                schema
                for schema in schemas
                if schema.get("function", {}).get("name") not in disabled
            ]

        self._cache_key = key
        self._cached_schemas = schemas
        return schemas

    def _build_mcp_schemas(self) -> Sequence[dict[str, Any]]:
        """Build MCP tool schemas - only returns discovered tools for token efficiency.

        MCP tools are NOT loaded by default. The agent must use search_tools() to
        discover them first, which adds them to the discovered set.
        """
        if not self._tool_registry or not getattr(self._tool_registry, "mcp_manager", None):
            return []

        # Only return schemas for tools that have been "discovered" via search_tools
        discovered_tools = self._tool_registry.get_discovered_mcp_tools()
        schemas: list[dict[str, Any]] = []
        for tool in discovered_tools:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("input_schema", {}),
                    },
                }
            )
        return schemas
