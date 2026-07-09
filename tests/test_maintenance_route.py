"""maintenance.py proxies health/signoff to the connector (no in-process pipeline import)."""
from __future__ import annotations

import atria.web.routes.maintenance as mroute


def test_signoff_injects_engineer_and_posts(monkeypatch):
    posted = {}
    class _Conn:
        def post_json(self, path, payload, timeout=15.0):
            posted["path"] = path; posted["payload"] = payload
            return {"ok": True, "event": {"id": "e1"}}
        def get_json(self, path, timeout=5.0):
            return {"qdrant": "ok"}
    monkeypatch.setattr(mroute, "_connector", lambda: _Conn())

    class _User: username = "eng@x"
    import asyncio
    body = mroute.SignoffBody(decision="acknowledged", query="q")
    out = asyncio.get_event_loop().run_until_complete(mroute.signoff(body, user=_User()))
    assert out["ok"] is True
    assert posted["path"] == "/connector/signoff"
    assert posted["payload"]["engineer"] == "eng@x"
    assert posted["payload"]["decision"] == "acknowledged"


def test_maintenance_py_has_no_pipeline_import():
    import inspect
    src = inspect.getsource(mroute)
    assert "import copilot" not in src
    assert "import audit" not in src
    assert "scripts" not in src
