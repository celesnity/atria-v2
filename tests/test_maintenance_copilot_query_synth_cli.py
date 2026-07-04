"""Tests for `query --synthesize` wiring (in-memory Qdrant, fake chat, temp audit)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_CLI = (
    Path(__file__).resolve().parent.parent
    / "modules" / "maintenance_copilot" / "scripts" / "copilot.py"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("mc_query_synth_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_query_synth_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def _embed_fn(texts):
    return [[1.0 if "gear" in t.lower() else 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    mod = _load_cli()
    from qdrant_client import QdrantClient
    shared = QdrantClient(":memory:")
    monkeypatch.setenv("MC_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    def fake_store(embed_fn=None, qdrant=None):
        s = mod.IndexStore(shared, _embed_fn)
        s.ensure_collection(dim=3)
        return s

    monkeypatch.setattr(mod, "_build_store", fake_store)

    def fake_chat(messages, **kw):
        # Build a schema-valid answer from the prompt itself: cite the first
        # chunk and quote the first line of its text verbatim.
        user = messages[-1]["content"]
        chunk_id = re.search(r"chunk_id: (\S+)", user).group(1)
        quote = re.search(r"text:\n([^\n]+)", user).group(1)
        return json.dumps({
            "answer_type": "extractive",
            "response": {"primary_answer": "Per the AMM, see the cited step.",
                         "exact_quote": quote, "is_sensitive": False},
            "citations": [{"chunk_id": chunk_id}],
            "related_suggestions": [],
            "data_collection_requirement": {"needs_user_input": False,
                                            "missing_fields": []},
        })

    monkeypatch.setattr(mod, "_synthesis_chat_fn", lambda: fake_chat)
    return mod, str(tmp_path / "audit.jsonl")


def test_query_synthesize_attaches_answer_and_audits(cli, capsys):
    mod, audit_log = cli
    mod.main(["ingest"])
    capsys.readouterr()
    rc = mod.main(["query", "gear removal", "--revision", "none", "--synthesize"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "answer" in out
    assert "disclaimer" in out["answer"]
    answer = out["answer"]
    assert answer["answer_type"] == "extractive"
    assert answer["structured"]["response"]["exact_quote"]
    assert answer["citations"]  # cited chunk survived verification
    assert answer["validation_warnings"] == []
    # An audit event was recorded, carrying the structured-output telemetry.
    lines = Path(audit_log).read_text(encoding="utf-8").splitlines()
    events = [json.loads(ln) for ln in lines]
    query_events = [e for e in events if e["type"] == "query"]
    assert query_events and query_events[0]["answer_type"] == "extractive"
    assert query_events[0]["json_mode"] == "schema"  # default mode, fake accepts **kw


def test_query_without_synthesize_has_no_answer(cli, capsys):
    mod, _ = cli
    mod.main(["ingest"])
    capsys.readouterr()
    mod.main(["query", "gear", "--revision", "none"])
    out = json.loads(capsys.readouterr().out)
    assert "answer" not in out


def test_dead_sidecar_prints_clean_json_error(monkeypatch, capsys):
    mod = _load_cli()

    def dead_store(*a, **k):
        raise ConnectionError("connection refused: qdrant :6333")

    monkeypatch.setattr(mod, "_build_store", dead_store)
    rc = mod.main(["query", "gear removal", "--synthesize"])
    assert rc == 1
    captured = capsys.readouterr()
    out = json.loads(captured.out)  # single clean JSON line, no traceback
    assert "qdrant unreachable" in out["error"]
    assert out["hint"] == "run: python copilot.py health"
    assert "Traceback" not in captured.err


def test_non_connectivity_error_still_raises(monkeypatch):
    mod = _load_cli()

    def broken_store(*a, **k):
        raise ValueError("bad config")

    monkeypatch.setattr(mod, "_build_store", broken_store)
    with pytest.raises(ValueError):
        mod.main(["query", "gear removal"])


def test_audit_subcommand_skips_sidecar_wrap(monkeypatch, capsys, tmp_path):
    mod = _load_cli()
    monkeypatch.setenv("MC_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    # audit must not touch any sidecar even when stores are dead
    monkeypatch.setattr(mod, "_build_store", lambda *a, **k: 1 / 0)
    rc = mod.main(["audit", "--limit", "5"])
    assert rc == 0
