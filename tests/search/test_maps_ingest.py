"""Live ingestion integration test for the Track 8 POI dataset."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

XLSX = (
    Path(__file__).resolve().parents[2] / "mobility/track8/ai_maps_track3_dataset_participants.xlsx"
)

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        and XLSX.exists()
    ),
    reason="needs live Postgres, Qdrant, an embedding key and the Track 8 xlsx",
)


def test_ingest_pois_end_to_end():
    from atria.core.context_engineering.search import pg

    script = Path(__file__).resolve().parents[2] / "modules/maps_search/scripts/ingest.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(XLSX)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    pois = pg.fetch_all("SELECT count(*) AS n FROM pois")[0]["n"]
    profiles = pg.fetch_all("SELECT count(*) AS n FROM map_user_profiles")[0]["n"]
    assert pois == 80
    assert profiles > 0
    sample = pg.fetch_all("SELECT lat, lon, search_norm FROM pois LIMIT 1")[0]
    assert isinstance(sample["lat"], float) and isinstance(sample["lon"], float)
    assert sample["search_norm"] == sample["search_norm"].lower()
    # idempotency
    proc2 = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(XLSX)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc2.returncode == 0, proc2.stderr
    assert pg.fetch_all("SELECT count(*) AS n FROM pois")[0]["n"] == 80
