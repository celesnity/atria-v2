"""AssistantAgent: restricted toolset + assistant-first prompt (integration-built suite)."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TOOLS = {
    "run_command",
    "get_process_output",
    "kill_process",
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "search",
    "subagent",
    "invoke_skill",
    "batch_tool",
    "notebook_edit",
}


@pytest.fixture(scope="module")
def suite():
    from atria.core.runtime.config import ConfigManager
    from atria.core.runtime import ModeManager
    from atria.core.runtime.services.runtime_service import RuntimeService
    from atria.core.context_engineering.tools.implementations.file_ops import FileOperations
    from atria.core.context_engineering.tools.implementations.write_tool import WriteTool
    from atria.core.context_engineering.tools.implementations.edit_tool.tool import EditTool
    from atria.core.context_engineering.tools.implementations.bash_tool.tool import BashTool
    from atria.core.context_engineering.tools.implementations.notebook_edit_tool import (
        NotebookEditTool,
    )

    config_manager = ConfigManager(working_dir=REPO_ROOT)
    config = config_manager.get_config()
    service = RuntimeService(config_manager, ModeManager())
    return service.build_suite(
        file_ops=FileOperations(config, REPO_ROOT),
        write_tool=WriteTool(config, REPO_ROOT),
        edit_tool=EditTool(config, REPO_ROOT),
        bash_tool=BashTool(config, REPO_ROOT),
        notebook_edit_tool=NotebookEditTool(REPO_ROOT),
        ask_user_tool=None,
        mcp_manager=None,
    )


def test_suite_exposes_assistant_agent(suite):
    assert suite.agents.assistant is not None


def test_assistant_schemas_exclude_coding_tools(suite):
    names = {s["function"]["name"] for s in suite.agents.assistant.build_tool_schemas()}
    assert "knowledge_search" in names
    assert "get_user_profile" in names
    assert names & FORBIDDEN_TOOLS == set()


def test_assistant_prompt_is_assistant_first(suite):
    prompt = suite.agents.assistant.system_prompt
    assert "organization's AI assistant" in prompt
    assert "knowledge_search" in prompt  # module SKILL block included
    # the coding prompt's tool sections must not be present
    assert "run_command" not in prompt


def test_normal_agent_unchanged(suite):
    names = {s["function"]["name"] for s in suite.agents.normal.build_tool_schemas()}
    assert "run_command" in names
