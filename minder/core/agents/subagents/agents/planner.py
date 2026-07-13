"""Planner subagent for codebase exploration and planning.

This subagent explores the codebase, analyzes patterns, and writes
a detailed implementation plan to a designated plan file.
"""

from minder.core.agents.prompts.loader import load_prompt
from minder.core.agents.subagents.specs import SubAgentSpec
from minder.core.agents.components import PLANNING_TOOLS

PLANNER_SUBAGENT = SubAgentSpec(
    name="Planner",
    description=(
        "Codebase exploration and planning agent. Analyzes code, "
        "understands patterns, identifies relevant files, and creates detailed "
        "implementation plans. Writes the plan to a designated file path "
        "provided in the prompt."
    ),
    system_prompt=load_prompt("subagents/subagent-planner"),
    capability_profile=(
        "Explores and maps the codebase: locates definitions, traces callers, "
        "finds patterns, and reports where/how things are implemented."
    ),
    tools=list(PLANNING_TOOLS),
    model=None,  # Use default model from config
)
