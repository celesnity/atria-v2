"""Built-in tool schemas: system tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from minder.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    # ===== Message Tool =====
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": load_tool_description("send_message"),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "enum": ["slack", "discord", "webhook"],
                        "description": "Channel to send to",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message content",
                    },
                    "target": {
                        "type": "string",
                        "description": "Webhook URL (overrides configured default)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown"],
                        "description": "Message format",
                        "default": "text",
                    },
                },
                "required": ["channel", "message"],
            },
        },
    },
    # ===== PDF Tool =====
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": load_tool_description("read_pdf"),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the PDF file (absolute or relative to working directory)",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]
