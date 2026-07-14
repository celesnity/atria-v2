"""Tests for readiness-aware gating in ConnectorReconciler.reconcile_once.

A connector whose health() reports ok=True but ready=False must remain PENDING
(tools stay out of the catalog, no health-failure recorded).
A connector reporting ok=True, ready=True must transition to READY.
"""

from minder.core.modules import watcher
from minder.core.modules.registry import ConnectorState, get_registry, reset_registry_for_tests


class _FakeConn:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    def fetch_manifest(self):
        return {"tools": [{"name": "m_q"}]}

    def health(self, timeout: float = 2.0):
        return {"ok": True, "ready": self._ready}

    def is_healthy(self, timeout: float = 2.0) -> bool:
        return True


def _reg(monkeypatch, tmp_path, ready: bool):
    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    monkeypatch.setattr(watcher, "RemoteConnector", lambda *a, **k: _FakeConn(ready))
    return reg


def test_not_ready_stays_pending(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path, ready=False)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.PENDING


def test_ready_goes_ready(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path, ready=True)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.READY
