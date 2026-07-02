"""Tests for data_copilot module-local model config."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_defaults_use_openai_and_env_key():
    config = _load("config", "dc_config_defaults")
    cfg = config.load_config({"OPENAI_API_KEY": "sk-test"})
    assert set(cfg) == set(config.ROLES) == {"codegen", "verify", "report"}
    assert cfg["codegen"].base_url == "https://api.openai.com/v1"
    assert cfg["codegen"].model == "gpt-4o-mini"
    assert cfg["codegen"].api_key == "sk-test"


def test_env_overrides_take_precedence():
    config = _load("config", "dc_config_override")
    cfg = config.load_config(
        {
            "OPENAI_API_KEY": "sk-test",
            "DC_CODEGEN_BASE_URL": "http://localhost:8000/v1",
            "DC_CODEGEN_MODEL": "qwen2.5-coder",
            "DC_CODEGEN_API_KEY": "sk-local",
        }
    )
    assert cfg["codegen"].base_url == "http://localhost:8000/v1"
    assert cfg["codegen"].model == "qwen2.5-coder"
    assert cfg["codegen"].api_key == "sk-local"
    # verify role untouched, still falls back to OPENAI_API_KEY
    assert cfg["verify"].api_key == "sk-test"
