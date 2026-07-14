"""Agent-facing surface (contract v3): risk gate, dry-run, idempotency,
structured errors, event envelope, autonomy/context, declared events, reads."""

import httpx
import pytest
from fastapi.testclient import TestClient

from minder_module_sdk import Connector, ToolError, EventEnvelope, autonomy_allows
from minder_module_sdk.connector import Principal


# --- C2: risk gate ----------------------------------------------------------


def test_high_risk_action_is_gated_below_autonomy():
    conn = Connector("m")
    ran = {"v": False}

    @conn.tool("scrap_part", risk="high", reversible=False)
    def scrap_part(part: str = ""):
        ran["v"] = True
        return {"output": "scrapped"}

    out = conn.invoke("scrap_part", {"part": "X"}, autonomy="low")
    assert ran["v"] is False  # NOT executed
    assert out["requires_approval"] is True
    assert out["card"]["card_type"] == "decision_packet"
    assert out["card"]["risk"] == "high"


def test_action_runs_when_autonomy_allows():
    conn = Connector("m")

    @conn.tool("scrap_part", risk="high")
    def scrap_part(part: str = ""):
        return {"output": "scrapped"}

    out = conn.invoke("scrap_part", {"part": "X"}, autonomy="high")
    assert out["success"] is True and out["output"] == "scrapped"


def test_read_only_is_never_gated():
    conn = Connector("m")

    @conn.read("queue_depth")
    def queue_depth():
        return {"output": 7}

    out = conn.invoke("queue_depth", {}, autonomy="none")
    assert out["output"] == 7
    assert conn._tools["queue_depth"].risk == "none"


def test_autonomy_allows_ladder():
    assert autonomy_allows("low", "medium") is True
    assert autonomy_allows("critical", "high") is False
    assert autonomy_allows("none", "none") is True


# --- C3: dry-run ------------------------------------------------------------


def test_dry_run_without_handler_support_does_not_execute():
    conn = Connector("m")
    ran = {"v": False}

    @conn.tool("ship", risk="medium")
    def ship(id: int = 0):
        ran["v"] = True
        return {"output": "shipped"}

    out = conn.invoke("ship", {"id": 1}, autonomy="high", dry_run=True)
    assert ran["v"] is False
    assert out["dry_run"] is True
    assert "[dry-run]" in out["output"]


def test_dry_run_passed_to_aware_handler():
    conn = Connector("m")

    @conn.tool("ship", risk="medium")
    def ship(id: int = 0, dry_run: bool = False):
        return {"output": "preview" if dry_run else "shipped"}

    assert conn.invoke("ship", {"id": 1}, autonomy="high", dry_run=True)["output"] == "preview"


# --- C4: idempotency --------------------------------------------------------


def test_idempotent_retry_returns_cached_result():
    conn = Connector("m")
    calls = {"n": 0}

    @conn.tool("charge", risk="medium", idempotent=True)
    def charge(**kwargs):
        calls["n"] += 1
        return {"output": calls["n"]}

    a = conn.invoke("charge", {}, autonomy="high", request_key="k1")
    b = conn.invoke("charge", {}, autonomy="high", request_key="k1")
    assert a["output"] == b["output"] == 1
    assert calls["n"] == 1  # handler ran once


def test_non_idempotent_tool_ignores_request_key():
    conn = Connector("m")
    calls = {"n": 0}

    @conn.tool("act")
    def act(**kwargs):
        calls["n"] += 1
        return {"output": calls["n"]}

    conn.invoke("act", {}, request_key="k1")
    conn.invoke("act", {}, request_key="k1")
    assert calls["n"] == 2


# --- E2: structured errors --------------------------------------------------


def test_tool_error_produces_structured_error():
    conn = Connector("m")

    @conn.tool("dispatch")
    def dispatch(**kwargs):
        raise ToolError("mel_expired", "MEL item expired", retryable=False, details={"item": "34"})

    out = conn.invoke("dispatch", {})
    assert out["success"] is False
    assert out["error"]["code"] == "mel_expired"
    assert out["error"]["retryable"] is False
    assert out["error"]["details"]["item"] == "34"


# --- E1/E3: event envelope + actor ------------------------------------------


def test_action_auto_emits_invoked_and_completed():
    conn = Connector("m")
    seen: list[EventEnvelope] = []
    conn.on_event(seen.append)

    @conn.tool("act", risk="low")
    def act(**kwargs):
        return {"output": "ok"}

    conn.invoke("act", {}, agent_id="agent-7", principal=Principal("alice", "a@x"))
    types = [e.type for e in seen]
    assert types == ["action.invoked", "action.completed"]
    assert seen[0].actor["kind"] == "agent"
    assert seen[0].actor["agent_id"] == "agent-7"
    assert seen[0].actor["on_behalf_of"] == "alice"


