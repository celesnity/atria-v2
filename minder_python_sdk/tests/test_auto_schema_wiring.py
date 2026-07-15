from pydantic import BaseModel

from minder_python_sdk import Connector


def _conn():
    return Connector("t", version="1")


def test_auto_schema_nested_model_arrives_as_instance():
    conn = _conn()

    class Address(BaseModel):
        city: str

    @conn.tool("ship", description="ship")
    def ship(addr: Address):
        # The handler declared addr: Address, so it must receive an Address,
        # not a plain dict (auto-schema honors the handler's own type hint).
        return {"output": f"{type(addr).__name__}:{addr.city}"}

    out = conn.invoke("ship", {"addr": {"city": "hanoi"}})
    assert out["success"] is True and out["output"] == "Address:hanoi"


def test_explicit_params_model_keeps_dict_contract():
    conn = _conn()

    class Args(BaseModel):
        city: str

    @conn.tool("ship2", params_model=Args)
    def ship2(city: str):
        return {"output": city}

    out = conn.invoke("ship2", {"city": "hue"})
    assert out["success"] is True and out["output"] == "hue"


def test_streaming_tool_validates_input():
    conn = _conn()

    @conn.tool("count", description="count", streaming=True)
    def count(n: int):
        yield {"event": "progress", "n": n}
        yield {"event": "final", "output": n}

    # Bad input on the streaming path must fail closed, not reach the handler.
    events = b"".join(conn._sse(conn._tools["count"], {"n": "NaN"}, None))
    assert b"invalid arguments" in events


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
