"""In-process tests for module_template via conn.invoke (no HTTP)."""
from __future__ import annotations

import os
import sys

# Make the backend package importable (app.py imports `service` as a top-level module).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from atria_module_sdk.connector import Principal  # noqa: E402
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
