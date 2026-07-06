"""CLI wiring tests for whoami / can-access / guard_accessible (no live services)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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


def test_guard_accessible_splits_hits():
    k = _load("knowledge", "ek_knowledge_uut")
    identity = _load("identity", "ek_ident_for_cli")
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = [
        {"doc_id": "DOC002", "classification": "Internal", "department": "COMP"},
        {"doc_id": "DOC007", "classification": "Confidential", "department": "HR"},
    ]
    safe, blocked = k.guard_accessible(eng, hits)
    assert [h["doc_id"] for h in safe] == ["DOC002"]
    assert [h["doc_id"] for h in blocked] == ["DOC007"]


def test_can_access_command_denies(capsys, tmp_path, monkeypatch):
    k = _load("knowledge", "ek_knowledge_uut2")
    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    # users.csv
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n" "U004,n,ENG,Employee,e,Active\n",
        encoding="utf-8",
    )
    # a single sample doc
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "DOC036.md").write_text(
        "---\ndoc_id: DOC036\ntitle: t\ndepartment: EXEC\nclassification: Restricted\n---\nx\n",
        encoding="utf-8",
    )
    rc = k.main(["can-access", "U004", "DOC036", "--users", str(users), "--samples", str(docs)])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"allowed": false' in out.lower() or '"allowed": false' in out


def test_whoami_unknown_user_returns_clean_error(capsys, tmp_path, monkeypatch):
    k = _load("knowledge", "ek_knowledge_uut_unknown")
    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n" "U004,n,ENG,Employee,e,Active\n",
        encoding="utf-8",
    )
    rc = k.main(["whoami", "U999", "--users", str(users)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "error" in out.lower()


def test_parse_dotenv_reads_pairs_and_ignores_noise():
    """The .env parser must handle comments, blanks, export, quotes, and URLs."""
    k = _load("knowledge", "ek_knowledge_dotenv")
    text = (
        "# a comment\n"
        "\n"
        "OPENROUTER_API_KEY=sk-or-abc\n"
        "export EK_SYNTHESIS_MODEL=openai/gpt-4o-mini\n"
        'EK_SYNTHESIS_BASE_URL="https://openrouter.ai/api/v1"\n'
        "ATRIA_MODEL='openai/gpt-4o'\n"
        "MALFORMED_NO_EQUALS\n"
    )
    parsed = k._parse_dotenv(text)
    assert parsed["OPENROUTER_API_KEY"] == "sk-or-abc"
    assert parsed["EK_SYNTHESIS_MODEL"] == "openai/gpt-4o-mini"
    assert parsed["EK_SYNTHESIS_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert parsed["ATRIA_MODEL"] == "openai/gpt-4o"
    assert "MALFORMED_NO_EQUALS" not in parsed


def test_whoami_utf8_output_survives_legacy_console(tmp_path):
    """Vietnamese CLI output must not crash when stdout uses a legacy codec.

    Regression: on a cp1252 console (Windows default) ``json.dumps(ensure_ascii
    =False)`` raised UnicodeEncodeError on Vietnamese names. The CLI now forces
    UTF-8 on its own streams. Forcing ``PYTHONIOENCODING=cp1252`` reproduces the
    legacy console deterministically on any platform (a piped stdout honours it
    too), so this guards the fix cross-platform, not just on Windows.
    """
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U001,Nguyễn Văn Phú,HR,Employee,e,Active\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    proc = subprocess.run(
        [sys.executable, str(_MOD / "knowledge.py"), "whoami", "U001", "--users", str(users)],
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "Nguyễn Văn Phú" in proc.stdout.decode("utf-8")


def test_parser_accepts_graph_build_and_flags():
    knowledge = _load("knowledge", "ek_cli_graph")
    args = knowledge.build_parser().parse_args(["graph", "build", "--extract"])
    assert args.command == "graph" and args.graph_command == "build" and args.extract is True


def test_parser_accepts_graph_stats_and_reset():
    knowledge = _load("knowledge", "ek_cli_graph2")
    a = knowledge.build_parser().parse_args(["graph", "stats"])
    b = knowledge.build_parser().parse_args(["graph", "reset"])
    assert a.graph_command == "stats" and b.graph_command == "reset"


def test_query_parser_has_graph_flag():
    knowledge = _load("knowledge", "ek_cli_graph3")
    args = knowledge.build_parser().parse_args(["query", "q", "--user", "U001", "--graph"])
    assert args.graph is True


def test_cmd_query_graph_merges_safe_graph_hits(capsys, monkeypatch):
    knowledge = _load("knowledge", "ek_cli_qgraph")

    class FakeStore:
        def query(self, text, k, acl_filter, department=None):
            return [
                {
                    "score": 0.9,
                    "citation": "[A]",
                    "text": "a",
                    "doc_id": "DOCA",
                    "chunk_id": "DOCA#0",
                    "title": "A",
                    "department": "COMP",
                    "classification": "Public",
                    "knowledge_space": "Company Knowledge",
                }
            ]

    class FakeGraphStore:
        def neighbors_via_entities(self, seeds, hops, acl, limit):
            return [
                {
                    "chunk_id": "DOCB#0",
                    "doc_id": "DOCB",
                    "text": "b",
                    "title": "B",
                    "department": "COMP",
                    "classification": "Internal",
                    "knowledge_space": "Company Knowledge",
                    "citation": "[B]",
                }
            ]

        def neighbors_via_tags(self, seeds, acl, limit):
            return []

    # Point the user resolver at a known user without touching the real CSV.
    monkeypatch.setenv("EK_USERS_CSV", str(_MOD.parent / "access" / "users.csv"))
    rc = knowledge._cmd_query(
        "q",
        "U001",
        5,
        None,
        synthesize=False,
        users_path=None,
        store=FakeStore(),
        graph=True,
        graph_store_obj=FakeGraphStore(),
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    ids = {h["chunk_id"] for h in out["hits"]}
    assert {"DOCA#0", "DOCB#0"} <= ids  # vector + safe graph hit both present


def test_health_reports_neo4j_key(capsys, monkeypatch):
    knowledge = _load("knowledge", "ek_cli_health_neo4j")
    # Force the neo4j probe to fail fast (no server) — health must still return a dict.
    monkeypatch.setenv("EK_NEO4J_URI", "bolt://127.0.0.1:59999")
    knowledge._cmd_health()
    out = json.loads(capsys.readouterr().out)
    assert "neo4j" in out
