import json
import os
from minder_python_sdk import Connector
from minder_python_sdk.connector import Principal
from fastapi.testclient import TestClient


def test_conn_block_fills_name_and_remote_entry(monkeypatch):
    monkeypatch.setenv("MINDER_MODULE_REMOTE_ENTRY", "http://h:9300/dashboard/remoteEntry.js")
    conn = Connector("my_module")
    d = conn.block("./MyAnswer", {"answer": "hi"})
    assert d["render"] == "remote"
    assert d["remote_name"] == "my_module"
    assert d["component"] == "./MyAnswer"
    assert d["remote_entry"] == "http://h:9300/dashboard/remoteEntry.js"
    assert d["api_base"] == "http://h:9300"
    assert d["props"] == {"answer": "hi"}


def test_conn_invoke_runs_tool_in_process():
    conn = Connector("m")

    @conn.tool("echo", parameters={"type": "object", "properties": {"q": {"type": "string"}}})
    def echo(q: str = ""):
        return {"output": q.upper()}

    out = conn.invoke("echo", {"q": "hi"})
    assert out["success"] is True and out["output"] == "HI"


def test_health_ready_defaults_true():
    conn = Connector("m")
    c = TestClient(conn.asgi())
    assert c.get("/connector/health").json()["ready"] is True


def test_readiness_probe_can_report_not_ready():
    conn = Connector("m")

    @conn.readiness_probe
    def probe():
        return {"ready": False, "detail": "ingesting"}

    c = TestClient(conn.asgi())
    assert c.get("/connector/health").json()["ready"] is False


from pydantic import BaseModel


def test_params_model_derives_schema_and_validates():
    conn = Connector("m")

    class P(BaseModel):
        q: str
        k: int = 5

    @conn.tool("search", params_model=P)
    def search(q: str, k: int = 5):
        return {"output": f"{q}:{k}"}

    # Schema derived:
    assert conn._tools["search"].parameters["properties"]["q"]["type"] == "string"
    # Valid:
    assert conn.invoke("search", {"q": "hi", "k": 3})["output"] == "hi:3"
    # Invalid (missing required q):
    bad = conn.invoke("search", {"k": 3})
    assert bad["success"] is False and "invalid arguments" in bad["output"]


def test_params_model_and_parameters_are_mutually_exclusive():
    conn = Connector("m")
    import pytest
    with pytest.raises(ValueError):
        @conn.tool("x", parameters={"type": "object"}, params_model=BaseModel)
        def x():
            return {}


def test_requires_auth_blocks_anonymous():
    conn = Connector("m")

    @conn.tool("secret", requires_auth=True)
    def secret(principal=None):
        return {"output": "ok"}

    anon = conn.invoke("secret", {})
    assert anon["success"] is False and anon["output"] == "authentication required"
    authed = conn.invoke("secret", {}, principal=Principal(username="alice", email="a@x"))
    assert authed["output"] == "ok"


def test_session_id_injected_into_handler():
    conn = Connector("m")
    seen = {}

    @conn.tool("cap")
    def cap(session_id=None, **kwargs):
        seen["sid"] = session_id
        return {"output": "ok"}

    conn.invoke("cap", {}, session_id="sess-123")
    assert seen["sid"] == "sess-123"


def test_manifest_advertises_exposed_blocks_and_versions(monkeypatch):
    monkeypatch.setenv("MODULE_PUBLIC_BASE", "http://h:9300")
    conn = Connector("m", min_core_version="2")
    conn.expose_block("./MyAnswer")

    @conn.tool("q", card_type="m_answer")
    def q():
        return {}

    from fastapi.testclient import TestClient
    mani = TestClient(conn.asgi()).get("/connector/manifest").json()
    assert mani["remote"]["exposed"] == {"dashboard": "./Dashboard", "./MyAnswer": "./MyAnswer"}
    assert mani["card_types"] == ["m_answer"]
    assert mani["contract_version"] == "3" and mani["min_core_version"] == "2"


def test_stream_delivers_ui_intent_for_matching_session():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    conn.page("home", path="/", label="Home")
    client = TestClient(conn.asgi())

    with client.stream("GET", "/connector/stream?session=s1") as resp:
        lines = resp.iter_lines()
        assert next(lines) == ": ok"           # open marker
        conn.push_ui_intent("s1", {"intent": "navigate", "route": "home"})
        # advance to the data frame (skip blank separators / pings)
        payload = None
        for _ in range(10):
            line = next(lines)
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                break
        assert payload is not None
        assert payload["type"] == "ui.intent"
        assert payload["session_id"] == "s1"
        assert payload["payload"]["intent"]["route"] == "home"


def test_snapshot_then_delta_applies_and_versions():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    client = TestClient(conn.asgi())

    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "snapshot", "snapshot": {"page": "home", "n": 1}},
    )
    assert r.json() == {"ok": True, "version": 1}

    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "delta", "base_version": 1,
              "delta": [{"op": "replace", "path": "/n", "value": 2}]},
    )
    assert r.json() == {"ok": True, "version": 2}

    ctx = client.get("/connector/context", headers={"X-Minder-Session": "s1"}).json()
    assert ctx["ui_snapshot"] == {"page": "home", "n": 2}


def test_snapshot_delta_version_mismatch_returns_409():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    client = TestClient(conn.asgi())
    client.post("/connector/ui/snapshot",
                json={"session_id": "s1", "kind": "snapshot", "snapshot": {"n": 1}})
    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "delta", "base_version": 99,
              "delta": [{"op": "replace", "path": "/n", "value": 2}]},
    )
    assert r.status_code == 409
    assert r.json()["version"] == 1
