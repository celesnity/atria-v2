"""agent_mode config field and MINDER_AGENT_MODE env override."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_mode_defaults_to_normal(monkeypatch):
    monkeypatch.delenv("MINDER_AGENT_MODE", raising=False)
    from minder.core.runtime.config import ConfigManager

    config = ConfigManager(working_dir=REPO_ROOT).get_config()
    assert config.agent_mode == "normal"


def test_agent_mode_env_override(monkeypatch):
    monkeypatch.setenv("MINDER_AGENT_MODE", "assistant")
    from minder.core.runtime.config import ConfigManager

    config = ConfigManager(working_dir=REPO_ROOT).get_config()
    assert config.agent_mode == "assistant"


def test_agent_mode_invalid_value_fails_closed(monkeypatch):
    monkeypatch.setenv("MINDER_AGENT_MODE", "asistant")
    from minder.core.runtime.config import ConfigManager

    import pytest as _pytest

    with _pytest.raises(Exception) as excinfo:
        ConfigManager(working_dir=REPO_ROOT).get_config()
    assert "agent_mode" in str(excinfo.value)
