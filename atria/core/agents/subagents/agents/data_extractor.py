"""Data-Extractor subagent: runs planner SQL, repairs on error."""

from atria.core.agents.prompts.loader import load_prompt
from atria.core.agents.subagents.specs import SubAgentSpec

DATA_EXTRACTOR_SUBAGENT = SubAgentSpec(
    name="Data-Extractor",
    description=(
        "Materializes one sub-table inside a deep_analyze job's SQLite DB. "
        "Spawned by the deep_analyze orchestrator — not invoked directly by the main agent."
    ),
    system_prompt=load_prompt("subagents/subagent-data-extractor"),
    tools=["run_sql", "describe_table"],
)
