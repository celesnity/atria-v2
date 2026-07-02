# tests/test_maintenance_copilot_graph_cli.py
"""Tests for the `graph` CLI subcommands (fake graph store + fake extractor)."""

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
    spec = importlib.util.spec_from_file_location("mc_graph_cli_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_graph_cli_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_EXTRACT_JSON = """{"entities":[{"type":"ATAChapter","key":"32","props":{}}],
"relationships":[]}"""


@pytest.fixture()
def cli(monkeypatch):
    mod = _load_cli()

    calls = {"upserts": 0}

    class _FakeStore:
        def ensure_constraints(self):
            pass

        def upsert_extraction(self, ext):
            calls["upserts"] += 1
            return len(ext.entities), len(ext.edges)

        def neighbors(self, key, hops=1):
            return [{"neighbor_key": "32-30-01", "neighbor_labels": ["MELItem"],
                     "edge_type": "IN_CHAPTER", "status": "unverified", "confidence": 0.9}]

        def confirm_edge(self, s, t, d):
            return 1

        def stats(self):
            return {"nodes": 1, "edges": 0, "unverified_edges": 0}

        def reset(self):
            pass

    monkeypatch.setattr(mod, "_build_graph_store", lambda run_fn=None: _FakeStore())
    monkeypatch.setattr(mod, "_kg_chat_fn", lambda: (lambda messages: _EXTRACT_JSON))
    return mod, calls


def test_graph_build_extracts_and_upserts(cli, capsys):
    mod, calls = cli
    rc = mod.main(["graph", "build"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["chunks"] >= 4          # one per sample-manual chunk
    assert out["nodes"] >= 1
    assert calls["upserts"] >= 4


def test_graph_show_flags_unverified(cli, capsys):
    mod, _ = cli
    rc = mod.main(["graph", "show", "32", "--hops", "1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["key"] == "32"
    assert out["neighbors"][0]["status"] == "unverified"
    assert out["unverified"] == 1


def test_graph_confirm_and_stats(cli, capsys):
    mod, _ = cli
    assert mod.main(["graph", "confirm", "32-30-01", "IN_CHAPTER", "32"]) == 0
    assert json.loads(capsys.readouterr().out)["confirmed"] == 1
    assert mod.main(["graph", "stats"]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == 1
