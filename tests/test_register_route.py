import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.core.modules.registry import ConnectorState, reset_registry_for_tests, get_registry
from atria.web.dependencies.service_auth import require_module_register
from atria.web.routes.module_connector import router


@pytest.fixture
def client(monkeypatch, tmp_path):
    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_module_register] = lambda: {"client_id": "atria-module", "roles": ["module-register"]}
    return TestClient(app)


def test_register_creates_pending_connector(client):
    r = client.post("/api/modules/register", json={
        "module": "m", "connector_url": "http://m:9200",
        "remote_entry": "http://localhost:9200/dashboard/remoteEntry.js",
    })
    assert r.status_code == 200 and r.json() == {"ok": True}
    rec = get_registry().connector_records()[0]
    assert rec.name == "m" and rec.state is ConnectorState.PENDING


def test_deregister_marks_down(client):
    client.post("/api/modules/register", json={"module": "m", "connector_url": "http://m:9200"})
    get_registry().mark_connector_ready("m", [{"name": "m_q"}])
    r = client.post("/api/modules/deregister", json={"module": "m"})
    assert r.status_code == 204
    assert get_registry().connector_records()[0].state is ConnectorState.DOWN
