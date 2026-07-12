#!/usr/bin/env python
"""map_doctor -- one-command health check for the map-db backend.

Reports the selected backend, driver availability, DB connectivity and row
counts, so a SILENT JSON fallback (stopped container / missing psycopg / empty
DB) becomes visible instead of quietly measuring the wrong engine. Never prints
secrets -- only the DSN host:port. CLI or AtriaDash bridge:

    PYTHONUTF8=1 python scripts/map_doctor.py
    AtriaDash.json('map_doctor.py', [])

Exit 0 when the active backend is healthy, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _db  # noqa: E402

_TABLES = ("map_pois", "map_embeddings", "map_admin_areas", "map_addresses")


def _strict() -> bool:
    return os.environ.get("ATRIA_MAP_STRICT_DB", "").strip().lower() in ("1", "true", "yes")


def diagnose() -> dict:
    backend = _db.backend()
    out = {"backend": backend, "strict_db": _strict(), "driver": None,
           "dsn_host": None, "connected": False, "counts": {}, "verdict": "",
           "ok": False, "error": None}
    try:  # driver presence (import only — no secrets touched)
        import psycopg  # noqa: F401
        from pgvector.psycopg import register_vector  # noqa: F401
        out["driver"] = "psycopg+pgvector"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"driver missing: {exc}"
    try:  # host:port only — never the credentials
        out["dsn_host"] = _db.get_dsn().rsplit("@", 1)[-1]
    except Exception:  # noqa: BLE001
        pass

    if backend != "db":
        out["verdict"] = "backend=json (db engine not selected) — configured state, ok"
        out["ok"] = True
        return out
    if out["driver"] is None:
        out["verdict"] = "db selected but DRIVER MISSING -> queries SILENTLY fall back to JSON"
        return out
    try:
        conn = _db.connect()
        out["connected"] = True
        for t in _TABLES:
            try:
                out["counts"][t] = conn.execute(f"select count(*) from {t}").fetchone()[0]
            except Exception as exc:  # noqa: BLE001
                out["counts"][t] = f"ERR {exc}"
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        out["verdict"] = "db selected but UNREACHABLE -> queries SILENTLY fall back to JSON"
        return out

    pois = out["counts"].get("map_pois")
    emb = out["counts"].get("map_embeddings")
    healthy = isinstance(pois, int) and pois > 0
    out["ok"] = healthy
    out["verdict"] = (f"db healthy: {pois} pois, {emb} embeddings"
                      if healthy else "db reachable but EMPTY -> run db_import.py + gen_embeddings.py")
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    d = diagnose()
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if d["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
