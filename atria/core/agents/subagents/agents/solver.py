"""Solver subagent: an autonomous coding-task solver that writes to the blackboard."""

from atria.core.agents.prompts.loader import load_prompt
from atria.core.agents.subagents.specs import SubAgentSpec

SOLVER_SUBAGENT = SubAgentSpec(
    name="solver",
    description=(
        "Autonomous coding solver. Takes one self-contained task, implements the "
        "smallest correct change, verifies it, and records a PATCH_SUMMARY note on "
        "the shared blackboard. USE FOR: a focused fix or change that should be "
        "implemented and verified end-to-end in an isolated context."
    ),
    system_prompt=load_prompt("subagents/subagent-solver"),
    tools=[
        "read_file",
        "search",
        "list_files",
        "find_symbol",
        "find_referencing_symbols",
        "edit_file",
        "write_file",
        "run_command",
        "NOTE",
    ],
)
