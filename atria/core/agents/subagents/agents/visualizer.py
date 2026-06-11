"""Visualizer subagent: renders one chart and streams it to the UI."""

from atria.core.agents.prompts.loader import load_prompt
from atria.core.agents.subagents.specs import SubAgentSpec

VISUALIZER_SUBAGENT = SubAgentSpec(
    name="Visualizer",
    description=(
        "Renders one chart from a deep_analyze sub-table and streams it via send_data. "
        "Spawned by the deep_analyze orchestrator — not invoked directly by the main agent."
    ),
    system_prompt=load_prompt("subagents/subagent-visualizer"),
    tools=["chart", "send_data"],
)
