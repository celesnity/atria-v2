"""Apply (or drop) the GeoRAG schema on map-db.

Usage:
    python db_setup.py          -> apply scripts/db_schema.sql (idempotent)
    python db_setup.py --drop   -> drop all map_* tables, then re-apply

Extensions are (re-)created defensively here as well: the container's
docker-entrypoint-initdb.d only runs on an empty data volume.
Prints one JSON status object to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
from _data import emit

SCHEMA_FILE = Path(__file__).resolve().parent / "db_schema.sql"

TABLES = [
    "map_query_embeddings",
    "map_embeddings",
    "map_admin_areas",
    "map_aliases",
    "map_addresses",
    "map_pois",
    "map_categories",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the tasco_jarvis_map DB schema")
    parser.add_argument("--drop", action="store_true", help="drop map_* tables first")
    args = parser.parse_args()

    try:
        conn = _db.connect()
    except _db.MapDbUnavailable as exc:
        emit({"error": f"map-db unavailable: {exc}"})
        sys.exit(1)

    with conn:
        if args.drop:
            with conn.cursor() as cur:
                for table in TABLES:
                    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        n = _db.run_sql_script(conn, SCHEMA_FILE.read_text(encoding="utf-8"))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name LIKE 'map\\_%' ORDER BY table_name"
            )
            tables = [r[0] for r in cur.fetchall()]

    emit({"status": "ok", "dropped": bool(args.drop), "statements": n, "tables": tables})


if __name__ == "__main__":
    main()
