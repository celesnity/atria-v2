"""Tests for the `check` inconsistency-flagging command (fakes; temp audit)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_CLI = (
    Path(__file__).resolve().parent.parent
    / "modules" / "maintenance_copilot" / "scripts" / "copilot.py"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("mc_check_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_check_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeStore:
    def __init__(self, hits):
        self._hits = hits

    def query(self, text, k=5, ata_chapter=None, revision="current"):
        return self._hits


class _FakeGraph:
    def neighbors(self, key, hops=1):
        return [{"neighbor_key": "PLACARD-32-30-01", "neighbor_labels": ["Part"],
                 "edge_type": "REQUIRES", "status": "unverified", "confidence": 0.8}]


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    mod = _load_cli()
    monkeypatch.setenv("MC_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    return mod, tmp_path


def test_check_flags_missing_mel_and_requires_advisory(cli, capsys, monkeypatch):
    mod, tmp_path = cli
    # MEL not found (empty hits) + a REQUIRES advisory from the graph.
    monkeypatch.setattr(mod, "_build_store", lambda: _FakeStore([]))
    monkeypatch.setattr(mod, "_build_graph_store", lambda run_fn=None: _FakeGraph())
    payload = json.dumps({"defect": "gear indicator inop", "cited_mel": "MEL 32-30-01",
                          "dispatch_condition": "one indicator inop", "classification": ""})
    rc = mod.main(["check", payload])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert any(i["severity"] == "high" for i in out["inconsistencies"])
    assert any("PLACARD-32-30-01" in a["item"] for a in out["advisories"])
    assert out["advisories"][0]["status"] == "unverified"
    log = Path(str(tmp_path / "audit.jsonl")).read_text().splitlines()
    assert any(json.loads(x)["type"] == "check" for x in log)


def test_check_flags_category_mismatch(cli, capsys, monkeypatch):
    mod, _ = cli
    hits = [{"chunk_id": "mel_ata32#0", "text": "MEL 32-30-01 Category C. ...",
             "citation": "MEL ... · mel_ata32#0", "doc_type": "MEL",
             "revision": "Rev-18", "ata_chapter": "32", "score": 0.9}]
    monkeypatch.setattr(mod, "_build_store", lambda: _FakeStore(hits))
    monkeypatch.setattr(mod, "_build_graph_store", lambda run_fn=None: _FakeGraph())
    payload = json.dumps({"defect": "d", "cited_mel": "MEL 32-30-01",
                          "dispatch_condition": "x", "classification": "A"})
    mod.main(["check", payload])
    out = json.loads(capsys.readouterr().out)
    assert any("classification" in i["issue"] and i["severity"] == "medium"
               for i in out["inconsistencies"])
