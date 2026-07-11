"""Ingest the Track 8 POI xlsx into Postgres + Qdrant (idempotent).

Usage:
    python modules/maps_search/scripts/ingest.py \
        --xlsx mobility/track8/ai_maps_track3_dataset_participants.xlsx

Reads corpus sheets only (POI_Dataset, User_Preferences). Never reads
held-out evaluation sheets — those are held-out test sets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import openpyxl

# Repo root, so `atria` resolves when this file is run directly (as a script,
# rather than through a test runner that already puts the repo root on
# sys.path). Needed regardless of whether atria is pip-installed editable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from atria.core.context_engineering.search import pg  # noqa: E402
from atria.core.context_engineering.search.dense import DenseIndex  # noqa: E402
from atria.core.context_engineering.search.embedder import Embedder  # noqa: E402
from atria.core.context_engineering.search.normalize import (  # noqa: E402
    normalize_for_search,
)

COLLECTION = "poi_places"

_DDL = [
    """CREATE TABLE IF NOT EXISTS pois(
        poi_id text PRIMARY KEY, name text, category text, brand text,
        city text, district text, address text,
        lat double precision, lon double precision,
        rating real, review_count int, popularity real,
        attributes text, tags text, description text, search_norm text,
        tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('simple', search_norm)) STORED)""",
    "CREATE INDEX IF NOT EXISTS pois_tsv_idx ON pois USING gin(tsv)",
    """CREATE TABLE IF NOT EXISTS map_user_profiles(
        user_id text PRIMARY KEY, persona text, current_location text,
        preferences text, avoid text, budget_level text, notes text)""",
]


def _sheet_rows(workbook: Any, name: str) -> list[dict[str, Any]]:
    """Read a Track 8 sheet (header row 1, data from row 2) into dicts.

    Args:
        workbook: openpyxl workbook object.
        name: Sheet name to read.

    Returns:
        List of dicts mapping column names to values.
    """
    rows = list(workbook[name].iter_rows(values_only=True))
    header = [str(c) for c in rows[0]]
    return [
        {header[i]: raw[i] for i in range(len(header))}
        for raw in rows[1:]
        if raw and any(c is not None for c in raw)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, help="Path to the Track 8 participants xlsx")
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.xlsx, read_only=True)
    pois = _sheet_rows(workbook, "POI_Dataset")
    profiles = _sheet_rows(workbook, "User_Preferences")

    for ddl in _DDL:
        pg.execute(ddl)

    for profile in profiles:
        pg.execute(
            """INSERT INTO map_user_profiles(user_id, persona,
                 current_location, preferences, avoid, budget_level, notes)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               ON CONFLICT (user_id) DO UPDATE SET
                 persona=EXCLUDED.persona,
                 current_location=EXCLUDED.current_location,
                 preferences=EXCLUDED.preferences,
                 avoid=EXCLUDED.avoid, budget_level=EXCLUDED.budget_level,
                 notes=EXCLUDED.notes""",
            [
                str(profile.get(k, "") or "")
                for k in (
                    "user_id",
                    "persona",
                    "current_location",
                    "preferences",
                    "avoid",
                    "budget_level",
                    "notes",
                )
            ],
        )

    ids: list[str] = []
    texts: list[str] = []
    payloads: list[dict[str, Any]] = []
    skipped = 0
    for poi in pois:
        try:
            lat = float(poi["latitude"])
            lon = float(poi["longitude"])
        except (TypeError, ValueError, KeyError):
            print(f"skipping {poi.get('poi_id', '<no id>')}: invalid coordinates")
            skipped += 1
            continue

        searchable = " ".join(
            str(poi.get(field) or "")
            for field in (
                "poi_name",
                "brand",
                "category",
                "attributes",
                "tags",
                "description",
            )
        )
        pg.execute(
            """INSERT INTO pois(poi_id, name, category, brand, city,
                 district, address, lat, lon, rating, review_count,
                 popularity, attributes, tags, description, search_norm)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                 $16)
               ON CONFLICT (poi_id) DO UPDATE SET
                 name=EXCLUDED.name, category=EXCLUDED.category,
                 brand=EXCLUDED.brand, city=EXCLUDED.city,
                 district=EXCLUDED.district, address=EXCLUDED.address,
                 lat=EXCLUDED.lat, lon=EXCLUDED.lon,
                 rating=EXCLUDED.rating,
                 review_count=EXCLUDED.review_count,
                 popularity=EXCLUDED.popularity,
                 attributes=EXCLUDED.attributes, tags=EXCLUDED.tags,
                 description=EXCLUDED.description,
                 search_norm=EXCLUDED.search_norm""",
            [
                str(poi["poi_id"]),
                str(poi["poi_name"]),
                str(poi.get("category") or ""),
                str(poi.get("brand") or ""),
                str(poi.get("city") or ""),
                str(poi.get("district") or ""),
                str(poi.get("address") or ""),
                lat,
                lon,
                float(poi.get("rating") or 0.0),
                int(float(poi.get("review_count") or 0)),
                float(poi.get("popularity_score") or 0.0),
                str(poi.get("attributes") or ""),
                str(poi.get("tags") or ""),
                str(poi.get("description") or ""),
                normalize_for_search(searchable),
            ],
        )
        ids.append(str(poi["poi_id"]))
        texts.append(searchable)
        payloads.append(
            {
                "name": str(poi["poi_name"]),
                "category": str(poi.get("category") or ""),
                "city": str(poi.get("city") or ""),
                "district": str(poi.get("district") or ""),
                "lat": lat,
                "lon": lon,
                "rating": float(poi.get("rating") or 0.0),
                "popularity": float(poi.get("popularity_score") or 0.0),
            }
        )

    embedder = Embedder()
    vectors = embedder.embed(texts)
    index = DenseIndex(COLLECTION)
    index.ensure(dim=len(vectors[0]))
    index.upsert(ids, vectors, payloads)
    print(
        f"ingested {len(ids)} POIs, {len(profiles)} profiles into "
        f"pg + qdrant:{COLLECTION} ({skipped} skipped for invalid coordinates)"
    )


if __name__ == "__main__":
    main()
