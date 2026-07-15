from minder_python_sdk import Connector
from minder_python_sdk._response import ActionError, Response


def _conn():
    return Connector("t", version="1")


def test_response_result_maps_to_output():
    conn = _conn()

    @conn.tool("r1", description="r")
    def r1(x: int):
        return Response(result=x * 2)

    out = conn.invoke("r1", {"x": 3})
    assert out["success"] is True and out["output"] == 6


def test_response_error_maps_to_failure():
    conn = _conn()

    @conn.tool("r2", description="r")
    def r2(x: int):
        return Response(error="bad thing")

    out = conn.invoke("r2", {"x": 1})
    assert out["success"] is False and "bad thing" in out["output"]


def test_action_error_is_handled_failure():
    conn = _conn()

    @conn.tool("r3", description="r")
    def r3(x: int):
        raise ActionError("nope")

    out = conn.invoke("r3", {"x": 1})
    assert out["success"] is False and "nope" in out["output"]
