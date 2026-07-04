from atria.models.config import AppConfig


def test_loop_control_defaults():
    cfg = AppConfig()
    assert cfg.max_iterations_default == 25
    assert cfg.max_nudge_attempts == 3
    assert cfg.max_todo_nudges == 4
    assert cfg.completion_nudge_enabled is False
    assert cfg.explore_first_enabled is False


def test_run_loop_uses_config_for_caps_not_hardcoded():
    import inspect

    from atria.core.agents.main_agent import run_loop

    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.max_nudge_attempts" in src
    assert "self.config.max_todo_nudges" in src
    assert "self.config.max_iterations_default" in src


def test_completion_nudge_is_gated():
    import inspect

    from atria.core.agents.main_agent import run_loop

    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.completion_nudge_enabled" in src


def test_explore_first_is_gated():
    import inspect

    from atria.core.agents.main_agent import run_loop

    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.explore_first_enabled" in src


def test_run_loop_does_not_double_retry_429_503():
    import inspect

    from atria.core.agents.main_agent import run_loop

    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    # run_loop should only retry the codes http_client does NOT handle.
    assert "(500, 502, 504)" in src
    assert "(429, 500, 502, 503, 504)" not in src
