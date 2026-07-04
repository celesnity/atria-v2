"""Tests for context-window budgeting: output caps + input trimming."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_output_tokens_and_ctx_from_env(monkeypatch):
    bud = _load("budget", "mc_budget_uut")
    monkeypatch.setenv("MC_MODEL_CTX", "30000")
    monkeypatch.setenv("MC_SYNTHESIS_MAX_OUTPUT_TOKENS", "800")
    assert bud.model_context_limit() == 30000
    assert bud.output_tokens("synthesis") == 800
    # Input budget = ctx - output - safety margin, and always non-negative.
    assert 0 < bud.input_budget("synthesis") < 30000


def test_bad_env_falls_back_to_default(monkeypatch):
    bud = _load("budget", "mc_budget_uut2")
    monkeypatch.setenv("MC_MODEL_CTX", "not-a-number")
    assert bud.model_context_limit() == 30000


def test_fit_text_truncates_only_when_over(monkeypatch):
    bud = _load("budget", "mc_budget_uut3")
    assert bud.fit_text("short", 100) == "short"
    long = "word " * 5000
    trimmed = bud.fit_text(long, 50)
    assert len(trimmed) < len(long)
    assert bud.estimate_tokens(trimmed) <= 50 + 10  # marker slack


def test_fit_hits_drops_passages_over_budget(monkeypatch):
    # A tiny context forces synthesis to keep only what fits.
    monkeypatch.setenv("MC_MODEL_CTX", "1200")
    monkeypatch.setenv("MC_SYNTHESIS_MAX_OUTPUT_TOKENS", "256")
    syn = _load("synthesis", "mc_synth_budget_uut")
    hits = [{"chunk_id": f"amm_ata32#{i}", "text": "gear " * 200, "score": 0.9}
            for i in range(6)]
    fitted = syn.fit_hits_to_budget("what is the gear torque?", hits)
    assert 1 <= len(fitted) < len(hits)


def test_fit_hits_truncates_when_top_hit_alone_too_big(monkeypatch):
    monkeypatch.setenv("MC_MODEL_CTX", "1000")
    monkeypatch.setenv("MC_SYNTHESIS_MAX_OUTPUT_TOKENS", "256")
    syn = _load("synthesis", "mc_synth_budget_uut2")
    hits = [{"chunk_id": "amm_ata32#0", "text": "gear " * 5000, "score": 0.9}]
    fitted = syn.fit_hits_to_budget("q", hits)
    assert len(fitted) == 1
    assert len(fitted[0]["text"]) < len(hits[0]["text"])  # truncated


def test_client_defaults_max_tokens_per_role():
    cfg = _load("config", "mc_cfg_budget_uut")
    client_mod = _load("client", "mc_client_budget_uut")
    seen = {}

    class _FakeChat:
        class completions:
            @staticmethod
            def create(model, messages, **kw):
                seen.update(kw)
                return type("R", (), {"choices": [type("C", (), {
                    "message": type("M", (), {"content": "ok"})()})()]})()

    class _FakeOpenAI:
        def __init__(self, base_url, api_key):
            self.chat = _FakeChat()

    rc = client_mod.RoleClient(
        cfg.load_config(env={}),
        client_factory=lambda base_url, api_key: _FakeOpenAI(base_url, api_key),
    )
    rc.chat("synthesis", [{"role": "user", "content": "hi"}])
    assert seen["max_tokens"] == 1536  # default output cap (JSON envelope needs headroom)


def test_client_respects_explicit_max_tokens():
    cfg = _load("config", "mc_cfg_budget_uut2")
    client_mod = _load("client", "mc_client_budget_uut2")
    seen = {}

    class _FakeChat:
        class completions:
            @staticmethod
            def create(model, messages, **kw):
                seen.update(kw)
                return type("R", (), {"choices": [type("C", (), {
                    "message": type("M", (), {"content": "ok"})()})()]})()

    class _FakeOpenAI:
        def __init__(self, base_url, api_key):
            self.chat = _FakeChat()

    rc = client_mod.RoleClient(
        cfg.load_config(env={}),
        client_factory=lambda base_url, api_key: _FakeOpenAI(base_url, api_key),
    )
    rc.chat("synthesis", [{"role": "user", "content": "hi"}], max_tokens=1)
    assert seen["max_tokens"] == 1  # caller override wins
