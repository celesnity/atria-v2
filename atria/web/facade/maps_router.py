"""Tasco Maps hackathon API facade over the maps_search provider.

Implements the documented surface: /v1/search, /v1/autocomplete,
/v1/nearby-search, /v1/poi/{id} (plus doc-listed aliases). /v1/route and
geocoding are deliberately deferred and return the documented
service_unavailable ErrorResponse.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Request

from atria.core.context_engineering.search import pg
from atria.core.context_engineering.search.registry import discover_module_providers
from atria.core.modules.registry import resolve_modules_root
from atria.core.context_engineering.search.types import SearchContext, SearchHit
from atria.web.facade.common import error_response, facade_guard

maps_facade_router = APIRouter(tags=["maps-facade"])

_MAX_LIMIT = 20


@lru_cache(maxsize=1)
def _places_provider() -> Any:
    registry = discover_module_providers(resolve_modules_root())
    provider = registry.get("places")
    if provider is None:
        raise RuntimeError("places provider not registered (is modules/maps_search present?)")
    return provider


def _place_result(hit: SearchHit) -> dict[str, Any]:
    md = hit.metadata or {}
    result: dict[str, Any] = {
        "id": f"poi:{hit.id}",
        "type": "poi",
        "name": hit.title,
        "label": hit.title,
        "address": md.get("address"),
        "category": md.get("category"),
        "coordinates": {"lat": md.get("lat"), "lon": md.get("lon")},
        "score": round(float(hit.score), 4),
        "source": "atria",
    }
    if md.get("distance_m") is not None:
        result["distanceMeters"] = int(md["distance_m"])
    return result


def _run_search(
    q: str,
    lat: float | None,
    lon: float | None,
    radius_meters: float | None,
    category: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if lat is not None and lon is not None:
        filters["near"] = {"lat": lat, "lon": lon}
        if radius_meters:
            filters["radius_m"] = radius_meters
    if category:
        filters["category"] = category
    results = _places_provider().search(q, filters, min(limit, _MAX_LIMIT), SearchContext())
    return [_place_result(h) for h in results.hits]


@maps_facade_router.get("/v1/search")
@maps_facade_router.get("/search")
@maps_facade_router.get("/v1/geocode-search")
@facade_guard
def search(
    request: Request,
    q: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radiusMeters: float | None = None,
    category: str | None = None,
    limit: int = 10,
    lang: str = "vi",
) -> Any:
    if not q:
        return error_response(400, "invalid_request", "q is required", {"field": "q"}, request)
    results = _run_search(q, lat, lon, radiusMeters, category, limit)
    return {"query": q, "results": results, "meta": {"limit": limit, "lang": lang}}


@maps_facade_router.get("/v1/autocomplete")
@maps_facade_router.get("/autocomplete")
@facade_guard
def autocomplete(
    request: Request,
    q: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    limit: int = 5,
    sessionId: str | None = None,
    lang: str = "vi",
) -> Any:
    if not q:
        return error_response(400, "invalid_request", "q is required", {"field": "q"}, request)
    results = _run_search(q, lat, lon, None, None, min(limit, 10))
    return {
        "query": q,
        "suggestions": results,
        "meta": {"limit": limit, "sessionId": sessionId},
    }


@maps_facade_router.get("/v1/nearby-search")
@maps_facade_router.get("/nearby-search")
@facade_guard
def nearby_search(
    request: Request,
    lat: float | None = None,
    lon: float | None = None,
    radiusMeters: float = 1000,
    category: str | None = None,
    openNow: bool | None = None,
    limit: int = 10,
    lang: str = "vi",
) -> Any:
    if lat is None or lon is None:
        return error_response(
            400, "invalid_request", "lat and lon are required", {"fields": ["lat", "lon"]}, request
        )
    query = category or "địa điểm"
    results = _run_search(query, lat, lon, radiusMeters, category, limit)
    return {
        "center": {"lat": lat, "lon": lon},
        "results": results,
        "meta": {"radiusMeters": radiusMeters, "limit": limit},
    }


@maps_facade_router.get("/v1/poi/{poi_id}")
@maps_facade_router.get("/poi/{poi_id}")
@facade_guard
def poi_detail(poi_id: str, request: Request, lang: str = "vi", include: str | None = None) -> Any:
    raw_id = poi_id.removeprefix("poi:")
    rows = pg.fetch_all(
        "SELECT poi_id, name, category, brand, city, district, address, lat, lon, "
        "rating, review_count, attributes, tags, description "
        "FROM pois WHERE poi_id = $1",
        [raw_id],
    )
    if not rows:
        return error_response(404, "not_found", f"POI {poi_id} not found", None, request)
    row = rows[0]
    tags = [t.strip() for t in str(row["tags"] or "").split(";") if t.strip()]
    return {
        "poi": {
            "id": f"poi:{row['poi_id']}",
            "type": "poi",
            "name": row["name"],
            "label": row["name"],
            "address": row["address"],
            "category": row["category"],
            "coordinates": {"lat": row["lat"], "lon": row["lon"]},
            "rating": row["rating"],
            "aiSummary": (row["description"] or "")[:300] or None,
            "tags": tags,
            "source": "atria",
        }
    }


@maps_facade_router.get("/v1/route")
@maps_facade_router.get("/route")
@maps_facade_router.get("/v1/geocoding")
@maps_facade_router.get("/v1/reverse-geocoding")
@maps_facade_router.get("/v1/reverse")
def deferred_endpoints(request: Request) -> Any:
    return error_response(
        503,
        "service_unavailable",
        "This capability ships with the routing/geocoding facade (deferred).",
        None,
        request,
    )
