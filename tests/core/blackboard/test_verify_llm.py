"""build_verify_llm resilience — the bidder LLM must survive models that reject
``temperature`` (e.g. the gpt-5 reasoning family) instead of failing every bid."""
from __future__ import annotations

import sys
import types

from minder.core.blackboard.verify_llm import build_verify_llm


class _Cfg:
    """Minimal config exposing what build_verify_llm reads."""

    def __init__(self):
        self.blackboard = types.SimpleNamespace(verify=True, verify_model="gpt-5-mini")
        self.model_critique = None
        self.model_compact = None
        self.model = "gpt-5-mini"
        self.api_base_url = "https://api.openai.com/v1"

    def get_api_key(self):
        return "sk-test"


def _install_fake_openai(monkeypatch, *, reject_temperature: bool, calls: list):
    """Install a fake ``openai`` module whose create() records kwargs and can 400
    on any non-default temperature, mimicking the gpt-5 family."""

    class _Msg:
        content = "YES 0.9 can do it"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if reject_temperature and "temperature" in kwargs:
                raise Exception(
                    "400 Unsupported value: 'temperature' does not support 0 with "
                    "this model; only the default (1) value is supported."
                )
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **_kw):
            self.chat = _Chat()

    fake = types.ModuleType("openai")
    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)


def test_verify_llm_retries_without_temperature_on_rejection(monkeypatch):
    calls: list = []
    _install_fake_openai(monkeypatch, reject_temperature=True, calls=calls)

    llm = build_verify_llm(_Cfg())
    assert llm is not None
    out = llm("system", "user")

    assert out == "YES 0.9 can do it"
    # First attempt carries temperature=0, retry drops it.
    assert len(calls) == 2
    assert calls[0].get("temperature") == 0
    assert "temperature" not in calls[1]


def test_verify_llm_keeps_temperature_when_supported(monkeypatch):
    calls: list = []
    _install_fake_openai(monkeypatch, reject_temperature=False, calls=calls)

    llm = build_verify_llm(_Cfg())
    out = llm("system", "user")

    assert out == "YES 0.9 can do it"
    # Deterministic call succeeds first try; no retry.
    assert len(calls) == 1
    assert calls[0].get("temperature") == 0
