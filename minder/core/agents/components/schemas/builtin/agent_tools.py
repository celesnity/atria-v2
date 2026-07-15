"""Built-in tool schemas: agent tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from minder.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    # apply_patch was removed — this agent does not modify files.
    # ===== Task Completion Tool =====
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": load_tool_description("task_complete"),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Summary of what was accomplished. Include key details: "
                            "file paths created/modified, URLs, ports, commands to run, "
                            "or test results. "
                            "Be specific enough that the user can act on this summary alone."
                        ),
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "partial", "failed"],
                        "description": "Completion status: 'success' if fully completed, 'partial' if some parts done, 'failed' if couldn't complete",
                        "default": "success",
                    },
                },
                "required": ["summary", "status"],
            },
        },
    },
]
