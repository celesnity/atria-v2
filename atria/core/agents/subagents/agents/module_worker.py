"""Module-worker subagent: an autonomous worker operating a single module.

Generic and always-registered so background workers resolve subagent_type
"module_worker" headlessly. The per-module gateway block + the concrete task are
injected into the run prompt when a module workflow is delegated.
"""
from __future__ import annotations

from atria.core.agents.prompts.loader import load_prompt
from atria.core.agents.subagents.specs import SubAgentSpec

_FALLBACK = (
    "You are one worker in a collaborative multi-agent job operating a single "
    "module. Do ONLY your assigned subtask using the module's documented "
    "commands (run scripts with absolute paths; invoke_skill before guessing "
    "flags). Other workers share a blackboard — write short verified NOTEs about "
    "what you find/do so peers can build on it, and return a concise result "
    "summary. Your module context and subtask follow."
)

MODULE_WORKER_SUBAGENT: SubAgentSpec = {
    "name": "module_worker",
    "description": (
        "Autonomous worker for one task on a module, using the module's documented "
        "commands. Shares a blackboard with peer workers; returns a result summary."
    ),
    "system_prompt": load_prompt("subagents/subagent-module-worker", fallback=_FALLBACK),
    "tools": ["run_command", "invoke_skill", "read_file", "write_file"],
}
