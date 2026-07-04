"""Tool for spawning subagents."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import SubAgentManager

TASK_TOOL_NAME = "subagent"

TASK_TOOL_DESCRIPTION = """Delegate one or more independent tasks to ephemeral subagents.

Each task in `tasks` runs as its own subagent on a background worker, in an
isolated context, and writes its findings back to a shared blackboard. All tasks
in one call share that blackboard, so a later wave can build on what an earlier
wave committed.

## When to Use
- Complex, self-contained work that can be handed off: research, analysis, code
  review, or a focused change
- Several independent pieces of work — pass them all at once to run concurrently
- Tasks requiring focused reasoning or heavy token usage in an isolated context

## When NOT to Use
- Simple tasks that can be completed with a few direct tool calls
- Tasks requiring intermediate feedback or clarification mid-run

## Available Subagent Types
{subagent_descriptions}

## Usage Notes
1. Put everything the subagent needs in `prompt` — it cannot see the conversation.
2. Pass multiple items in `tasks` to run them concurrently on the worker pool.
3. Tasks are independent — there is no dependency ordering. When step B needs
   step A's result, run A first, collect it with `get_subagent_output(job_id)`,
   then issue B in a new call.
4. Returns a `job_id`; use `get_subagent_output(job_id)` to poll and collect.
5. Delegation requires Redis and a running `atria-worker`."""


def create_task_tool_schema(manager: "SubAgentManager") -> dict[str, Any]:
    """Create the unified ``subagent`` tool schema with available subagent types.

    Args:
        manager: The SubAgentManager with registered subagents

    Returns:
        OpenAI-compatible tool schema dict
    """
    # Use get_agent_configs() which reads from ALL_SUBAGENTS directly
    # instead of get_available_types() which requires register_defaults() to be called first
    agent_configs = manager.get_agent_configs()

    available_types = [c.name for c in agent_configs]

    # Build subagent descriptions for tool description
    subagent_lines = []
    for config in agent_configs:
        subagent_lines.append(f"- **{config.name}**: {config.description}")

    subagent_descriptions = "\n".join(subagent_lines)

    return {
        "type": "function",
        "function": {
            "name": TASK_TOOL_NAME,
            "description": TASK_TOOL_DESCRIPTION.format(
                subagent_descriptions=subagent_descriptions
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": (
                            "One or more independent tasks to delegate. Each runs as "
                            "its own subagent on a worker; all share one blackboard so "
                            "they read each other's committed notes. A single "
                            "delegation is just a one-element list."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "subagent_type": {
                                    "type": "string",
                                    "description": "Which subagent type runs this task.",
                                    "enum": available_types,
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": (
                                        "Full self-contained instructions; the subagent "
                                        "has no access to conversation history."
                                    ),
                                },
                            },
                            "required": ["subagent_type", "prompt"],
                        },
                    },
                },
                "required": ["tasks"],
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
