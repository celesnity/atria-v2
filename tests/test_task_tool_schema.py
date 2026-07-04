"""Schema shape for the unified ``subagent`` tool."""
from __future__ import annotations

from atria.core.agents.subagents.task_tool import TASK_TOOL_NAME, create_task_tool_schema


class _FakeConfig:
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description


class _FakeManager:
    def get_agent_configs(self) -> list[_FakeConfig]:
        return [_FakeConfig("code_explorer", "Explore the codebase.")]


def test_tool_is_named_subagent() -> None:
    assert TASK_TOOL_NAME == "subagent"
    schema = create_task_tool_schema(_FakeManager())
    assert schema["function"]["name"] == "subagent"


def test_tasks_array_is_required_with_typed_items() -> None:
    schema = create_task_tool_schema(_FakeManager())
    params = schema["function"]["parameters"]
    assert params["required"] == ["tasks"]

    tasks = params["properties"]["tasks"]
    assert tasks["type"] == "array"
    item_props = tasks["items"]["properties"]
    assert set(tasks["items"]["required"]) == {"subagent_type", "prompt"}
    # subagent_type enum reflects the registered agent configs.
    assert item_props["subagent_type"]["enum"] == ["code_explorer"]


def test_no_strategy_field() -> None:
    schema = create_task_tool_schema(_FakeManager())
    props = schema["function"]["parameters"]["properties"]
    assert "strategy" not in props
