"""Master list of built-in tool schemas used by Minder agents.

The complete schema definitions live in the :mod:`.builtin` subpackage, grouped
by domain (file, process, web, symbol, ...). They are reassembled here as
``_BUILTIN_TOOL_SCHEMAS`` for backwards-compatible imports.

Tool descriptions are loaded from markdown templates in
``minder/core/agents/prompts/templates/tools/``.
"""

from __future__ import annotations

from minder.core.agents.components.schemas.builtin import BUILTIN_TOOL_SCHEMAS

_BUILTIN_TOOL_SCHEMAS = BUILTIN_TOOL_SCHEMAS

__all__ = ["_BUILTIN_TOOL_SCHEMAS"]
