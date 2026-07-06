"""Tests for the enterprise_knowledge RoleClient (fake OpenAI factory)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeEmbeddings:
    def __init__(self):
        self.last_encoding_format = "UNSET"

    def create(self, model, input, encoding_format=None):
        # Record the wire format so tests can assert we request plain floats.
        # OpenAI-compatible providers (e.g. OpenRouter/NVIDIA) return float
        # arrays, not the SDK's default base64 — see client.embed().
        self.last_encoding_format = encoding_format

        class _Item:
            def __init__(self, v): self.embedding = v
        class _Resp:
            data = [_Item([float(len(t))]) for t in input]
        return _Resp()


class _FakeClient:
    instances = 0

    def __init__(self, base_url, api_key):
        _FakeClient.instances += 1
        self.base_url, self.api_key = base_url, api_key
        self.embeddings = _FakeEmbeddings()


def test_embed_dispatches_and_reuses_client_per_endpoint():
    config = _load("config", "ek_cfg_for_client")
    client = _load("client", "ek_client_uut")
    _FakeClient.instances = 0
    rc = client.RoleClient(config.load_config(env={}), client_factory=_FakeClient)
    out = rc.embed("index_embed", ["ab", "abc"])
    assert out == [[2.0], [3.0]]
    # embed() must request float arrays explicitly (not the SDK's base64 default),
    # else float-returning providers yield "No embedding data received".
    underlying = next(iter(rc._clients.values()))
    assert underlying.embeddings.last_encoding_format == "float"
    # Both roles share the same OpenAI base_url → one underlying client.
    rc.embed("synthesis", ["x"])
    assert _FakeClient.instances == 1


def test_unknown_role_raises():
    config = _load("config", "ek_cfg_for_client2")
    client = _load("client", "ek_client_uut2")
    rc = client.RoleClient(config.load_config(env={}), client_factory=_FakeClient)
    import pytest
    with pytest.raises(ValueError):
        rc.embed("nope", ["x"])
