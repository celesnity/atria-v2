"""Tests for the enterprise_knowledge module-local model-provider config."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "modules" / "enterprise_knowledge" / "scripts" / "config.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ek_config_uut", _CONFIG_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_config_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_config_has_exactly_two_roles():
    mod = _load()
    cfg = mod.load_config(env={})
    assert set(cfg) == {"index_embed", "synthesis"}


def test_defaults_are_hosted_openai():
    mod = _load()
    cfg = mod.load_config(env={})
    assert cfg["index_embed"].base_url.endswith("/v1")
    assert "embedding" in cfg["index_embed"].model
    assert cfg["synthesis"].base_url.endswith("/v1")


def test_api_key_falls_back_to_openai_env():
    mod = _load()
    cfg = mod.load_config(env={"OPENAI_API_KEY": "sk-test-123"})
    assert cfg["index_embed"].api_key == "sk-test-123"


def test_env_overrides_win_per_role():
    mod = _load()
    env = {"EK_SYNTHESIS_BASE_URL": "https://openrouter.ai/api/v1",
           "EK_SYNTHESIS_MODEL": "qwen/qwen-2.5-72b-instruct"}
    cfg = mod.load_config(env=env)
    assert cfg["synthesis"].base_url == "https://openrouter.ai/api/v1"
    assert cfg["synthesis"].model == "qwen/qwen-2.5-72b-instruct"
    assert cfg["index_embed"].base_url != "https://openrouter.ai/api/v1"
