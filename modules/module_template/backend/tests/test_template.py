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


def test_gated_action_carries_undo_escape_route():
    # delete is HIGH risk → gated below "high"; the decision packet must say how
    # to recover (BE-SDK-08). create_product carries an undo hint of its own.
    out = mt.conn.invoke("create_product", {"sku": "SKU-U", "name": "Undoable", "price": 5},
                         autonomy="none")
    assert out["requires_approval"] is True
    assert "delete_product" in (out["card"]["undo"] or "")


def test_operational_graph_endpoint_returns_linked_context():
    from fastapi.testclient import TestClient
    client = TestClient(mt.conn.asgi())
    # capability advertised
    assert client.get("/connector/health").json()["capabilities"]["graph"] is True
    # whole graph has product + category nodes joined by in_category edges
    full = client.get("/connector/graph").json()
    kinds = {n["kind"] for n in full["nodes"]}
    assert {"product", "category"} <= kinds
    assert any(e["rel"] == "in_category" for e in full["edges"])
    # a focused query returns just that node's neighbourhood
    sub = client.get("/connector/graph", params={"node": "category:A", "depth": 1}).json()
    assert sub["focus"] == "category:A"
    assert all(n["id"] in {e["from"] for e in sub["edges"]} | {e["to"] for e in sub["edges"]}
               | {"category:A"} for n in sub["nodes"])


def test_graph_page_declared_for_navigation():
    # the Graph tab is a declared page so the auto navigate tool can open it
    mani = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(
        mt.conn.asgi()).get("/connector/manifest").json()
    assert any(p["id"] == "graph" for p in mani["ui"]["pages"])


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
