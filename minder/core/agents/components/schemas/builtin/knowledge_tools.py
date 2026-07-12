"""Built-in tool schemas: knowledge tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from minder.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    # ===== Session Inspection Tools =====
    {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": load_tool_description("list_subagents"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
