from atria.core.agents.components.prompts.builders import SystemPromptBuilder


def test_has_subagents_false_when_no_manager():
    b = SystemPromptBuilder(tool_registry=None, subagent_manager=None)
    ctx = b._gating_context()
    assert ctx["has_subagents"] is False


def test_has_subagents_true_when_manager_present():
    b = SystemPromptBuilder(tool_registry=None, subagent_manager=object())
    ctx = b._gating_context()
    assert ctx["has_subagents"] is True
