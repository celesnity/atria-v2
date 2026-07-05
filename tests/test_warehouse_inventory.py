from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "modules" / "warehouse" / "scripts" / "inventory.py"


@pytest.fixture()
def env(tmp_path):
    """Point the warehouse CLI at an isolated, freshly-seeded temp DB."""
    e = os.environ.copy()
    e["ATRIA_WAREHOUSE_DB"] = str(tmp_path / "warehouse.db")
    return e


def run(env, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def list_json(env, *args: str) -> dict:
    r = run(env, "list", "--json", *args)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── seeding & listing ────────────────────────────────────────────────────────


def test_fresh_db_is_seeded(env):
    payload = list_json(env)
    skus = {it["sku"] for it in payload["items"]}
    assert {"SKU-001", "SKU-002", "SKU-003"} <= skus


def test_list_json_returns_items_and_low_stock(env):
    payload = list_json(env)
    assert isinstance(payload["items"], list)
    assert all(
        {"sku", "name", "location", "quantity", "unit_price", "reorder_level"}.issubset(item.keys())
        for item in payload["items"]
    )
    by_sku = {it["sku"]: it for it in payload["items"]}
    for sku in payload["low_stock"]:
        assert by_sku[sku]["quantity"] <= by_sku[sku]["reorder_level"]


def test_list_json_query_filter(env):
    payload = list_json(env, "--query", "gear")
    assert payload["items"]
    assert all(
        "gear" in it["name"].lower() or "gear" in it["sku"].lower() for it in payload["items"]
    )


def test_list_low_only(env):
    payload = list_json(env, "--low-only")
    assert all(it["quantity"] <= it["reorder_level"] for it in payload["items"])


# ── CRUD + audit ledger ───────────────────────────────────────────────────────


def test_add_logs_movement(env):
    r = run(
        env,
        "add",
        "--sku",
        "SKU-900",
        "--name",
        "Bolt",
        "--location",
        "Z1",
        "--quantity",
        "30",
        "--unit-price",
        "1.50",
        "--reorder-level",
        "5",
    )
    assert r.returncode == 0, r.stderr
    hist = json.loads(run(env, "history", "--sku", "SKU-900", "--json").stdout)["movements"]
    assert any(m["kind"] == "add" and m["delta"] == 30 for m in hist)


def test_add_duplicate_fails(env):
    r = run(
        env,
        "add",
        "--sku",
        "SKU-001",
        "--name",
        "Dup",
        "--location",
        "X",
        "--quantity",
        "1",
        "--unit-price",
        "1",
        "--reorder-level",
        "1",
    )
    assert r.returncode == 1
    assert "already exists" in r.stderr


def test_receive_and_ship_update_quantity(env):
    run(env, "receive", "--sku", "SKU-001", "--qty", "10", "--reference", "PO-1")
    run(env, "ship", "--sku", "SKU-001", "--qty", "4", "--reference", "ORD-1")
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["SKU-001"]["quantity"] == 56  # 50 + 10 - 4
    kinds = {
        m["kind"]
        for m in json.loads(run(env, "history", "--sku", "SKU-001", "--json").stdout)["movements"]
    }
    assert {"receive", "ship"} <= kinds


def test_ship_cannot_go_negative(env):
    r = run(env, "ship", "--sku", "SKU-003", "--qty", "999")
    assert r.returncode == 1
    assert "negative" in r.stderr


def test_adjust_negative_guard(env):
    r = run(env, "adjust", "--sku", "SKU-003", "--delta", "-999")
    assert r.returncode == 1


def test_move_changes_location(env):
    assert run(env, "move", "--sku", "SKU-001", "--location", "B9-99").returncode == 0
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["SKU-001"]["location"] == "B9-99"


def test_set_reorder(env):
    assert run(env, "set-reorder", "--sku", "SKU-001", "--level", "99").returncode == 0
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["SKU-001"]["reorder_level"] == 99
    assert "SKU-001" in list_json(env)["low_stock"]  # 50 <= 99


def test_remove(env):
    assert run(env, "remove", "--sku", "SKU-002").returncode == 0
    assert "SKU-002" not in {it["sku"] for it in list_json(env)["items"]}


# ── reporting ─────────────────────────────────────────────────────────────────


def test_summary_json(env):
    s = json.loads(run(env, "summary", "--json").stdout)
    assert s["skus"] == 3
    assert s["units"] == 65  # 50 + 12 + 3
    assert s["value"] == pytest.approx(50 * 185000 + 12 * 450000 + 3 * 520000, rel=1e-6)
    assert s["low_stock_count"] == len(s["low_stock"])


def test_valuation_json(env):
    v = json.loads(run(env, "valuation", "--by", "location", "--json").stdout)
    assert v["by"] == "location"
    assert sum(g["units"] for g in v["groups"]) == 65


def test_low_stock_json(env):
    low = json.loads(run(env, "low-stock", "--json").stdout)
    assert all(it["quantity"] <= it["reorder_level"] for it in low["items"])


# ── read-only query guard ─────────────────────────────────────────────────────


def test_query_select_ok(env):
    r = run(env, "query", "--json", "--sql", "SELECT COUNT(*) AS n FROM items")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["rows"][0]["n"] == 3


def test_query_rejects_write(env):
    for sql in ("DELETE FROM items", "UPDATE items SET quantity=0", "SELECT 1; DROP TABLE items"):
        r = run(env, "query", "--sql", sql)
        assert r.returncode == 1, f"should reject: {sql}"


# ── import / export / reset ────────────────────────────────────────────────────


def test_export_import_roundtrip(env, tmp_path):
    out = tmp_path / "dump.json"
    assert run(env, "export", "--format", "json", "--out", str(out)).returncode == 0
    assert run(env, "reset").returncode == 0
    assert list_json(env)["items"] == []
    assert run(env, "import", "--file", str(out), "--format", "json").returncode == 0
    assert len(list_json(env)["items"]) == 3


def test_reset_empties_everything(env):
    assert run(env, "reset").returncode == 0
    assert list_json(env)["items"] == []
    assert json.loads(run(env, "history", "--json").stdout)["movements"] == []


# ── schema v2 migration ───────────────────────────────────────────────────────


def test_v1_db_migrates_in_place(tmp_path):
    """A v1 database gains the v2 columns without losing rows or history."""
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE items (
            sku TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT,
            quantity INTEGER NOT NULL DEFAULT 0, unit_price REAL NOT NULL DEFAULT 0,
            reorder_level INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL, kind TEXT NOT NULL,
            delta INTEGER NOT NULL DEFAULT 0, balance INTEGER, reason TEXT,
            reference TEXT, created_at TEXT NOT NULL);
        CREATE INDEX idx_movements_sku ON movements(sku, created_at);
        PRAGMA user_version = 1;
        INSERT INTO items VALUES ('OLD-1', 'Legacy widget', 'A1', 7, 2.5, 3,
                                  '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
        INSERT INTO movements (sku, kind, delta, balance, created_at)
            VALUES ('OLD-1', 'add', 7, 7, '2026-01-01T00:00:00Z');
        """
    )
    conn.commit()
    conn.close()

    e = os.environ.copy()
    e["ATRIA_WAREHOUSE_DB"] = str(db)
    payload = list_json(e)
    assert len(payload["items"]) == 1
    it = payload["items"][0]
    assert it["sku"] == "OLD-1" and it["quantity"] == 7
    assert it["name_vi"] == "" and it["category"] == ""
    assert it["ordered_by"] is None and it["ordered_at"] is None
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM movements").fetchone()[0] == 1
    conn.close()


# ── snapshot ──────────────────────────────────────────────────────────────────


def test_snapshot_shape_and_math(env):
    snap = json.loads(run(env, "snapshot").stdout)
    assert {"generated_at", "items", "stats", "categories", "movements"} <= snap.keys()
    by_sku = {it["sku"]: it for it in snap["items"]}
    # Seed: SKU-003 qty=3 reorder=8 -> low, suggestion = max(8*2-3, 8) = 13.
    assert by_sku["SKU-003"]["status"] == "low"
    assert by_sku["SKU-003"]["suggested_order"] == 13
    assert by_sku["SKU-001"]["status"] == "in_stock"
    assert by_sku["SKU-001"]["suggested_order"] == 0
    assert snap["stats"]["skus"] == 3
    assert snap["stats"]["low_count"] == 1 and snap["stats"]["out_count"] == 0
    assert set(snap["categories"]) == {"Fluids", "Brakes", "Engine"}


def test_snapshot_spw_and_sold_today(env):
    run(env, "sell", "--line", "SKU-001=7", "--json")
    snap = json.loads(run(env, "snapshot").stdout)
    by_sku = {it["sku"]: it for it in snap["items"]}
    assert by_sku["SKU-001"]["spw"] == pytest.approx(7 / 4.0)
    assert by_sku["SKU-001"]["days_left"] is not None
    assert snap["stats"]["sold_today_count"] == 7
    assert snap["stats"]["sold_today_value"] == pytest.approx(7 * 185000)


# ── sell / revert ─────────────────────────────────────────────────────────────


def test_sell_multi_line_shares_reference(env):
    r = run(env, "sell", "--line", "SKU-001=2", "--line", "SKU-002=1", "--json")
    assert r.returncode == 0, r.stderr
    sale = json.loads(r.stdout)
    assert sale["ok"] and len(sale["lines"]) == 2
    assert sale["total_value"] == pytest.approx(2 * 185000 + 1 * 450000)
    refs = {
        m["reference"]
        for m in json.loads(run(env, "history", "--json").stdout)["movements"]
        if m["kind"] == "ship"
    }
    assert refs == {sale["reference"]}


def test_sell_is_atomic_on_bad_line(env):
    r = run(env, "sell", "--line", "SKU-001=2", "--line", "SKU-003=999", "--json")
    assert r.returncode == 1
    assert "insufficient" in r.stderr
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["SKU-001"]["quantity"] == 50  # untouched


def test_revert_roundtrip_and_guards(env):
    sale = json.loads(run(env, "sell", "--line", "SKU-001=5", "--json").stdout)
    ref = sale["reference"]
    r = run(env, "revert", "--reference", ref, "--json")
    assert r.returncode == 0, r.stderr
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["SKU-001"]["quantity"] == 50
    # Double revert refused.
    r = run(env, "revert", "--reference", ref)
    assert r.returncode == 1 and "already" in r.stderr
    # Unknown reference refused.
    assert run(env, "revert", "--reference", "NOPE-1").returncode == 1


def test_revert_receive_negative_guard(env):
    run(env, "receive", "--sku", "SKU-003", "--qty", "5", "--reference", "RCV-9")
    run(env, "ship", "--sku", "SKU-003", "--qty", "7")  # 3+5-7 = 1 left
    r = run(env, "revert", "--reference", "RCV-9")  # would need -5 -> negative
    assert r.returncode == 1 and "negative" in r.stderr


# ── ordered marker ────────────────────────────────────────────────────────────


def test_ordered_marker_lifecycle(env):
    it = json.loads(run(env, "mark-ordered", "--sku", "SKU-003", "--json").stdout)["item"]
    assert it["ordered_by"] == "You" and it["ordered_at"]
    it = json.loads(run(env, "unmark-ordered", "--sku", "SKU-003", "--json").stdout)["item"]
    assert it["ordered_by"] is None
    run(env, "mark-ordered", "--sku", "SKU-003")
    run(env, "receive", "--sku", "SKU-003", "--qty", "10")
    by_sku = {i["sku"]: i for i in list_json(env)["items"]}
    assert by_sku["SKU-003"]["ordered_by"] is None  # receive fulfils the order


# ── stdin import ──────────────────────────────────────────────────────────────


def run_stdin(env, stdin_text: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        input=stdin_text,
    )


def test_import_from_stdin_with_errors(env):
    csv_text = (
        "sku,name,name_vi,category,quantity,unit_price,reorder_level\n"
        "OP-085,Oil pan gasket,Gioăng các te,Engine,10,120000,4\n"
        "BAD-1,No qty,,Filters,,5000,2\n"
        "SKU-001,Gear oil 75W-90,,Fluids,60,185000,10\n"
    )
    r = run_stdin(env, csv_text, "import", "--format", "csv", "--file", "-", "--json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert res["added"] == 1 and res["updated"] == 1 and res["skipped"] == 1
    assert res["errors"][0]["row"] == 2
    by_sku = {it["sku"]: it for it in list_json(env)["items"]}
    assert by_sku["OP-085"]["name_vi"] == "Gioăng các te"
    assert by_sku["SKU-001"]["quantity"] == 60  # recount via import
    kinds = {
        m["kind"]
        for m in json.loads(run(env, "history", "--sku", "SKU-001", "--json").stdout)["movements"]
    }
    assert "recount" in kinds
