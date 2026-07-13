"""In-process tests for module_template via conn.invoke (no HTTP)."""
from __future__ import annotations

import os
import sys

# Make the backend package importable (app.py imports `service` as a top-level module).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minder_module_sdk.connector import Principal  # noqa: E402
import app as mt  # noqa: E402


def test_typed_query_validates():
    ok = mt.conn.invoke("template_typed_query", {"topic": "blocks", "limit": 2})
    assert ok["success"] is True and ok["output"]["count"] == 2
    bad = mt.conn.invoke("template_typed_query", {"topic": "x", "limit": 99})  # >5 → invalid
    assert bad["success"] is False and "invalid arguments" in bad["output"]


def test_requires_auth_gate():
    anon = mt.conn.invoke("template_secure", {})
    assert anon["success"] is False and anon["output"] == "authentication required"
    authed = mt.conn.invoke("template_secure", {}, principal=Principal(username="alice", email="a@x"))
    assert authed["success"] is True and "alice" in authed["output"]


def test_manifest_advertises_block_and_min_core():
    from fastapi.testclient import TestClient
    os.environ["MT_PUBLIC_BASE"] = "http://localhost:9300"
    mani = TestClient(mt.conn.asgi()).get("/connector/manifest").json()
    assert mani["remote"]["exposed"]["./ShowcaseBlock"] == "./ShowcaseBlock"
    assert mani["min_core_version"] == "2"
    assert "template_card" in mani["card_types"]


def test_start_and_list_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_TEST", "1")
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import importlib, db as _db
    importlib.reload(_db); _db.init_db()
    import app as mt; importlib.reload(mt)
    monkeypatch.setattr(mt.tasks.run_job, "delay", lambda *a, **k: None)
    out = mt.conn.invoke("template_start_job", {"steps": 2})
    assert "started job" in out["output"]
    lst = mt.conn.invoke("template_list_jobs", {})
    assert len(lst["output"]["jobs"]) == 1
