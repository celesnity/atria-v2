from minder_python_sdk import Connector


def _conn():
    return Connector("t", version="1")


def test_tool_without_schema_infers_parameters():
    conn = _conn()

    @conn.tool("greet", description="greet")
    def greet(name: str, times: int = 1):
        return {"output": name * times}

    spec = next(t for t in conn._tool_specs() if t["name"] == "greet")
    assert spec["parameters"]["properties"]["name"]["type"] == "string"
    assert spec["parameters"]["required"] == ["name"]


def test_explicit_parameters_still_win():
    conn = _conn()
    hand = {"type": "object", "properties": {"x": {"type": "string"}}}

    @conn.tool("raw", parameters=hand)
    def raw(x: str, secret_unused: int = 0):
        return {"output": x}

    spec = next(t for t in conn._tool_specs() if t["name"] == "raw")
    assert spec["parameters"] == hand  # untouched


def test_auto_schema_gives_input_validation():
    conn = _conn()

    @conn.tool("addone", description="add one")
    def addone(n: int):
        return {"output": n + 1}

    ok = conn.invoke("addone", {"n": 5})
    assert ok["success"] is True and ok["output"] == 6

    bad = conn.invoke("addone", {"n": "not-an-int"})
    assert bad["success"] is False
    assert "invalid arguments" in bad["output"]


def test_no_arg_tool_keeps_empty_schema():
    conn = _conn()

    @conn.tool("ping", description="ping")
    def ping(**kwargs):
        return {"output": "pong"}

    spec = next(t for t in conn._tool_specs() if t["name"] == "ping")
    assert spec["parameters"] == {"type": "object", "properties": {}}
