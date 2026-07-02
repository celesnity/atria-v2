"""Tests for the data_copilot role-dispatched chat client."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


class _FakeCompletions:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def create(self, model, messages, **kw):
        self.calls.append((model, messages, kw))
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.chat = type("Chat", (), {"completions": _FakeCompletions("hello")})()


def test_chat_dispatches_to_role_endpoint():
    config = _load("config", "dc_config_for_client")
    client = _load("client", "dc_client_uut")
    cfg = config.load_config({"OPENAI_API_KEY": "sk-test"})
    made = {}

    def factory(base_url, api_key):
        made["args"] = (base_url, api_key)
        return _FakeClient(base_url, api_key)

    rc = client.RoleClient(cfg, client_factory=factory)
    out = rc.chat("codegen", [{"role": "user", "content": "hi"}], temperature=0)
    assert out == "hello"
    assert made["args"] == ("https://api.openai.com/v1", "sk-test")


def test_unknown_role_raises():
    config = _load("config", "dc_config_for_client2")
    client = _load("client", "dc_client_uut2")
    rc = client.RoleClient(
        config.load_config({"OPENAI_API_KEY": "k"}), client_factory=lambda b, a: _FakeClient(b, a)
    )
    with pytest.raises(ValueError):
        rc.chat("nope", [{"role": "user", "content": "x"}])
