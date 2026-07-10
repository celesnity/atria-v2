from atria.core.modules import watcher
from atria.core.modules.registry import (
    ConnectorState, ModuleRegistry, RECONCILE_FAIL_LIMIT, reset_registry_for_tests,
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
