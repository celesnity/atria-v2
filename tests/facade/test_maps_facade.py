"""Maps facade endpoints return the documented PlaceResult/ErrorResponse shapes (live data)."""

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

PLACE_RESULT_KEYS = {
    "id",
    "type",
    "name",
    "label",
    "address",
    "category",
    "coordinates",
    "score",
    "source",
}


@pytest.fixture(scope="module")
def client():
    from minder.web.facade.maps_router import maps_facade_router

    app = FastAPI()
    app.include_router(maps_facade_router)
    return TestClient(app)


def test_search_returns_place_results(client):
    resp = client.get("/v1/search", params={"q": "Hồ Hoàn Kiếm", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "Hồ Hoàn Kiếm"
    assert body["results"], "expected at least one hit for a known POI"
    first = body["results"][0]
    assert PLACE_RESULT_KEYS <= set(first)
    assert first["id"].startswith("poi:")
    assert set(first["coordinates"]) == {"lat", "lon"}


def test_search_with_focus_point_adds_distance(client):
    resp = client.get(
        "/v1/search",
        params={"q": "cà phê", "lat": 21.0285, "lon": 105.8542, "limit": 5},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results and any("distanceMeters" in r for r in results)


def test_search_missing_q_is_invalid_request(client):
    resp = client.get("/v1/search")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert "requestId" in body


def test_autocomplete_shape(client):
    resp = client.get("/v1/autocomplete", params={"q": "Hồ", "limit": 3, "sessionId": "s-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert "suggestions" in body and body["meta"]["sessionId"] == "s-1"


def test_nearby_search_requires_center_and_returns_center(client):
    assert client.get("/v1/nearby-search").status_code == 400
    resp = client.get(
        "/v1/nearby-search",
        params={"lat": 21.0285, "lon": 105.8542, "radiusMeters": 3000, "limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["center"] == {"lat": 21.0285, "lon": 105.8542}


def test_poi_detail_and_not_found(client):
    hit = client.get("/v1/search", params={"q": "Hồ Hoàn Kiếm", "limit": 1}).json()["results"][0]
    resp = client.get(f"/v1/poi/{hit['id']}")
    assert resp.status_code == 200
    poi = resp.json()["poi"]
    assert poi["id"] == hit["id"] and "rating" in poi
    missing = client.get("/v1/poi/poi:does-not-exist-xyz")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_route_is_documented_unavailable(client):
    resp = client.get("/v1/route", params={"from": "a", "to": "b"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "service_unavailable"


def test_search_backend_failure_returns_service_unavailable(client, monkeypatch):
    import minder.web.facade.maps_router as maps_router

    monkeypatch.setattr(
        maps_router,
        "_places_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    resp = client.get("/v1/search", params={"q": "x"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "service_unavailable"
