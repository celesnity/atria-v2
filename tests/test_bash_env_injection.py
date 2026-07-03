"""Bash tool injects conversation/project env vars into every subprocess."""

from __future__ import annotations

from unittest.mock import patch


def test_session_id_becomes_conversation_id_and_slug(monkeypatch):
    """When a UI callback exposes session_id=42, exec_env must include
    ATRIA_CONVERSATION_ID=42 and ATRIA_PROJECT_SLUG=conv-42."""
    from atria.core.context_engineering.tools.implementations.bash_tool import tool as bash_mod

    class _FakeCb:
        session_id = "42"

    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)
    monkeypatch.delenv("ATRIA_PROJECT_SLUG", raising=False)
    monkeypatch.delenv("ATRIA_SESSION_ID", raising=False)

    with patch.object(bash_mod, "get_current_ui_callback", return_value=_FakeCb()):
        env = bash_mod._build_exec_env(working_dir="/tmp")  # helper to be extracted

    assert env["ATRIA_CONVERSATION_ID"] == "42"
    assert env["ATRIA_PROJECT_SLUG"] == "conv-42"
    assert env["ATRIA_SESSION_ID"] == "42"


def test_no_session_means_no_conversation_vars(monkeypatch):
    """No UI callback → conversation vars must be absent (not empty strings)."""
    from atria.core.context_engineering.tools.implementations.bash_tool import tool as bash_mod

    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)
    monkeypatch.delenv("ATRIA_PROJECT_SLUG", raising=False)
    monkeypatch.delenv("ATRIA_SESSION_ID", raising=False)

    with patch.object(bash_mod, "get_current_ui_callback", return_value=None):
        env = bash_mod._build_exec_env(working_dir="/tmp")

    assert "ATRIA_CONVERSATION_ID" not in env
    assert "ATRIA_PROJECT_SLUG" not in env


def test_explicit_env_overrides_session(monkeypatch):
    """If ATRIA_CONVERSATION_ID is already set in the parent env, keep it."""
    from atria.core.context_engineering.tools.implementations.bash_tool import tool as bash_mod

    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "99")
    monkeypatch.setenv("ATRIA_PROJECT_SLUG", "conv-99")

    class _FakeCb:
        session_id = "42"

    with patch.object(bash_mod, "get_current_ui_callback", return_value=_FakeCb()):
        env = bash_mod._build_exec_env(working_dir="/tmp")

    assert env["ATRIA_CONVERSATION_ID"] == "99"
    assert env["ATRIA_PROJECT_SLUG"] == "conv-99"


def test_worker_overrides_win_without_ui_callback(monkeypatch):
    """Background worker path: no UI callback, but explicit overrides (from the
    task payload) inject the session id + workspace and win over os.environ.

    This is what lets a dispatched data_copilot subagent write into the
    conversation's session folder instead of the module fallback dir.
    """
    from atria.core.context_engineering.tools.implementations.bash_tool import tool as bash_mod

    # Simulate a worker whose process env already has a stale/wrong workspace.
    monkeypatch.setenv("ATRIA_WORKSPACE", "/modules")
    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)

    overrides = {
        "ATRIA_WORKSPACE": "/ws/conv",
        "ATRIA_SESSION_DIR": "/ws/conv",
        "ATRIA_SESSION_ID": "sess42",
        "ATRIA_CONVERSATION_ID": "sess42",
        "ATRIA_PROJECT_SLUG": "conv-sess42",
    }
    with patch.object(bash_mod, "get_current_ui_callback", return_value=None):
        env = bash_mod._build_exec_env(working_dir="/modules", overrides=overrides)

    # Overrides win unconditionally, even over a pre-existing os.environ value.
    assert env["ATRIA_WORKSPACE"] == "/ws/conv"
    assert env["ATRIA_CONVERSATION_ID"] == "sess42"
    assert env["ATRIA_SESSION_ID"] == "sess42"


def test_empty_override_values_are_ignored(monkeypatch):
    """Blank override values must not clobber real env (no-session worker)."""
    from atria.core.context_engineering.tools.implementations.bash_tool import tool as bash_mod

    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)

    with patch.object(bash_mod, "get_current_ui_callback", return_value=None):
        env = bash_mod._build_exec_env(
            working_dir="/ws", overrides={"ATRIA_WORKSPACE": "/ws", "ATRIA_CONVERSATION_ID": ""}
        )

    assert env["ATRIA_WORKSPACE"] == "/ws"
    assert "ATRIA_CONVERSATION_ID" not in env
