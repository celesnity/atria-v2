"""Knowledge facade: COP envelope, per-request identity, RBAC behavior (live data)."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    ),
    reason="needs live Postgres, Qdrant and an embedding key",
)


@pytest.fixture(scope="module")
def client():
    from minder.web.facade.knowledge_router import knowledge_facade_router

    app = FastAPI()
    app.include_router(knowledge_facade_router)
    return TestClient(app)


def _search(client, keyword, user_id=None, page_size=5):
    headers = {"X-User-Id": user_id} if user_id else {}
    return client.post(
        "/cop/aiwsp/knowledge/search",
        json={
            "example": {"keyword": keyword},
            "pageInfo": {"pageSize": page_size, "currentPage": 0},
        },
        headers=headers,
    )


def test_envelope_and_hit_shape(client):
    resp = _search(client, "chính sách thử việc", user_id="U001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success" and body["message"] == "SUCCESS"
    assert "requestId" in body
    hits = body["body"]["result"]
    assert hits, "HR user must find the probation policy"
    assert {"documentId", "title", "snippet", "department", "classification", "score"} <= set(
        hits[0]
    )


def test_missing_keyword_is_invalid_request(client):
    resp = client.post("/cop/aiwsp/knowledge/search", json={"example": {}})
    assert resp.status_code == 400
    assert resp.json()["status"] == "error"
    assert resp.json()["code"] == "invalid_request"


def test_rbac_withheld_for_outsider(client):
    # U004 (Engineering employee) asking for executive strategy content:
    resp = _search(client, "ưu tiên chiến lược của công ty năm 2026", user_id="U004")
    body = resp.json()["body"]
    assert body["withheldCount"] >= 1
    assert all(h["classification"] not in ("Restricted",) for h in body["result"])
    note = body["note"] or ""
    assert "withheld" in note


def test_executive_sees_it_with_no_withheld(client):
    resp = _search(client, "ưu tiên chiến lược của công ty năm 2026", user_id="U007")
    body = resp.json()["body"]
    assert body["withheldCount"] == 0
    assert any(h["documentId"] == "DOC036" for h in body["result"])


def test_anonymous_degrades_to_most_restrictive(client):
    resp = _search(client, "khung lương Product Manager")
    body = resp.json()["body"]
    assert all(h["classification"] in ("Public", "Internal") for h in body["result"])
