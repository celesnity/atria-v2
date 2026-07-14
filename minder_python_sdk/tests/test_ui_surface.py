"""UI-driving surface: declaration in manifest, intent builders/validation,
and the per-session intent bus."""

from fastapi.testclient import TestClient

from minder_python_sdk import Connector, navigate, fill, request_confirm
from minder_python_sdk.ui import UiSurface, Page, Form


def _catalog_conn() -> Connector:
    conn = Connector("catalog")
    conn.page("product_new", path="/products/new", label="Add product")
    conn.form(
        "add_product",
        route="product_new",
        fields=[
            {"name": "sku", "type": "string", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "category", "type": "enum", "options": ["A", "B", "C"], "required": False},
        ],
        submit_tool="create_product",
        risk="medium",
        instructions="Fill sku+name; ask user to confirm before submitting.",
    )
    return conn


def test_declared_surface_in_manifest():
    conn = _catalog_conn()
    client = TestClient(conn.asgi())
    mani = client.get("/connector/manifest").json()
    ui = mani["ui"]
    assert ui["pages"][0]["id"] == "product_new"
    form = ui["forms"][0]
    assert form["id"] == "add_product"
    assert form["submit_tool"] == "create_product"
    assert form["risk"] == "medium"
    assert "confirm" in form["instructions"].lower()
    assert client.get("/connector/health").json()["capabilities"]["ui_driving"] is True


def test_navigate_tool_auto_registered_from_pages():
    conn = _catalog_conn()
    conn.page("metrics", path="/metrics", label="Metrics")
    nav = conn._tools["catalog_navigate"]
    # Enum reflects every declared page and refreshes as pages are added.
    assert nav.parameters["properties"]["page"]["enum"] == ["product_new", "metrics"]
    assert nav.risk == "low" and nav.read_only is False


def test_navigate_tool_pushes_intent_to_session_bus():
    import queue

    from minder_python_sdk.connector import Principal

    conn = _catalog_conn()
    conn.page("metrics", path="/metrics", label="Metrics")
    q: "queue.Queue[dict]" = queue.Queue()
    conn._ui_bus["sess"] = [q]

    res = conn._call(conn._tools["catalog_navigate"], {"page": "metrics"}, Principal(), session_id="sess")
    assert "Metrics" in res["output"]
    assert q.get_nowait() == {"intent": "navigate", "route": "metrics"}


def test_navigate_tool_rejects_unknown_page():
    from minder_python_sdk.connector import Principal

    conn = _catalog_conn()
    res = conn._call(conn._tools["catalog_navigate"], {"page": "ghost"}, Principal())
    assert res["success"] is False and res["error"]["code"] == "unknown_page"


def test_intent_builders():
    assert navigate("product_new") == {"intent": "navigate", "route": "product_new"}
    f = fill("add_product", {"sku": "ABC"}, partial=True)
    assert f["intent"] == "fill" and f["values"]["sku"] == "ABC" and f["partial"] is True
    assert request_confirm("add_product", summary="ok")["summary"] == "ok"


def test_surface_validation_flags_unknown_targets():
    s = UiSurface(pages={"p": Page("p", "/p", "P")}, forms={"f": Form("f", "p", [])})
    assert s.validate(navigate("p")) is None
    assert "unknown route" in s.validate(navigate("nope"))
    assert s.validate(fill("f", {})) is None
    assert "unknown form" in s.validate(fill("ghost", {}))


def test_push_ui_intent_emits_event_and_enqueues():
    conn = _catalog_conn()
    seen = []
    conn.on_event(seen.append)
    # register a fake subscriber queue for the session
    import queue

    q: "queue.Queue[dict]" = queue.Queue()
    conn._ui_bus["s1"] = [q]

    conn.push_ui_intent("s1", navigate("product_new"))
    assert q.get_nowait()["route"] == "product_new"
    assert seen[-1].type == "ui.intent"
    assert seen[-1].payload["intent"]["intent"] == "navigate"


def test_push_ui_intent_warns_on_unknown_but_still_sends():
    conn = _catalog_conn()
    out = conn.push_ui_intent("s1", navigate("ghost"))
    assert out["ok"] is True
    assert "unknown route" in out["warning"]


def test_ui_intent_http_endpoint_routes_to_bus():
    conn = _catalog_conn()
    import queue

    q: "queue.Queue[dict]" = queue.Queue()
    conn._ui_bus["sess"] = [q]
    client = TestClient(conn.asgi())
    r = client.post(
        "/connector/ui/intent",
        json={"session_id": "sess", "intent": fill("add_product", {"sku": "ABC"})},
    )
    assert r.json()["ok"] is True
    assert q.get_nowait()["values"]["sku"] == "ABC"
