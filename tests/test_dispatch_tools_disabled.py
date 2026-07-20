"""The main agent must not advertise background-dispatch tools.

No installed module uses subagents (enterprise_knowledge has subagent.enabled
= false; maintenance_copilot has no subagent block), and dispatching a trivial
lookup to `solve`/divide produced "job started" turns that never answered the
user. Removing these tools from the advertised schema is the reliable fix —
prompt rules alone did not hold. See normal_builder._DISABLED_TOOL_NAMES.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from minder.core.agents.components.schemas.normal_builder import ToolSchemaBuilder
from minder.core.agents.components.prompts.builders import SystemPromptBuilder
from minder.core.agents.prompts.composition import create_composer
from minder.core.context_engineering.tools.handlers.todo_handler import TodoHandler
from minder.core.context_engineering.tools.registry_mixins.inline_tools import InlineToolsMixin


TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "minder/core/agents/prompts/templates"
)


def _tool_names() -> set[str]:
    schemas = ToolSchemaBuilder(tool_registry=None).build()
    return {s["function"]["name"] for s in schemas}


def test_dispatch_tools_not_advertised() -> None:
    names = _tool_names()
    for disabled in ("solve", "get_solve_result", "spawn_subagent", "request_help"):
        assert disabled not in names, f"{disabled} must not be advertised to the model"


def test_composed_prompts_do_not_reference_removed_dispatch_tools() -> None:
    """A model must never be instructed to call a tool absent from its schema."""
    main_prompt = create_composer(TEMPLATES_DIR, "system/main").compose(
        {"todo_tracking_enabled": True}
    )
    thinking_prompt = create_composer(TEMPLATES_DIR, "system/thinking").compose({})

    assert "request_help" not in main_prompt
    assert "request_help" not in thinking_prompt


def test_runtime_prompt_hides_disabled_todo_tools() -> None:
    """Prompt guidance must match the schema after disabled-tool filtering."""
    registry = SimpleNamespace(_handlers={"write_todos": object(), "list_todos": object()})

    prompt = SystemPromptBuilder(registry).build()

    assert "write_todos" not in prompt


def test_empty_todo_call_is_a_safe_noop() -> None:
    """Malformed optional tracking must not abort the user task."""

    class Registry(InlineToolsMixin):
        def __init__(self) -> None:
            self.todo_handler = TodoHandler()

    result = Registry()._write_todos({})

    assert result["success"] is True
    assert result["skipped"] is True


def test_core_answering_tools_still_present() -> None:
    # The agent is no longer a code/file agent: it orchestrates and answers via
    # shell. run_command must remain.
    names = _tool_names()
    assert "run_command" in names, "run_command must remain available"


# File/code tools, background-process management, apply_patch, and the blackboard
# NOTE tool were deleted from the builtin schema set entirely — they must not
# appear for ANY agent (main or subagent) nor in the settings page.
_DELETED_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "read_file",
        "list_files",
        "search",
        "apply_patch",
        "list_processes",
        "get_process_output",
        "kill_process",
        "NOTE",
    }
)


def test_deleted_tools_gone_for_all_agents() -> None:
    # allowed_tools=None (main) and an explicit list (subagent) both resolve
    # against _BUILTIN_TOOL_SCHEMAS — deletion removes them everywhere.
    main_names = _tool_names()
    assert not (_DELETED_TOOLS & main_names), "deleted tools leaked into main agent"

    sub_schemas = ToolSchemaBuilder(
        tool_registry=None, allowed_tools=list(_DELETED_TOOLS) + ["run_command"]
    ).build()
    sub_names = {s["function"]["name"] for s in sub_schemas}
    assert not (_DELETED_TOOLS & sub_names), "deleted tools resurfaced via allowed_tools"


def test_deleted_tools_absent_from_settings() -> None:
    from minder.core.agents.components.schemas.disabled_tools import all_builtin_tool_meta

    settings_names = {m["name"] for m in all_builtin_tool_meta()}
    assert not (_DELETED_TOOLS & settings_names), "deleted tools still shown in settings page"
