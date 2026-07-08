#!/usr/bin/env python
"""SQLite storage layer for the warehouse module.

A single embedded database file holds two tables:

- ``items``     — current stock state, one row per SKU (1:1 with the old CSV).
- ``movements`` — append-only audit ledger; every stock change writes a row in
  the same transaction so the ledger can never drift from ``items``.

The DB path defaults to ``../data/warehouse.db`` but can be overridden with the
``ATRIA_WAREHOUSE_DB`` environment variable (tests point this at a temp file so
they never touch the live store). The schema is created on first connect; if a
legacy ``inventory.csv`` is present it is migrated in, otherwise a small sample
dataset is seeded so the reference module is populated out of the box.

Schema v2 adds bilingual/category metadata and the "ordered" restock marker:
``name_vi``, ``category``, ``ordered_by``, ``ordered_at`` on ``items``.
Existing v1 databases are migrated in place with additive ``ALTER TABLE``s.
"""

from __future__ import annotations

import csv
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "warehouse.db"
LEGACY_CSV = DATA_DIR / "inventory.csv"

SCHEMA_VERSION = 2

# Public item columns, in display order, returned by the CLI / JSON payloads.
ITEM_FIELDS = [
    "sku",
    "name",
    "name_vi",
    "category",
    "location",
    "quantity",
    "unit_price",
    "reorder_level",
    "ordered_by",
    "ordered_at",
    "updated_at",
]

# Sample seed used for a fresh DB when no legacy CSV is present. Quantities for
# SKU-001..003 are pinned by tests/test_warehouse_inventory.py — keep them.
SEED_ITEMS = [
    {"sku": "SKU-001", "name": "Gear oil 75W-90", "name_vi": "Dầu hộp số 75W-90",
     "category": "Fluids", "location": "A1-03",
     "quantity": 50, "unit_price": 185000, "reorder_level": 10},
    {"sku": "SKU-002", "name": "Brake pads front", "name_vi": "Má phanh trước",
     "category": "Brakes", "location": "B2-11",
     "quantity": 12, "unit_price": 450000, "reorder_level": 5},
    {"sku": "SKU-003", "name": "Timing belt", "name_vi": "Dây curoa cam",
     "category": "Engine", "location": "C4-07",
     "quantity": 3, "unit_price": 520000, "reorder_level": 8},
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    sku           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    name_vi       TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    location      TEXT,
    quantity      INTEGER NOT NULL DEFAULT 0,
    unit_price    REAL    NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 0,
    ordered_by    TEXT,
    ordered_at    TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS movements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sku        TEXT    NOT NULL,
    kind       TEXT    NOT NULL,
    delta      INTEGER NOT NULL DEFAULT 0,
    balance    INTEGER,
    reason     TEXT,
    reference  TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_movements_sku ON movements(sku, created_at);
"""

# Columns added by schema v2, applied to v1 databases in place.
_V2_COLUMNS = [
    ("name_vi", "TEXT NOT NULL DEFAULT ''"),
    ("category", "TEXT NOT NULL DEFAULT ''"),
    ("ordered_by", "TEXT"),
    ("ordered_at", "TEXT"),
]


def now() -> str:
    """Return the current UTC time as an ISO-8601 ``Z`` timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gen_reference(prefix: str) -> str:
    """Build a unique movement reference like ``SALE-20260705T081500Z-a3f2``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{secrets.token_hex(2)}"


def item_status(quantity: int, reorder_level: int) -> str:
    """Classify stock state: ``out`` (0), ``low`` (<= reorder) or ``in_stock``."""
    if quantity <= 0:
        return "out"
    if quantity <= reorder_level:
        return "low"
    return "in_stock"


def db_path() -> Path:
    """Resolve the active DB file (env override wins; else the module default)."""
    override = os.environ.get("ATRIA_WAREHOUSE_DB")
    return Path(override) if override else DEFAULT_DB


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-v2 database up to the current schema (idempotent)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    for col, decl in _V2_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} {decl}")


def connect() -> sqlite3.Connection:
    """Open (creating + bootstrapping if needed) the warehouse DB."""
    path = db_path()
    fresh = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Dashboard subprocesses and the agent CLI may write concurrently.
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.executescript(_SCHEMA)
    if int(conn.execute("PRAGMA user_version").fetchone()[0]) < SCHEMA_VERSION:
        _migrate(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    # Seed only on first creation so an intentional `reset` stays empty.
    if fresh and conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
        seed(conn)
    conn.commit()
    return conn


def connect_readonly() -> sqlite3.Connection:
    """Open the DB in read-only mode (used by the guarded ``query`` command)."""
    path = db_path()
    if not path.exists():
        connect().close()  # bootstrap the file so a read-only open succeeds
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


def log_movement(
    conn: sqlite3.Connection,
    sku: str,
    kind: str,
    delta: int,
    balance: int | None,
    *,
    reason: str | None = None,
    reference: str | None = None,
    commit: bool = True,
) -> None:
    """Append a row to the audit ledger. Caller owns the transaction by default."""
    conn.execute(
        "INSERT INTO movements (sku, kind, delta, balance, reason, reference, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sku, kind, int(delta), balance, reason, reference, now()),
    )
    if commit:
        conn.commit()


def item_dict(row: sqlite3.Row) -> dict:
    """Normalise an ``items`` row into the JSON shape the UI/agent expect."""
    return {
        "sku": row["sku"],
        "name": row["name"],
        "name_vi": row["name_vi"] or "",
        "category": row["category"] or "",
        "location": row["location"] or "",
        "quantity": int(row["quantity"]),
        "unit_price": float(row["unit_price"]),
        "reorder_level": int(row["reorder_level"]),
        "ordered_by": row["ordered_by"],
        "ordered_at": row["ordered_at"],
        "updated_at": row["updated_at"],
    }


def _read_legacy_csv() -> list[dict] | None:
    if not LEGACY_CSV.exists():
        return None
    with LEGACY_CSV.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows or None


def seed(conn: sqlite3.Connection) -> int:
    """Populate an empty DB from the legacy CSV if present, else the sample set.

    Returns the number of items inserted. Safe to call on a non-empty DB:
    existing SKUs are left untouched.
    """
    rows = _read_legacy_csv() or SEED_ITEMS
    ts = now()
    inserted = 0
    for r in rows:
        try:
            qty = int(r["quantity"])
            cur = conn.execute(
                "INSERT OR IGNORE INTO items "
                "(sku, name, name_vi, category, location, quantity, unit_price, "
                " reorder_level, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["sku"], r["name"], (r.get("name_vi") or ""), (r.get("category") or ""),
                 (r.get("location") or ""), qty,
                 float(r["unit_price"]), int(r["reorder_level"]), ts, ts),
            )
        except (KeyError, ValueError):
            continue
        if cur.rowcount:
            inserted += 1
            log_movement(conn, r["sku"], "add", qty, qty, reason="seed", commit=False)
    conn.commit()
    return inserted
