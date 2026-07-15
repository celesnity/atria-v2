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
    from minder_python_sdk.connector import Principal
    from minder_python_sdk.envelope import EventEnvelope

    conn = _catalog_conn()
    conn.page("metrics", path="/metrics", label="Metrics")
    seen: list[EventEnvelope] = []
    conn.on_event(seen.append)

    res = conn._call(conn._tools["catalog_navigate"], {"page": "metrics"}, Principal(), session_id="sess")
    assert "Metrics" in res["output"]
    ui_intent_events = [e for e in seen if e.type == "ui.intent" and e.session_id == "sess"]
    assert ui_intent_events, "expected a ui.intent envelope for session 'sess'"
    assert ui_intent_events[-1].payload["intent"] == {"intent": "navigate", "route": "metrics"}


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

    conn.push_ui_intent("s1", navigate("product_new"))
    assert seen[-1].type == "ui.intent"
    assert seen[-1].session_id == "s1"
    assert seen[-1].payload["intent"]["intent"] == "navigate"
    assert seen[-1].payload["intent"]["route"] == "product_new"


def test_push_ui_intent_warns_on_unknown_but_still_sends():
    conn = _catalog_conn()
    out = conn.push_ui_intent("s1", navigate("ghost"))
    assert out["ok"] is True
    assert "unknown route" in out["warning"]


def test_ui_intent_http_endpoint_routes_to_bus():
    from minder_python_sdk.envelope import EventEnvelope

    conn = _catalog_conn()
    seen: list[EventEnvelope] = []
    conn.on_event(seen.append)
    client = TestClient(conn.asgi())
    r = client.post(
        "/connector/ui/intent",
        json={"session_id": "sess", "intent": fill("add_product", {"sku": "ABC"})},
    )
    assert r.json()["ok"] is True
    ui_intent_events = [e for e in seen if e.type == "ui.intent" and e.session_id == "sess"]
    assert ui_intent_events, "expected a ui.intent envelope for session 'sess'"
    assert ui_intent_events[-1].payload["intent"]["values"]["sku"] == "ABC"
