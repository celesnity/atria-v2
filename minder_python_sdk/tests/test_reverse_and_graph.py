"""BE-SDK-08 (how to reverse) + BE-SDK-10 (Operational Graph query)."""

from fastapi.testclient import TestClient

from minder_python_sdk import Connector
from minder_python_sdk.connector import Principal


# --- BE-SDK-08: reversibility carries *how* to reverse -----------------------


def test_undo_is_advertised_in_manifest_and_context():
    conn = Connector("m")

    @conn.tool("scrap_part", risk="high", reversible=True, undo="restore_part(part)")
    def scrap_part(part: str = ""):
        return {"output": "scrapped"}

    client = TestClient(conn.asgi())
    spec = next(t for t in client.get("/connector/manifest").json()["tools"]
                if t["name"] == "scrap_part")
    assert spec["reversible"] is True
    assert spec["undo"] == "restore_part(part)"

    action = next(a for a in client.get("/connector/context").json()["actions"]
                  if a["name"] == "scrap_part")
    assert action["undo"] == "restore_part(part)"


def test_undo_rides_the_decision_packet_when_gated():
    conn = Connector("m")

    @conn.tool("scrap_part", risk="high", reversible=True, undo="restore_part(part)")
    def scrap_part(part: str = ""):
        return {"output": "scrapped"}

    out = conn.invoke("scrap_part", {"part": "X"}, autonomy="low")
    assert out["requires_approval"] is True
    assert out["card"]["undo"] == "restore_part(part)"
    assert out["card"]["reversible"] is True


# --- BE-SDK-10: Operational Graph query -------------------------------------


def test_graph_provider_answers_linked_context():
    conn = Connector("m")

    @conn.graph
    def graph(node=None, depth=1, principal=None):
        return {
            "nodes": [{"id": node}, {"id": "wo-1"}],
            "edges": [{"from": node, "to": "wo-1", "rel": "blocks"}],
        }

    client = TestClient(conn.asgi())
    body = client.get("/connector/graph", params={"node": "part-7", "depth": "2"}).json()
    assert body["available"] is True
    assert body["nodes"][0]["id"] == "part-7"
    assert body["edges"][0]["rel"] == "blocks"
    assert client.get("/connector/health").json()["capabilities"]["graph"] is True


def test_graph_query_fail_closes_without_provider():
    conn = Connector("m")
    client = TestClient(conn.asgi())
    body = client.post("/connector/graph", json={"node": "x"}).json()
    assert body == {"nodes": [], "edges": [], "available": False}
    assert client.get("/connector/health").json()["capabilities"]["graph"] is False


def test_graph_provider_receives_principal():
    conn = Connector("m")
    seen = {}

    @conn.graph
    def graph(node=None, principal=None):
        seen["user"] = principal.username
        return {"nodes": [], "edges": []}

    conn.query_graph("n", principal=Principal("alice", "a@x"))
    assert seen["user"] == "alice"
