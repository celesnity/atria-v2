from types import SimpleNamespace

from minder_python_sdk.context import (
    MAX_STATE_CHARS,
    Note,
    _ContextRegistrar,
    build_state_entries,
    cap_value,
)


def _owner():
    return SimpleNamespace(_ctx_state={}, _ctx_knowledge=[], _ctx_notes=[])


def test_state_decorator_registers_provider_and_returns_fn():
    owner = _owner()
    reg = _ContextRegistrar(owner)

    @reg.state("inventory", "Current stock")
    def inv():
        return {"in_stock": 42}

    assert inv() == {"in_stock": 42}  # returned unchanged
    assert owner._ctx_state["inventory"].description == "Current stock"


def test_knowledge_ignores_blank_and_appends():
    owner = _owner()
    reg = _ContextRegistrar(owner)
    reg.knowledge("  ")
    reg.knowledge(" Always check MEL. ")
    assert owner._ctx_knowledge == ["Always check MEL."]


def test_note_dedupes_by_name():
    owner = _owner()
    reg = _ContextRegistrar(owner)
    reg.note("products", "old")
    reg.note("products", "new")
    reg.note("", "ignored")
    assert owner._ctx_notes == [Note(name="products", text="new")]


def test_build_state_entries_evaluates_live_and_injects_principal():
    seen = {}

    def inv(principal=None):
        seen["p"] = principal
        return {"in_stock": 42}

    providers = {"inventory": _StateProvider_desc(inv, "stock")}
    out = build_state_entries(providers, principal="alice", session_id="s1")
    assert out == [{"name": "inventory", "description": "stock", "value": {"in_stock": 42}}]
    assert seen["p"] == "alice"


def test_build_state_entries_is_fail_closed_per_entry():
    def boom():
        raise RuntimeError("nope")

    def ok():
        return 1

    providers = {
        "bad": _StateProvider_desc(boom, ""),
        "good": _StateProvider_desc(ok, ""),
    }
    out = build_state_entries(providers, principal=None, session_id=None)
    assert [e["name"] for e in out] == ["good"]  # bad skipped, good survives


def test_cap_value_truncates_oversized():
    big = "x" * (MAX_STATE_CHARS + 10)
    value, truncated = cap_value(big)
    assert truncated is True and len(value) == MAX_STATE_CHARS


def test_build_state_entries_flags_truncated():
    def big():
        return "y" * (MAX_STATE_CHARS + 5)

    out = build_state_entries({"b": _StateProvider_desc(big, "")}, None, None)
    assert out[0]["truncated"] is True


# Helper: construct a _StateProvider without importing its private name everywhere.
def _StateProvider_desc(fn, description):
    from minder_python_sdk.context import _StateProvider

    return _StateProvider(description=description, fn=fn)


def test_context_endpoint_returns_live_state_with_principal():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.context.state("whoami", "Who is asking")
    def whoami(principal=None):
        return {"user": getattr(principal, "username", None)}

    client = TestClient(conn.asgi())
    body = client.get(
        "/connector/context",
        headers={"X-Minder-Principal": '{"username": "alice"}'},
    ).json()
    assert {"name": "whoami", "description": "Who is asking", "value": {"user": "alice"}} in body[
        "state"
    ]


def test_context_state_defaults_to_empty_list():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")
    body = TestClient(conn.asgi()).get("/connector/context").json()
    assert body["state"] == []


def test_manifest_exposes_knowledge_and_notes():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")
    conn.context.knowledge("Always check MEL before dispatch.")
    conn.context.note("products", "Product catalog area.")

    mani = TestClient(conn.asgi()).get("/connector/manifest").json()
    assert mani["context"]["knowledge"] == ["Always check MEL before dispatch."]
    assert mani["context"]["notes"] == [{"name": "products", "text": "Product catalog area."}]


def test_manifest_context_defaults_empty():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    mani = TestClient(Connector("m").asgi()).get("/connector/manifest").json()
    assert mani["context"] == {"knowledge": [], "notes": []}


def test_tool_enrichment_surfaces_in_manifest():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.tool(
        "create_product",
        risk="medium",
        when_to_use="When the user wants a new product and has SKU + price",
        examples=[{"sku": "A-1", "name": "Pump", "price": 9.9}],
    )
    def create_product(sku: str, name: str, price: float, **kw):
        return {"output": "ok"}

    @conn.read("list_products", description="List products")
    def list_products():
        return {"output": []}

    tools = {t["name"]: t for t in TestClient(conn.asgi()).get("/connector/manifest").json()["tools"]}
    assert tools["create_product"]["when_to_use"].startswith("When the user")
    assert tools["create_product"]["examples"] == [{"sku": "A-1", "name": "Pump", "price": 9.9}]
    # Unset tool has empty defaults, not missing keys.
    assert tools["list_products"]["when_to_use"] == ""
    assert tools["list_products"]["examples"] == []


def test_enriched_tool_still_invokes_and_gates_normally():
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.tool("echo", when_to_use="whenever", examples=[{"q": "hi"}])
    def echo(q: str = ""):
        return {"output": q.upper()}

    assert conn.invoke("echo", {"q": "hi"})["output"] == "HI"
