"""Tool for spawning subagents."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import SubAgentManager

REQUEST_HELP_TOOL_NAME = "request_help"

REQUEST_HELP_TOOL_DESCRIPTION = """Post an un-addressed request for help on the shared blackboard.

You do NOT choose who answers. Every helper agent independently decides whether it
can contribute, based on its own capabilities. Volunteers run in the background and
write their answers to a response board; you collect them with
`get_help_responses(request_id)`.

## When to Use
- You need information, analysis, or a focused change and are not sure which helper
  is best suited — describe WHAT you need and let helpers self-select.

## Available Helpers (they decide, not you)
{subagent_descriptions}

## Usage Notes
1. Put everything a helper needs in `prompt` — helpers cannot see the conversation.
2. `max_helpers` caps how many volunteers run (default 3).
3. Returns a `request_id`; poll with `get_help_responses(request_id)`.
4. Requires Redis and a running `atria-worker`. If no helper volunteers, you get an
   empty response set — plan, run code yourself, or re-request differently."""


def create_request_help_schema(manager: "SubAgentManager") -> dict[str, Any]:
    """Create the ``request_help`` tool schema (no caller-chosen routing).

    Args:
        manager: The SubAgentManager with registered subagents.

    Returns:
        OpenAI-compatible tool schema dict.
    """
    agent_configs = manager.get_agent_configs()
    lines = []
    for c in agent_configs:
        profile = getattr(c, "capability_profile", None)
        if not profile:
            continue  # builtins like ask-user are not volunteers
        lines.append(f"- **{c.name}**: {profile}")
    subagent_descriptions = "\n".join(lines) or "- (no helpers with profiles registered)"
    return {
        "type": "function",
        "function": {
            "name": REQUEST_HELP_TOOL_NAME,
            "description": REQUEST_HELP_TOOL_DESCRIPTION.format(
                subagent_descriptions=subagent_descriptions
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Full self-contained description of what you need. Helpers "
                            "cannot see the conversation."
                        ),
                    },
                    "max_helpers": {
                        "type": "integer",
                        "description": "Max volunteers to run (default 3).",
                    },
                },
                "required": ["prompt"],
            },
        },
    }


def format_task_result(result: dict[str, Any], subagent_type: str) -> str:
    """Format the task result for display.

    Args:
        result: The result from subagent execution
        subagent_type: The type of subagent that was used

    Returns:
        Formatted result string
    """
    if not result.get("success"):
        error = result.get("error", "Unknown error")
        return f"[{subagent_type}] Task failed: {error}"

    content = result.get("content", "")
    if not content:
        return f"[{subagent_type}] Task completed (no output)"

    return f"[{subagent_type}] {content}"
