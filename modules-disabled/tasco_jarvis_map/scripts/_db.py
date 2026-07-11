"""Postgres (map-db) plumbing for the GeoRAG hybrid backend.

The map module keeps two engines: the legacy JSON one in search.py and the
Postgres+PostGIS+pgvector one in search_db.py. This file owns connection
handling, env/config resolution, and the fusion constants so calibration
happens in exactly one place.

Backend selection: ATRIA_MAP_BACKEND=db|json (default db). The dispatcher in
search.py falls back to the JSON engine on MapDbUnavailable (or any DB error),
so a stopped map-db container never breaks the dashboard.
"""

from __future__ import annotations

import os
import re

from _data import MODULE_DIR

REPO_DIR = MODULE_DIR.parent.parent  # modules/tasco_jarvis_map -> repo root

DEFAULT_DSN = "postgresql://atria_map:atria_map@localhost:5433/atria_map"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

# ---- Hybrid fusion constants (single calibration point, see plan Phase 4) ----
# All signals are 0..1. Final score = 100 * max(fused, s_lex) which keeps the
# legacy 0-100 scale and its tier semantics (exact name ~100, exact alias ~95,
# prefix ~80, substring ~60) while the fused hybrid adds fuzzy/semantic recall.
# Load-bearing consumers of the scale: jarvis_chat fast-path (>=55) and the
# result threshold (>20).
WEIGHTS_NO_ORIGIN = {"lex": 0.35, "fts": 0.35, "vec": 0.30, "geo": 0.0}
WEIGHTS_ORIGIN = {"lex": 0.20, "fts": 0.25, "vec": 0.20, "geo": 0.35}
SCORE_THRESHOLD = 20.0  # results kept when score > threshold (legacy)
ALIAS_PENALTY = 0.05  # rank>0 alias matches score slightly below the name
FTS_SATURATION = 0.10  # ts_rank_cd(...,32) saturates ~0.1 on this corpus
GEO_DECAY_METERS = 2000.0  # s_geo = exp(-distance / this)


class MapDbUnavailable(RuntimeError):
    """map-db cannot be reached / driver missing — caller should fall back."""


_DOTENV_CACHE: dict[str, str] | None = None


def _dotenv() -> dict[str, str]:
    """Parse the repo-root .env once (standalone terminal runs don't inherit
    the backend's environment). Never overrides real env vars."""
    global _DOTENV_CACHE
    if _DOTENV_CACHE is None:
        vals: dict[str, str] = {}
        env_file = REPO_DIR / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                if key:
                    vals[key] = val
        _DOTENV_CACHE = vals
    return _DOTENV_CACHE


def env_get(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    if val is None or val == "":
        val = _dotenv().get(key)
    return val if val not in (None, "") else default


def get_dsn() -> str:
    return env_get("MAP_DATABASE_URL", DEFAULT_DSN)


def backend() -> str:
    return (env_get("ATRIA_MAP_BACKEND", "db") or "db").strip().lower()


def embed_disabled() -> bool:
    return (env_get("MAP_EMBED_DISABLED", "") or "").strip().lower() in ("1", "true", "yes")


def connect():
    """Open an autocommit psycopg connection with pgvector registered.

    Imports live inside so the JSON backend never needs the DB deps installed.
    """
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:  # driver not installed yet
        raise MapDbUnavailable(f"psycopg/pgvector not installed: {exc}") from exc
    try:
        conn = psycopg.connect(get_dsn(), connect_timeout=2, autocommit=True)
        register_vector(conn)
        return conn
    except Exception as exc:
        raise MapDbUnavailable(str(exc)) from exc


def run_sql_script(conn, sql: str) -> int:
    """Execute a multi-statement DDL script statement-by-statement (psycopg's
    extended protocol rejects multi-command strings). Returns statement count.
    Safe for our schema file: plain DDL, no dollar-quoted bodies."""
    statements = [s.strip() for s in re.split(r";\s*(?:\n|$)", sql) if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    return len(statements)
