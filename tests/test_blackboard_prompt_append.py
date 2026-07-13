"""Blackboard lessons append to the dynamic tail instead of a full prompt rebuild."""

from minder.core.agents.main_agent.agent import MainAgent


def _make_agent_shell(stable: str, dynamic: str):
    """Build a bare agent object without running the heavy __init__."""
    agent = MainAgent.__new__(MainAgent)
    agent._system_stable = stable
    agent._system_dynamic = dynamic
    agent.system_prompt = f"{stable}\n\n{dynamic}" if dynamic else stable
    agent._blackboard_handle = object()  # opaque; render is monkeypatched
    return agent


def test_lessons_appended_to_dynamic_not_rebuilt(monkeypatch):
    import minder.core.agents.main_agent.agent as agent_mod

    monkeypatch.setattr(
        agent_mod, "render_shared_lessons_section", lambda bb: "## Shared Lessons\n- L1"
    )
    agent = _make_agent_shell("STABLE", "ENV")

    agent.apply_blackboard_lessons()

    assert agent._system_stable == "STABLE"  # prefix untouched -> cache preserved
    assert "## Shared Lessons\n- L1" in agent._system_dynamic
    assert "## Shared Lessons" in agent.system_prompt


def test_apply_is_idempotent(monkeypatch):
    import minder.core.agents.main_agent.agent as agent_mod

    monkeypatch.setattr(
        agent_mod, "render_shared_lessons_section", lambda bb: "## Shared Lessons\n- L1"
    )
    agent = _make_agent_shell("STABLE", "ENV")

    agent.apply_blackboard_lessons()
    agent.apply_blackboard_lessons()  # second call must not double-append

    assert agent._system_dynamic.count("## Shared Lessons") == 1
