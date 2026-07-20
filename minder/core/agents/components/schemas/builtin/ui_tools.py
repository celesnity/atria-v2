"""Built-in schemas for direct browser UI SDK actions (no MCP transport)."""

from __future__ import annotations

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "ui_describe",
            "description": "Read the live UI SDK registry and context for modules open in the current browser session. Call this before ui_act.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ui_act",
            "description": "Invoke a live UI action registered by an open module. Use ui_describe first and only use the returned module and action names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "Module name returned by ui_describe."},
                    "action": {"type": "string", "description": "Action name returned by ui_describe."},
                    "args": {"type": "object", "description": "JSON arguments for the action.", "default": {}},
                },
                "required": ["module", "action"],
            },
        },
    },
]
