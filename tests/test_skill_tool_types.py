import logging
from pathlib import Path

from atria.core.skill_tools import SkillToolContext, ToolSpec


def test_tool_spec_minimal():
    spec = ToolSpec(
        name="t", description="d", parameters={"type": "object"}, handler=lambda **k: {"ok": True}
    )
    assert spec.name == "t"
    assert spec.card_path is None
    assert spec.handler() == {"ok": True}


def test_tool_spec_with_card_path():
    spec = ToolSpec(
        name="t",
        description="d",
        parameters={},
        handler=lambda **k: {},
        card_path=Path("/tmp/x.md"),
    )
    assert spec.card_path == Path("/tmp/x.md")


def test_context_defaults():
    ctx = SkillToolContext()
    assert ctx.working_dir is None
    assert ctx.broadcaster is None
    assert isinstance(ctx.logger, logging.Logger)


def test_context_mutation_propagates():
    """Handler captures ctx by closure; mutating ctx.broadcaster later must be visible."""
    ctx = SkillToolContext()
    events = []

    def handler():
        if ctx.broadcaster:
            ctx.broadcaster({"hello": "world"})

    handler()
    assert events == []

    ctx.broadcaster = lambda e: events.append(e)
    handler()
    assert events == [{"hello": "world"}]
