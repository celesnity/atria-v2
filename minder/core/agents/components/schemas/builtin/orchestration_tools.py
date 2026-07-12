"""Built-in tool schemas: orchestration tools.

Auto-grouped from the former monolithic `definitions.py`. Each module exports a
`SCHEMAS` list of OpenAI-style function tool schema dicts.
"""

from __future__ import annotations

from typing import Any

from minder.core.agents.prompts.loader import load_tool_description

SCHEMAS: list[dict[str, Any]] = [
    # ===== Batch Tool =====
    {
        "type": "function",
        "function": {
            "name": "batch_tool",
            "description": load_tool_description("batch_tool"),
            "parameters": {
                "type": "object",
                "properties": {
                    "invocations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool": {
                                    "type": "string",
                                    "description": "Name of the tool to invoke",
                                },
                                "input": {
                                    "type": "object",
                                    "description": "Arguments to pass to the tool",
                                },
                            },
                            "required": ["tool", "input"],
                        },
                        "description": "List of tool invocations to execute",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["parallel", "serial"],
                        "description": "Execution mode: 'parallel' (concurrent) or 'serial' (sequential)",
                        "default": "parallel",
                    },
                },
                "required": ["invocations"],
            },
        },
    },
    # ===== Plan Presentation Tool =====
    {
        "type": "function",
        "function": {
            "name": "present_plan",
            "description": load_tool_description("present_plan"),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_file_path": {
                        "type": "string",
                        "description": "Absolute path to the plan file to present for approval.",
                    },
                },
                "required": ["plan_file_path"],
            },
        },
    },
]
