"""Built-in tool schemas, grouped by domain.

The schemas were historically a single ~1600-line list in ``definitions.py``.
They are now split into focused modules (one ``SCHEMAS`` list each) and
reassembled here, in their original order, as ``BUILTIN_TOOL_SCHEMAS``.
"""

from __future__ import annotations

from typing import Any

from .agent_tools import SCHEMAS as _AGENT
from .file_tools import SCHEMAS as _FILE
from .interaction_tools import SCHEMAS as _INTERACTION
from .orchestration_tools import SCHEMAS as _ORCHESTRATION
from .process_tools import SCHEMAS as _PROCESS
from .system_tools import SCHEMAS as _SYSTEM
from .web_tools import SCHEMAS as _WEB

# Order preserved from the original monolithic definition.
BUILTIN_TOOL_SCHEMAS: list[dict[str, Any]] = [
    *_FILE,
    *_PROCESS,
    *_WEB,
    *_INTERACTION,
    *_SYSTEM,
    *_AGENT,
    *_ORCHESTRATION,
]

__all__ = ["BUILTIN_TOOL_SCHEMAS"]
