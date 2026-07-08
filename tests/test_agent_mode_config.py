"""agent_mode config field and ATRIA_AGENT_MODE env override."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_mode_defaults_to_normal(monkeypatch):
    monkeypatch.delenv("ATRIA_AGENT_MODE", raising=False)
    from atria.core.runtime.config import ConfigManager

    config = ConfigManager(working_dir=REPO_ROOT).get_config()
    assert config.agent_mode == "normal"


def test_agent_mode_env_override(monkeypatch):
    monkeypatch.setenv("ATRIA_AGENT_MODE", "assistant")
    from atria.core.runtime.config import ConfigManager

    config = ConfigManager(working_dir=REPO_ROOT).get_config()
    assert config.agent_mode == "assistant"
