from atria.core.modules import watcher
from atria.core.modules.registry import (
    ConnectorState, RECONCILE_FAIL_LIMIT, reset_registry_for_tests,
)


class _FakeConn:
    def __init__(self, manifest, healthy):
        self._manifest, self._healthy = manifest, healthy
    def fetch_manifest(self):
        return self._manifest
    def is_healthy(self, timeout=2.0):
        return self._healthy


def _install(monkeypatch, tmp_path, manifest, healthy):
    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    from atria.core.modules import registry as reg_mod
    reg = reg_mod.get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    monkeypatch.setattr(watcher, "RemoteConnector",
                        lambda *a, **k: _FakeConn(manifest, healthy))
    return reg


def test_reconcile_marks_ready_with_live_tools(monkeypatch, tmp_path):
    tools = [{"name": "m_q", "parameters": {"type": "object"}}]
    reg = _install(monkeypatch, tmp_path, {"tools": tools}, healthy=True)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.READY
    assert reg.connector_tools("m") == tools


def test_repeated_unhealthy_polls_go_down(monkeypatch, tmp_path):
    reg = _install(monkeypatch, tmp_path, None, healthy=False)
    r = watcher.ConnectorReconciler()
    for _ in range(RECONCILE_FAIL_LIMIT):
        r.reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.DOWN


def test_on_change_fired_when_state_changes(monkeypatch, tmp_path):
    """on_change is called when a reconcile pass changes registry state."""
    tools = [{"name": "m_q", "parameters": {"type": "object"}}]
    _install(monkeypatch, tmp_path, {"tools": tools}, healthy=True)
    fired = []
    r = watcher.ConnectorReconciler(on_change=lambda: fired.append(1))
    r.reconcile_once("m")
    assert fired, "on_change should be called when state flips to READY"


def test_on_change_not_fired_when_state_unchanged(monkeypatch, tmp_path):
    """on_change is NOT called on a no-op reconcile pass (already READY, same tools)."""
    tools = [{"name": "m_q", "parameters": {"type": "object"}}]
    reg = _install(monkeypatch, tmp_path, {"tools": tools}, healthy=True)
    # First pass: PENDING -> READY (state changes, on_change fires — ignore this)
    r = watcher.ConnectorReconciler(on_change=lambda: None)
    r.reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.READY

    # Second pass: already READY with same tools — version should not bump
    fired = []
    r2 = watcher.ConnectorReconciler(on_change=lambda: fired.append(1))
    r2.reconcile_once("m")
    assert not fired, "on_change must not fire when registry version did not change"
