from atria.core.agents.main_agent.agent import MainAgent


class _Stub(MainAgent):
    def __init__(self, stable, dynamic):
        self._system_stable = stable
        self._system_dynamic = dynamic


def test_compose_includes_dynamic_tail_after_stable_prefix():
    agent = _Stub("STABLE_PREFIX", "DYNAMIC_TAIL")
    composed = agent._compose_system_content()
    assert composed.startswith("STABLE_PREFIX")
    assert "DYNAMIC_TAIL" in composed
    # Stable must be an exact byte prefix so servers can prefix-cache it.
    assert composed[: len("STABLE_PREFIX")] == "STABLE_PREFIX"


def test_compose_stable_only_when_no_dynamic():
    agent = _Stub("STABLE_PREFIX", "")
    assert agent._compose_system_content() == "STABLE_PREFIX"


def test_payload_has_no_dead_system_dynamic_key():
    import inspect

    from atria.core.agents.main_agent import run_loop

    src = inspect.getsource(run_loop)
    assert "_system_dynamic" not in src, "dead _system_dynamic payload key must be removed"


def test_prompt_cache_key_absent_by_default():
    # Default config: flag off -> no prompt_cache_key added.
    from atria.models.config import AppConfig

    cfg = AppConfig()
    assert getattr(cfg, "prompt_cache_key_enabled", None) is False
