# tests/knowledge/test_web_routes.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from minder.web.routes.knowledge import build_router


class FakeService:
    async def list_documents(self, tenant_id):
        return [{"id": 1, "title": "Doc", "status": "ready", "category": "reference_docs"}]

    async def drain_queue(self, batch=5):
        return 2


def test_list_documents_endpoint():
    app = FastAPI()
    app.include_router(
        build_router(service_factory=lambda: FakeService(), tenant_factory=lambda req: "t1",
                     seed_scan=lambda: 3)
    )
    client = TestClient(app)
    resp = client.get("/knowledge/documents")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Doc"


def test_rescan_endpoint_reports_counts():
    app = FastAPI()
    app.include_router(
        build_router(service_factory=lambda: FakeService(), tenant_factory=lambda req: "t1",
                     seed_scan=lambda: 3)
    )
    client = TestClient(app)
    resp = client.post("/knowledge/rescan")
    assert resp.json() == {"enqueued": 3, "processed": 2}
