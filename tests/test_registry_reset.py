"""ToolRegistry.reset_per_run_state clears session-scoped mutable state."""

from minder.core.context_engineering.tools.registry import ToolRegistry


def test_reset_clears_session_scoped_state():
    reg = ToolRegistry()  # bare registry; handlers self-initialize
    reg._invoked_skills.add("some-skill")
    reg._discovered_mcp_tools.add("srv__tool")
    reg._hook_manager = object()

    reg.reset_per_run_state()

    assert reg._invoked_skills == set()
    assert reg._discovered_mcp_tools == set()
    assert reg._hook_manager is None
    # Todo store emptied (todo_handler always present).
    assert not reg.todo_handler.has_todos()
