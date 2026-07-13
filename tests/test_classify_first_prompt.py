"""The composed main system prompt must instruct classify-first todo behavior."""

from pathlib import Path

from minder.core.agents.prompts.composition import create_composer

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "minder/core/agents/prompts/templates"
)


def _compose_main_prompt() -> str:
    composer = create_composer(TEMPLATES_DIR, "system/main")
    return composer.compose({"todo_tracking_enabled": True})


def test_prompt_states_2plus_distinct_actions_threshold():
    prompt = _compose_main_prompt()
    assert "2+ distinct actions" in prompt


def test_prompt_requires_classify_first():
    prompt = _compose_main_prompt()
    assert "Classify First" in prompt


def test_prompt_requires_todos_before_executing_multistep():
    prompt = _compose_main_prompt()
    lowered = prompt.lower()
    assert "before" in lowered and "write_todos" in prompt
