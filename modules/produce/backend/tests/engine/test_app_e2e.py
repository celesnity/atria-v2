"""End-to-end over real HTTP (TestClient): seed -> claim -> execute -> dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from engine import db
from engine.core import grant, scope


@pytest.fixture()
def client():
    from engine.app import create_app

    app = create_app()
    # startup lifespan runs init_db + seed against the SQLite engine from conftest.
    with TestClient(app) as c:
        # grant the dev principal supervisor rights on the whole site
        with db.db_session() as s:
            sc = scope.create(s, "site", kind="site", name="site")
            s.flush()
            s.add(grant.PrGrant(subject="dev", role="supervisor", scope_id=sc.id))
        yield c


def test_full_slice_over_http(client):
    # workflow_version_id 1 was seeded on startup
    wi = client.post("/work-items",
                     json={"workflow_version_id": 1, "scope_path": "site/lineA/res1"}).json()
    assert client.post(f"/work-items/{wi['id']}/claim").json()["status"] == "claimed"

    for key, data in (("prepare", {}), ("measure", {"value": 5}), ("finish", {})):
        run = client.post(f"/work-items/{wi['id']}/steps/{key}/start").json()
        out = client.post(f"/step-runs/{run['step_run_id']}/output", json={"data": data})
        assert out.status_code == 200, out.text

    # threshold breach is blocked (422)
    wi2 = client.post("/work-items",
                      json={"workflow_version_id": 1, "scope_path": "site/lineA/res1"}).json()
    client.post(f"/work-items/{wi2['id']}/claim")
    client.post(f"/work-items/{wi2['id']}/steps/prepare/start")
    run2 = client.post(f"/work-items/{wi2['id']}/steps/measure/start")
    # prepare must complete first — start measure should 409 until prepare submitted
    assert run2.status_code == 409

    dash = client.get("/dashboard", params={"scope_path": "site", "target": 1}).json()
    assert dash["throughput"] == 1
