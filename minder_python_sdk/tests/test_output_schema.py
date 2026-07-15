import logging

from minder_python_sdk import Connector
from minder_python_sdk._response import Response


def _conn():
    return Connector("t", version="1")


def test_output_schema_from_return_annotation():
    conn = _conn()

    @conn.tool("o1", description="o")
    def o1(x: int) -> int:
        return Response(result=x)

    spec = next(t for t in conn._tool_specs() if t["name"] == "o1")
    assert spec["output_schema"] is not None
    assert spec["output_schema"].get("type") == "integer"


def test_no_annotation_gives_null_output_schema():
    conn = _conn()

    @conn.tool("o2", description="o")
    def o2(x: int):
        return {"output": x}

    spec = next(t for t in conn._tool_specs() if t["name"] == "o2")
    assert spec["output_schema"] is None


def test_output_mismatch_warns_but_returns(caplog):
    conn = _conn()

    @conn.tool("o3", description="o")
    def o3(x: int) -> int:
        return Response(result="not-an-int")  # violates -> int

    with caplog.at_level(logging.WARNING):
        out = conn.invoke("o3", {"x": 1})
    assert out["success"] is True          # soft: still returned
    assert out["output"] == "not-an-int"
    assert any("output" in r.message.lower() for r in caplog.records)
