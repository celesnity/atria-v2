from minder_python_sdk import Connector
from minder_python_sdk._secret import Secret


def _conn():
    return Connector("t", version="1")


def test_secret_injected_from_headers():
    conn = _conn()

    @conn.tool("read_db", description="read")
    def read_db(query: str, db_password: Secret):
        return {"output": f"{query}:{db_password.value}"}

    out = conn.invoke("read_db", {"query": "q"}, headers={"x-db_password": "pw"})
    assert out["success"] is True and out["output"] == "q:pw"


def test_secret_injected_from_env(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "envpw")
    conn = _conn()

    @conn.tool("read_db2", description="read")
    def read_db2(query: str, db_password: Secret):
        return {"output": db_password.value}

    out = conn.invoke("read_db2", {"query": "q"})
    assert out["output"] == "envpw"


def test_missing_secret_is_fail_closed():
    conn = _conn()

    @conn.tool("read_db3", description="read")
    def read_db3(query: str, db_password: Secret):
        return {"output": "should not run"}

    out = conn.invoke("read_db3", {"query": "q"}, headers={})
    assert out["success"] is False
    assert "credential 'db_password' unavailable" in out["output"]


def test_secret_absent_from_manifest_schema():
    conn = _conn()

    @conn.tool("read_db4", description="read")
    def read_db4(query: str, db_password: Secret):
        return {"output": "x"}

    spec = next(t for t in conn._tool_specs() if t["name"] == "read_db4")
    assert "db_password" not in spec["parameters"]["properties"]
