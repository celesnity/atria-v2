"""Geo-aware hybrid search provider over the Track 8 POI corpus."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import distance_decay, haversine_km  # noqa: E402

from atria.core.context_engineering.search import pg  # noqa: E402
from atria.core.context_engineering.search.dense import DenseIndex  # noqa: E402
from atria.core.context_engineering.search.embedder import Embedder  # noqa: E402
from atria.core.context_engineering.search.fusion import (  # noqa: E402
    facet_counts,
    rrf_fuse,
    top_margin,
)
from atria.core.context_engineering.search.normalize import normalize_for_search  # noqa: E402
from atria.core.context_engineering.search.provider import SearchProvider  # noqa: E402
from atria.core.context_engineering.search.types import (  # noqa: E402
    SearchContext,
    SearchHit,
    SourceResults,
)

_RECALL = 30
_DEFAULT_RADIUS_M = 5000.0
_COLLECTION = "poi_places"
_HARD_FILTER_COLUMNS = ("category", "city", "district")


class PlacesProvider(SearchProvider):
    """Hybrid POI retrieval with optional hard filters and geo re-ranking."""

    name = "places"
    description = (
        "Vietnamese points of interest (cafes, restaurants, hotels, parks, "
        "hospitals, attractions...) across major cities, with attributes, "
        "ratings and coordinates. Supports proximity search via `near`."
    )
    filter_schema: dict[str, Any] = {
        "category": {
            "type": "string",
            "description": "Vietnamese category label, e.g. 'Quán cà phê', 'Nhà hàng', "
            "'Khách sạn'. See result facets for valid values.",
        },
        "city": {"type": "string", "description": "City, e.g. 'Hà Nội', 'TP.HCM', 'Đà Nẵng'."},
        "district": {"type": "string", "description": "District, e.g. 'Quận 1', 'Hoàn Kiếm'."},
        "near": {
            "type": "object",
            "description": "Focus point {lat, lon} for proximity ranking.",
            "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
        },
        "radius_m": {
            "type": "number",
            "description": f"Max distance from `near` in meters (default {int(_DEFAULT_RADIUS_M)}).",
        },
    }

    def __init__(self) -> None:
        """Initialize the embedder and dense index used for recall."""
        self._embedder = Embedder()
        self._dense = DenseIndex(_COLLECTION)

    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        """Run geo-aware hybrid search over the POI corpus.

        Recalls candidates independently over lexical (Postgres full-text
        search) and dense (Qdrant vector similarity) channels, applying the
        same hard filters (`category`, `city`, `district`) to both, fuses
        them with reciprocal-rank fusion, then re-ranks by an optional
        proximity boost (when `near` is given, POIs are also hard-excluded
        beyond `radius_m`) and a rating prior that favors highly-rated POIs
        without letting an unrated POI be penalized.

        Args:
            query: Free-text search query (Vietnamese or diacritics-stripped
                Vietnamese; normalized identically to the indexed content).
            filters: Model-controllable relevance filters. `category`,
                `city`, and `district` are hard equality filters applied at
                recall time on both channels. `near` (`{lat, lon}`) and
                `radius_m` (meters, default `_DEFAULT_RADIUS_M`) enable a
                post-recall proximity boost and radius cutoff; `radius_m` is
                only meaningful together with `near`.
            limit: Maximum number of hits to return.
            context: Runtime-injected search context. Unused by this
                provider — places carry no per-user access policy.

        Returns:
            SourceResults with hits ranked by fused-and-boosted score, each
            annotated with place metadata (and `distance_m` when `near` was
            given), category/city/district facets over the returned hits, a
            top_margin ambiguity signal, and a `note` when nothing matched.
        """
        near = filters.get("near") or None
        radius_m = float(filters.get("radius_m") or _DEFAULT_RADIUS_M)

        # --- lexical recall ---
        params: list[Any] = [normalize_for_search(query)]
        where = ["tsv @@ websearch_to_tsquery('simple', $1)"]
        for column in _HARD_FILTER_COLUMNS:
            if filters.get(column):
                params.append(filters[column])
                where.append(f"{column} = ${len(params)}")
        lexical_rows = pg.fetch_all(
            "SELECT poi_id, name, category, city, district, address, lat, lon, rating, "
            "popularity, description, "
            "ts_rank_cd(tsv, websearch_to_tsquery('simple', $1)) AS rank "
            f"FROM pois WHERE {' AND '.join(where)} ORDER BY rank DESC LIMIT {_RECALL}",
            params,
        )

        # --- dense recall ---
        from qdrant_client import models

        must: list[models.Condition] = [
            models.FieldCondition(key=column, match=models.MatchValue(value=filters[column]))
            for column in _HARD_FILTER_COLUMNS
            if filters.get(column)
        ]
        dense_filter = models.Filter(must=must) if must else None
        vector = self._embedder.embed([query])[0]
        dense_hits = self._dense.query(vector, query_filter=dense_filter, limit=_RECALL)

        # --- fuse and hydrate ---
        fused = rrf_fuse([[r["poi_id"] for r in lexical_rows], [h[0] for h in dense_hits]])
        by_id = {r["poi_id"]: r for r in lexical_rows}
        missing = [pid for pid in fused if pid not in by_id]
        if missing:
            rows = pg.fetch_all(
                "SELECT poi_id, name, category, city, district, address, lat, lon, rating, "
                "popularity, description FROM pois WHERE poi_id = ANY($1::text[])",
                [missing],
            )
            by_id.update({r["poi_id"]: r for r in rows})

        # --- geo re-rank + rating prior ---
        scored: list[tuple[float, dict[str, Any], float | None]] = []
        for poi_id, base in fused.items():
            row = by_id.get(poi_id)
            if row is None:
                continue
            score = base
            distance_m: float | None = None
            if near:
                km = haversine_km(
                    float(near["lat"]), float(near["lon"]), float(row["lat"]), float(row["lon"])
                )
                distance_m = km * 1000.0
                if distance_m > radius_m:
                    continue
                score *= distance_decay(km)
            rating = float(row["rating"] or 0.0)
            if rating > 0:
                score *= 0.6 + rating / 10.0
            scored.append((score, row, distance_m))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:limit]
        hits = []
        for score, row, distance_m in top:
            metadata: dict[str, Any] = {
                "category": row["category"],
                "city": row["city"],
                "district": row["district"],
                "address": row["address"],
                "lat": row["lat"],
                "lon": row["lon"],
                "rating": row["rating"],
            }
            if distance_m is not None:
                metadata["distance_m"] = round(distance_m)
            hits.append(
                SearchHit(
                    id=str(row["poi_id"]),
                    source=self.name,
                    title=str(row["name"]),
                    snippet=str(row["description"] or "")[:250],
                    score=score,
                    metadata=metadata,
                )
            )
        facet_rows = [
            {"category": row["category"], "city": row["city"], "district": row["district"]}
            for _, row, _ in top
        ]
        return SourceResults(
            source=self.name,
            hits=hits,
            facets=facet_counts(facet_rows, ["category", "city", "district"]),
            top_margin=top_margin([h.score for h in hits]),
            note=None if hits else "No places matched; try relaxing filters or radius.",
        )


def get_provider() -> PlacesProvider:
    """Module discovery entry point.

    Returns:
        A new PlacesProvider instance, used by `discover_module_providers`
        to register this module's search provider.
    """
    return PlacesProvider()
