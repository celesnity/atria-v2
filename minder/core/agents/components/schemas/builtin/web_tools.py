"""Built-in tool schemas: web tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from minder.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    # ===== Send Image Tool (web UI) =====
    {
        "type": "function",
        "function": {
            "name": "send_image",
            "description": (
                "Send an image to the web UI chat as a standalone image bubble. "
                "Provide either a local server-side absolute path OR a remote http(s) URL — "
                "never both, never neither. Use for screenshots, generated charts, diagrams, "
                "or any visual the user should see. Only works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute server-side path to a local image file "
                            "(PNG/JPEG/GIF/WebP/SVG, ≤10 MB)."
                        ),
                    },
                    "url": {
                        "type": "string",
                        "description": "Public http(s) URL of a remote image.",
                    },
                    "caption": {
                        "type": "string",
                        "description": "Optional caption shown below the image.",
                    },
                },
                "required": [],
            },
        },
    },
]
