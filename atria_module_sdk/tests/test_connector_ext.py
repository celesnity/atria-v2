import os
from atria_module_sdk import Connector
from fastapi.testclient import TestClient


def test_conn_block_fills_name_and_remote_entry(monkeypatch):
    monkeypatch.setenv("ATRIA_MODULE_REMOTE_ENTRY", "http://h:9300/dashboard/remoteEntry.js")
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
