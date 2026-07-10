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
