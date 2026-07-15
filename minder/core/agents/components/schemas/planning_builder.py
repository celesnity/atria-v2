"""Planning tools set for subagent tool filtering.

PLANNING_TOOLS defines the set of read-only tools used by the Planner
sub-agent spec for codebase exploration.
"""

# Read-only tools allowed for planning/exploration subagents
PLANNING_TOOLS = {
    "read_pdf",  # PDF extraction is read-only
    # Symbol tools (read-only)
    # MCP tool discovery (read-only)
    "search_tools",
    # Ask user for clarifying questions
    "ask_user",
    # Task completion (always allowed - agents must signal completion)
    "task_complete",
}
# NOTE: PLANNING_TOOLS corresponds to ToolPolicy.resolve("minimal").
# The profile system in tool_policy.py provides a more flexible way to define
# tool access levels. This set is kept for backward compatibility.