def test_reads_do_not_emit_action_events():
    conn = Connector("m")
    seen = []
    conn.on_event(seen.append)

    @conn.read("status")
    def status():
        return {"output": "green"}

    conn.invoke("status", {})
    assert seen == []


def test_manual_emit_event_dispatches():
    conn = Connector("m")
    seen = []
    conn.on_event(seen.append)
    env = conn.emit_event("queue.changed", {"depth": 4}, session_id="s1")
    assert env.type == "queue.changed"
    assert seen[0].payload["depth"] == 4


# --- A1/B2: declared events in manifest -------------------------------------


def test_declared_events_show_in_manifest():
    conn = Connector("m")
    conn.event("queue.changed", description="queue moved", schema={"type": "object"})

    @conn.tool("act")
    def act():
        return {}

    mani = TestClient(conn.asgi()).get("/connector/manifest").json()
    assert mani["events"][0]["type"] == "queue.changed"
    assert mani["tools"][0]["risk"] == "low"
    assert mani["default_autonomy"] == "high"


# --- A3/A5: context endpoint ------------------------------------------------


def test_context_endpoint_reports_autonomy_and_allowed_actions():
    conn = Connector("m")

    @conn.tool("safe", risk="low")
    def safe():
        return {}

    @conn.tool("danger", risk="critical")
    def danger():
        return {}

    client = TestClient(conn.asgi())
    r = client.get("/connector/context", headers={"X-Minder-Autonomy": "low"})
    body = r.json()
    assert body["autonomy"] == "low"
    allowed = {a["name"]: a["allowed"] for a in body["actions"]}
    assert allowed == {"safe": True, "danger": False}


def test_principal_parses_roles_and_scopes():
    import json

    conn = Connector("m")

    @conn.tool("who")
    def who(principal):
        return {"output": principal.scopes}

    client = TestClient(conn.asgi())
    hdr = json.dumps({"username": "bob", "roles": ["engineer"], "scopes": ["dispatch"]})
    r = client.post(
        "/connector/tools/who", json={"arguments": {}}, headers={"X-Minder-Principal": hdr}
    )
    assert r.json()["output"] == ["dispatch"]


# --- gate over HTTP end-to-end ----------------------------------------------


def test_approved_decision_reinvokes_gated_action():
    conn = Connector("m")
    ran = {"v": False}

    @conn.tool("scrap", risk="critical")
    def scrap(part: str = ""):
        ran["v"] = True
        return {"output": f"scrapped {part}"}

    client = TestClient(conn.asgi())
    # Human approves the previously-gated action → it now runs.
    r = client.post(
        "/connector/decision",
        json={"verdict": "approve", "action": "scrap", "arguments": {"part": "X"}},
    )
    assert ran["v"] is True
    assert r.json()["output"] == "scrapped X"


def test_rejected_decision_does_not_run():
    conn = Connector("m")
    ran = {"v": False}

    @conn.tool("scrap", risk="critical")
    def scrap(part: str = ""):
        ran["v"] = True
        return {}

    out = conn.apply_decision({"verdict": "reject", "action": "scrap"})
    assert ran["v"] is False and out["verdict"] == "reject"


def test_custom_decision_handler_receives_decision():
    conn = Connector("m")
    seen = {}

    @conn.on_decision
    def handle(decision, principal):
        seen["d"] = decision
        return "logged"

    out = conn.apply_decision({"verdict": "modify", "action": "x", "arguments": {"a": 1}})
    assert out["output"] == "logged"
    assert seen["d"]["arguments"] == {"a": 1}


def test_http_call_gated_by_autonomy_header():
    conn = Connector("m")

    @conn.tool("delete_all", risk="critical")
    def delete_all():
        return {"output": "boom"}

    client = TestClient(conn.asgi())
    r = client.post(
        "/connector/tools/delete_all",
        json={"arguments": {}},
        headers={"X-Minder-Autonomy": "medium"},
    )
    body = r.json()
    assert body["requires_approval"] is True
    assert body["card"]["action"] == "delete_all"


# --- declarative Agent.* surface: act intent + snapshot cache ----------------


def test_act_is_a_recognized_intent():
    from minder_module_sdk.ui import act, is_intent

    intent = act("products.add")
    assert intent == {"intent": "act", "name": "products.add"}
    assert is_intent(intent) is True


def _client_with_snapshot_module():
    """Build a minimal connector app for the snapshot round-trip test.

    Mirrors how the other tests in this file construct a connector
    (positional ``Connector(name)`` + ``TestClient(conn.asgi())``).
    """
    conn = Connector("snap_demo")
    return TestClient(conn.asgi())


def test_snapshot_round_trips_into_context():
    client = _client_with_snapshot_module()
    snap = {
        "page": "products",
        "data": [{"name": "products.list", "description": "rows", "value": [{"id": 1}]}],
        "actions": [{"name": "products.add", "description": "add"}],
    }
    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "default", "snapshot": snap},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    ctx = client.get("/connector/context").json()
    assert ctx["ui_snapshot"] == snap
