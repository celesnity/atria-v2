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


def test_config_has_exactly_three_roles():
    mod = _load()
    cfg = mod.load_config(env={})
    assert set(cfg) == {"index_embed", "synthesis", "kg_extract"}


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


def test_api_key_routed_by_endpoint_host_when_both_keys_present():
    """With both keys set, each role uses the key matching its base_url host.

    A ``.env`` carrying an OpenAI key and an OpenRouter key must not send the
    OpenAI key to an OpenRouter endpoint (which would 401).
    """
    mod = _load()
    env = {
        "OPENAI_API_KEY": "sk-openai",
        "OPENROUTER_API_KEY": "sk-or-router",
        "EK_INDEX_EMBED_BASE_URL": "https://openrouter.ai/api/v1",
        "EK_SYNTHESIS_BASE_URL": "https://openrouter.ai/api/v1",
    }
    cfg = mod.load_config(env=env)
    assert cfg["index_embed"].api_key == "sk-or-router"
    assert cfg["synthesis"].api_key == "sk-or-router"
    # An OpenAI-hosted role (default base_url) still uses the OpenAI key.
    cfg_openai = mod.load_config(env={k: v for k, v in env.items()
                                      if not k.startswith("EK_")})
    assert cfg_openai["index_embed"].api_key == "sk-openai"


def test_explicit_role_api_key_overrides_routing():
    mod = _load()
    env = {"OPENROUTER_API_KEY": "sk-or-router",
           "EK_SYNTHESIS_BASE_URL": "https://openrouter.ai/api/v1",
           "EK_SYNTHESIS_API_KEY": "sk-explicit"}
    cfg = mod.load_config(env=env)
    assert cfg["synthesis"].api_key == "sk-explicit"


def test_kg_extract_role_present_and_overridable():
    mod = _load()
    cfg = mod.load_config(env={
        "EK_KG_EXTRACT_MODEL": "openai/gpt-4o-mini",
        "EK_KG_EXTRACT_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY": "sk-or-x",
    })
    assert "kg_extract" in cfg
    assert cfg["kg_extract"].model == "openai/gpt-4o-mini"
    assert cfg["kg_extract"].base_url == "https://openrouter.ai/api/v1"
    assert cfg["kg_extract"].api_key == "sk-or-x"  # host-matched fallback key
