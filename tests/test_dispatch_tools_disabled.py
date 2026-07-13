"""The main agent must not advertise background-dispatch tools.

No installed module uses subagents (enterprise_knowledge has subagent.enabled
= false; maintenance_copilot has no subagent block), and dispatching a trivial
lookup to `solve`/divide produced "job started" turns that never answered the
user. Removing these tools from the advertised schema is the reliable fix —
prompt rules alone did not hold. See normal_builder._DISABLED_TOOL_NAMES.
"""
from __future__ import annotations

from minder.core.agents.components.schemas.normal_builder import ToolSchemaBuilder


def _tool_names() -> set[str]:
    schemas = ToolSchemaBuilder(tool_registry=None).build()
    return {s["function"]["name"] for s in schemas}


def test_dispatch_tools_not_advertised() -> None:
    names = _tool_names()
    for disabled in ("solve", "get_solve_result", "spawn_subagent"):
        assert disabled not in names, f"{disabled} must not be advertised to the model"


def test_core_answering_tools_still_present() -> None:
    # Guard against over-broad disabling: the tools EK actually answers with
    # (bash for knowledge.py, file search/read) must remain.
    names = _tool_names()
    for kept in ("run_command", "search", "read_file"):
        assert kept in names, f"{kept} must remain available"
