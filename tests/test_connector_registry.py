from minder.core.modules.registry import (
    ConnectorState,
    ModuleRegistry,
    RECONCILE_FAIL_LIMIT,
)


def _reg(tmp_path):
    (tmp_path / "m").mkdir()
    return ModuleRegistry(tmp_path)


def test_register_connector_is_pending_and_bumps_version(tmp_path):
    reg = _reg(tmp_path)
    v0 = reg.version
    reg.register_connector(name="m", connector_url="http://m:9200")
    assert reg.version == v0 + 1
    rec = reg.connector_records()[0]
    assert rec.state is ConnectorState.PENDING
    assert reg.connector_tools("m") == []  # not READY yet


def test_mark_ready_exposes_tools_and_bumps_on_change(tmp_path):
    reg = _reg(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    v1 = reg.version
    tools = [{"name": "m_query", "parameters": {"type": "object"}}]
    reg.mark_connector_ready("m", tools)
    assert reg.version == v1 + 1
    assert reg.connector_tools("m") == tools
    # Idempotent: same tools + state → no version bump.
    v2 = reg.version
    reg.mark_connector_ready("m", tools)
    assert reg.version == v2


def test_health_failures_flip_to_down_and_hide_tools(tmp_path):
    reg = _reg(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready("m", [{"name": "m_query"}])
    for _ in range(RECONCILE_FAIL_LIMIT):
        reg.record_health_failure("m")
    rec = reg.connector_records()[0]
    assert rec.state is ConnectorState.DOWN
    assert reg.connector_tools("m") == []


def test_live_service_modules_tracks_ready_state(tmp_path):
    reg = _reg(tmp_path)
    reg._modules["m"] = object()  # stand-in guidance Module keyed by name
    reg.register_connector(name="m", connector_url="http://m:9200")
    assert reg.live_service_modules() == []          # PENDING → not live
    reg.mark_connector_ready("m", [])
    assert reg.live_service_modules() == [reg._modules["m"]]
    reg.mark_connector_down("m")
    assert reg.live_service_modules() == []


def test_mark_connector_ready_stores_context_block(tmp_path):
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready(
        "m",
        [{"name": "m_tool"}],
        context={"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]},
    )
    rec = reg.connector("m")
    assert rec.context == {"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]}


def test_mark_connector_ready_defaults_context_to_empty_dict(tmp_path):
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready("m", [{"name": "m_tool"}])  # no context arg
    assert reg.connector("m").context == {}
