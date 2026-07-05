#!/usr/bin/env python
"""SQLite-backed inventory management for the warehouse module.

The live store is a single ``warehouse.db`` file (see ``_db.py``). Every stock
change is recorded in an append-only ``movements`` ledger alongside the
current-state ``items`` table.

Subcommands:
  state ........ list, summary, low-stock, valuation, history, query, snapshot, report
  CRUD ......... add, update, remove, reset
  stock ops .... adjust, receive, ship, sell, revert, move, set-reorder,
                 mark-ordered, unmark-ordered
  data ......... export, import, migrate

``snapshot`` returns everything the module dashboard renders in one call.
``sell`` writes one ``ship`` movement per line under a shared reference;
``revert --reference`` undoes a whole sale/receipt with compensating movements.
"""

from __future__ import annotations

import argparse
import csv
import io
import json as _json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _db

# ── small output helpers ────────────────────────────────────────────────────


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _emit(obj: object) -> None:
    print(_json.dumps(obj))


def _find(conn: sqlite3.Connection, sku: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()


def _low_stock_skus(items: list[dict]) -> list[str]:
    return [it["sku"] for it in items if it["quantity"] <= it["reorder_level"]]


_SORT_COLUMNS = {
    "sku": "sku COLLATE NOCASE",
    "name": "name COLLATE NOCASE",
    "quantity": "quantity DESC",
    "value": "(quantity * unit_price) DESC",
    "updated": "updated_at DESC",
}


# ── read commands ───────────────────────────────────────────────────────────


def cmd_list(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    where: list[str] = []
    params: list[object] = []
    if args.query:
        where.append("(sku LIKE ? OR name LIKE ? OR name_vi LIKE ? OR category LIKE ?)")
        like = f"%{args.query}%"
        params += [like, like, like, like]
    if args.location:
        where.append("location LIKE ?")
        params.append(f"%{args.location}%")
    if args.min_price is not None:
        where.append("unit_price >= ?")
        params.append(args.min_price)
    if args.max_price is not None:
        where.append("unit_price <= ?")
        params.append(args.max_price)

    sql = "SELECT * FROM items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + _SORT_COLUMNS.get(args.sort, _SORT_COLUMNS["sku"])

    rows = [_db.item_dict(r) for r in conn.execute(sql, params).fetchall()]
    if args.low_only:
        rows = [r for r in rows if r["quantity"] <= r["reorder_level"]]
    low = _low_stock_skus(rows)

    if args.json:
        _emit({"items": rows, "low_stock": low})
        return 0

    _print_table(rows)
    if low:
        print(f"\nlow stock (<= reorder_level): {', '.join(low)}")
    return 0


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no items)")
        return
    fields = _db.ITEM_FIELDS
    text = [{f: str(r.get(f, "")) for f in fields} for r in rows]
    widths = {f: max(len(f), max((len(r[f]) for r in text), default=0)) for f in fields}
    print("  ".join(f.ljust(widths[f]) for f in fields))
    print("  ".join("-" * widths[f] for f in fields))
    for r in text:
        print("  ".join(r[f].ljust(widths[f]) for f in fields))


def cmd_low_stock(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = [_db.item_dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
    low = [r for r in rows if r["quantity"] <= r["reorder_level"]]
    if args.json:
        _emit({"items": low, "low_stock": [r["sku"] for r in low]})
        return 0
    _print_table(low)
    return 0


def cmd_summary(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = [_db.item_dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
    total_units = sum(r["quantity"] for r in rows)
    total_value = round(sum(r["quantity"] * r["unit_price"] for r in rows), 2)
    low = _low_stock_skus(rows)
    by_loc: dict[str, dict] = {}
    for r in rows:
        loc = r["location"] or "(none)"
        agg = by_loc.setdefault(loc, {"location": loc, "skus": 0, "units": 0, "value": 0.0})
        agg["skus"] += 1
        agg["units"] += r["quantity"]
        agg["value"] = round(agg["value"] + r["quantity"] * r["unit_price"], 2)
    summary = {
        "skus": len(rows),
        "units": total_units,
        "value": total_value,
        "low_stock_count": len(low),
        "low_stock": low,
        "by_location": sorted(by_loc.values(), key=lambda a: a["location"]),
    }
    if args.json:
        _emit(summary)
        return 0
    print(f"SKUs:            {summary['skus']}")
    print(f"Units on hand:   {summary['units']}")
    print(f"Inventory value: ${summary['value']:.2f}")
    print(f"Low stock:       {summary['low_stock_count']}"
          + (f" ({', '.join(low)})" if low else ""))
    print("\nBy location:")
    for a in summary["by_location"]:
        print(f"  {a['location']:<10} {a['skus']:>3} skus  {a['units']:>6} units  ${a['value']:.2f}")
    return 0


def cmd_valuation(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = [_db.item_dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
    groups: dict[str, dict] = {}
    for r in rows:
        key = (r["location"] or "(none)") if args.by == "location" else r["sku"]
        agg = groups.setdefault(key, {"key": key, "units": 0, "value": 0.0})
        agg["units"] += r["quantity"]
        agg["value"] = round(agg["value"] + r["quantity"] * r["unit_price"], 2)
    out = sorted(groups.values(), key=lambda a: a["value"], reverse=True)
    if args.json:
        _emit({"by": args.by, "groups": out})
        return 0
    label = "Location" if args.by == "location" else "SKU"
    print(f"{label:<12} {'Units':>8} {'Value':>12}")
    for a in out:
        print(f"{a['key']:<12} {a['units']:>8} {'$' + format(a['value'], '.2f'):>12}")
    return 0


def cmd_history(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    sql = "SELECT * FROM movements"
    params: list[object] = []
    if args.sku:
        sql += " WHERE sku = ?"
        params.append(args.sku)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if args.json:
        _emit({"movements": rows})
        return 0
    if not rows:
        print("(no movements)")
        return 0
    for m in rows:
        sign = f"{m['delta']:+d}" if m["delta"] else "0"
        extra = " ".join(filter(None, [
            f"-> {m['balance']}" if m["balance"] is not None else "",
            f"({m['reason']})" if m["reason"] else "",
            f"ref={m['reference']}" if m["reference"] else "",
        ]))
        print(f"{m['created_at']}  {m['sku']:<10} {m['kind']:<11} {sign:>5}  {extra}")
    return 0


def cmd_query(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    # conn here is the read-only connection (see main()).
    rows = [dict(r) for r in conn.execute(args.sql).fetchall()]
    if args.json:
        _emit({"rows": rows})
        return 0
    if not rows:
        print("(no rows)")
        return 0
    cols = list(rows[0].keys())
    text = [{c: str(r.get(c, "")) for c in cols} for r in rows]
    widths = {c: max(len(c), max((len(r[c]) for r in text), default=0)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in text:
        print("  ".join(r[c].ljust(widths[c]) for c in cols))
    return 0


# ── write commands ───────────────────────────────────────────────────────────


def cmd_add(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if _find(conn, args.sku):
        _err(f"SKU already exists: {args.sku}")
        return 1
    ts = _db.now()
    conn.execute(
        "INSERT INTO items "
        "(sku, name, name_vi, category, location, quantity, unit_price, reorder_level, "
        " created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (args.sku, args.name, args.name_vi or "", args.category or "", args.location or "",
         args.quantity, args.unit_price, args.reorder_level, ts, ts),
    )
    _db.log_movement(conn, args.sku, "add", args.quantity, args.quantity,
                     reason="created", commit=False)
    conn.commit()
    if getattr(args, "json", False):
        _emit({"ok": True, "item": _db.item_dict(_find(conn, args.sku))})
    else:
        print(f"added: {args.sku}")
    return 0


def cmd_update(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    sets: list[str] = []
    params: list[object] = []
    qty_delta = 0
    new_balance = row["quantity"]
    for field, value in [("name", args.name), ("name_vi", args.name_vi),
                         ("category", args.category), ("location", args.location),
                         ("unit_price", args.unit_price), ("reorder_level", args.reorder_level)]:
        if value is not None:
            sets.append(f"{field} = ?")
            params.append(value)
    if args.quantity is not None:
        qty_delta = args.quantity - row["quantity"]
        new_balance = args.quantity
        sets.append("quantity = ?")
        params.append(args.quantity)
    if not sets:
        _err("nothing to update (pass at least one field)")
        return 1
    sets.append("updated_at = ?")
    params.append(_db.now())
    params.append(args.sku)
    conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE sku = ?", params)
    if qty_delta:
        _db.log_movement(conn, args.sku, "recount", qty_delta, new_balance,
                         reason="manual update", commit=False)
    conn.commit()
    if getattr(args, "json", False):
        _emit({"ok": True, "item": _db.item_dict(_find(conn, args.sku))})
    else:
        print(f"updated: {args.sku}")
    return 0


def _apply_delta(conn: sqlite3.Connection, sku: str, delta: int, kind: str,
                 reason: str | None, reference: str | None,
                 json_out: bool = False) -> int:
    row = _find(conn, sku)
    if row is None:
        _err(f"SKU not found: {sku}")
        return 1
    new_qty = row["quantity"] + delta
    if new_qty < 0:
        _err(f"would go negative ({new_qty}) for {sku}")
        return 1
    if kind == "receive":
        # Arriving stock fulfils an outstanding "ordered" marker.
        conn.execute(
            "UPDATE items SET quantity = ?, ordered_by = NULL, ordered_at = NULL, "
            "updated_at = ? WHERE sku = ?",
            (new_qty, _db.now(), sku),
        )
    else:
        conn.execute("UPDATE items SET quantity = ?, updated_at = ? WHERE sku = ?",
                     (new_qty, _db.now(), sku))
    _db.log_movement(conn, sku, kind, delta, new_qty,
                     reason=reason, reference=reference, commit=False)
    conn.commit()
    if json_out:
        _emit({"ok": True, "sku": sku, "kind": kind, "delta": delta,
               "balance": new_qty, "reference": reference})
    else:
        print(f"{kind}: {sku} -> quantity={new_qty}")
    return 0


def cmd_adjust(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    return _apply_delta(conn, args.sku, args.delta, "adjust", args.reason, args.reference,
                        json_out=args.json)


def cmd_receive(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    return _apply_delta(conn, args.sku, abs(args.qty), "receive", args.reason, args.reference,
                        json_out=args.json)


def cmd_ship(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    return _apply_delta(conn, args.sku, -abs(args.qty), "ship", args.reason, args.reference,
                        json_out=args.json)


def cmd_move(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    conn.execute("UPDATE items SET location = ?, updated_at = ? WHERE sku = ?",
                 (args.location, _db.now(), args.sku))
    _db.log_movement(conn, args.sku, "move", 0, row["quantity"],
                     reason=f"{row['location'] or '(none)'} -> {args.location}", commit=False)
    conn.commit()
    print(f"moved: {args.sku} -> {args.location}")
    return 0


def cmd_set_reorder(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    conn.execute("UPDATE items SET reorder_level = ?, updated_at = ? WHERE sku = ?",
                 (args.level, _db.now(), args.sku))
    _db.log_movement(conn, args.sku, "set-reorder", 0, row["quantity"],
                     reason=f"reorder_level -> {args.level}", commit=False)
    conn.commit()
    print(f"set-reorder: {args.sku} -> {args.level}")
    return 0


def cmd_remove(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    conn.execute("DELETE FROM items WHERE sku = ?", (args.sku,))
    _db.log_movement(conn, args.sku, "remove", -row["quantity"], 0,
                     reason="deleted", commit=False)
    conn.commit()
    print(f"removed: {args.sku}")
    return 0


def cmd_reset(conn: sqlite3.Connection, _args: argparse.Namespace) -> int:
    conn.execute("DELETE FROM items")
    conn.execute("DELETE FROM movements")
    conn.commit()
    print(f"reset: {_db.db_path()}")
    return 0


# ── data import / export ──────────────────────────────────────────────────────


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.table == "movements":
        rows = [dict(r) for r in conn.execute("SELECT * FROM movements ORDER BY id").fetchall()]
        cols = ["id", "sku", "kind", "delta", "balance", "reason", "reference", "created_at"]
    else:
        rows = [_db.item_dict(r) for r in
                conn.execute("SELECT * FROM items ORDER BY sku").fetchall()]
        cols = _db.ITEM_FIELDS

    if args.format == "json":
        payload = _json.dumps({args.table: rows}, indent=2)
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in cols})
        payload = buf.getvalue()

    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"exported {len(rows)} {args.table} row(s) -> {args.out}")
    else:
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def cmd_import(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.file == "-":
        # Read bytes and decode UTF-8 ourselves: on Windows sys.stdin may be
        # opened with the ANSI code page, which breaks Vietnamese payloads.
        text = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        path = Path(args.file)
        if not path.is_file():
            _err(f"file not found: {args.file}")
            return 1
        text = path.read_text(encoding="utf-8")
    if args.format == "json":
        data = _json.loads(text)
        rows = data.get("items", data) if isinstance(data, dict) else data
    else:
        rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))

    if args.replace:
        conn.execute("DELETE FROM items")
        conn.commit()

    ts = _db.now()
    added = updated = 0
    errors: list[dict] = []
    for idx, r in enumerate(rows, start=1):
        try:
            sku = str(r["sku"]).strip()
            if not sku:
                raise ValueError("empty sku")
            qty = int(r["quantity"])
            price = float(r["unit_price"])
            reorder = int(r.get("reorder_level") or 0)
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({"row": idx, "error": str(exc)})
            continue
        existing = _find(conn, sku)
        if existing is None:
            conn.execute(
                "INSERT INTO items "
                "(sku, name, name_vi, category, location, quantity, unit_price, reorder_level, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sku, r.get("name", sku), (r.get("name_vi") or ""), (r.get("category") or ""),
                 (r.get("location") or ""), qty, price, reorder, ts, ts),
            )
            _db.log_movement(conn, sku, "add", qty, qty, reason="import", commit=False)
            added += 1
        else:
            delta = qty - existing["quantity"]
            conn.execute(
                "UPDATE items SET name = ?, name_vi = ?, category = ?, location = ?, "
                "quantity = ?, unit_price = ?, reorder_level = ?, updated_at = ? WHERE sku = ?",
                (r.get("name", existing["name"]),
                 (r.get("name_vi") or existing["name_vi"]),
                 (r.get("category") or existing["category"]),
                 (r.get("location") or existing["location"]),
                 qty, price, reorder, ts, sku),
            )
            if delta:
                _db.log_movement(conn, sku, "recount", delta, qty, reason="import", commit=False)
            updated += 1
    conn.commit()
    if getattr(args, "json", False):
        _emit({"ok": not errors, "added": added, "updated": updated,
               "skipped": len(errors), "errors": errors})
    else:
        print(f"imported: {added} added, {updated} updated"
              + (f", {len(errors)} skipped" if errors else ""))
    return 0


def cmd_migrate(conn: sqlite3.Connection, _args: argparse.Namespace) -> int:
    if not _db.LEGACY_CSV.exists():
        print(f"no legacy CSV to migrate at {_db.LEGACY_CSV}")
        return 0
    inserted = _db.seed(conn)
    print(f"migrated {inserted} item(s) from {_db.LEGACY_CSV.name}")
    return 0


# ── dashboard-oriented commands ──────────────────────────────────────────────

# Units sold = ship movements minus reverted ships, so undone sales don't
# count toward sales-per-week or the sold-today KPI.
_SOLD_EXPR = ("CASE WHEN kind = 'ship' THEN -delta "
              "WHEN kind = 'revert' AND reason = 'revert ship' THEN -delta "
              "ELSE 0 END")


def _utc_today_start() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")


def _spw_by_sku(conn: sqlite3.Connection, days: int = 28) -> dict[str, float]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        f"SELECT sku, SUM({_SOLD_EXPR}) AS sold FROM movements "
        "WHERE created_at >= ? GROUP BY sku",
        (cutoff,),
    ).fetchall()
    weeks = days / 7.0
    return {r["sku"]: max(0.0, (r["sold"] or 0) / weeks) for r in rows}


def _build_snapshot(conn: sqlite3.Connection, today_start: str | None = None,
                    history_limit: int = 50) -> dict:
    """Assemble the dashboard snapshot dict (shared by snapshot + report)."""
    spw = _spw_by_sku(conn)
    items = []
    for r in conn.execute("SELECT * FROM items ORDER BY sku").fetchall():
        it = _db.item_dict(r)
        status = _db.item_status(it["quantity"], it["reorder_level"])
        rate = round(spw.get(it["sku"], 0.0), 2)
        days_left = None
        if status != "out" and rate > 0:
            days_left = max(1, round(it["quantity"] / (rate / 7.0)))
        suggested = 0
        if status != "in_stock":
            suggested = max(it["reorder_level"] * 2 - it["quantity"], it["reorder_level"], 1)
        it.update({"status": status, "spw": rate,
                   "days_left": days_left, "suggested_order": suggested})
        items.append(it)

    today_start = today_start or _utc_today_start()
    sold = conn.execute(
        f"SELECT m.sku, SUM({_SOLD_EXPR}) AS units FROM movements m "
        "WHERE m.created_at >= ? GROUP BY m.sku",
        (today_start,),
    ).fetchall()
    price_by_sku = {it["sku"]: it["unit_price"] for it in items}
    sold_units = sum(max(0, r["units"] or 0) for r in sold)
    sold_value = round(sum(max(0, r["units"] or 0) * price_by_sku.get(r["sku"], 0.0)
                           for r in sold), 2)

    # Last 7 local days (oldest -> today), keyed off the caller's today-start
    # so day boundaries match the dashboard's timezone.
    try:
        day0 = datetime.strptime(today_start, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        day0 = datetime.strptime(_utc_today_start(), "%Y-%m-%dT%H:%M:%SZ")
    week = []
    for back in range(6, -1, -1):
        start = day0 - timedelta(days=back)
        end = start + timedelta(days=1)
        rows_day = conn.execute(
            f"SELECT m.sku, SUM({_SOLD_EXPR}) AS units FROM movements m "
            "WHERE m.created_at >= ? AND m.created_at < ? GROUP BY m.sku",
            (start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ).fetchall()
        units = sum(max(0, r["units"] or 0) for r in rows_day)
        value = round(sum(max(0, r["units"] or 0) * price_by_sku.get(r["sku"], 0.0)
                          for r in rows_day), 2)
        week.append({"date": start.strftime("%Y-%m-%d"), "units": units, "value": value})

    stats = {
        "skus": len(items),
        "units": sum(it["quantity"] for it in items),
        "value": round(sum(it["quantity"] * it["unit_price"] for it in items), 2),
        "low_count": sum(1 for it in items if it["status"] == "low"),
        "out_count": sum(1 for it in items if it["status"] == "out"),
        "sold_today_count": sold_units,
        "sold_today_value": sold_value,
    }
    movements = [dict(r) for r in conn.execute(
        "SELECT * FROM movements ORDER BY id DESC LIMIT ?", (history_limit,)
    ).fetchall()]
    categories = sorted({it["category"] for it in items if it["category"]})
    return {"generated_at": _db.now(), "items": items, "stats": stats,
            "categories": categories, "movements": movements, "week": week}


def cmd_snapshot(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Everything the module dashboard needs, in a single subprocess call."""
    _emit(_build_snapshot(conn, args.today_start, args.history_limit))
    return 0


_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _render_report(snap: dict, fmt: str = "md") -> str:
    """Render a human-readable inventory + sales report from a snapshot dict."""
    st = snap.get("stats", {})
    items = snap.get("items", [])
    low = [it for it in items if it.get("status") != "in_stock"]
    top = sorted(items, key=lambda it: it.get("spw", 0), reverse=True)
    top = [it for it in top if it.get("spw", 0) > 0][:5]
    week = snap.get("week", [])

    def money(n: float) -> str:
        return f"{n:,.0f} VND"

    md = fmt != "txt"
    h1 = (lambda s: f"# {s}") if md else (lambda s: s.upper())
    h2 = (lambda s: f"\n## {s}") if md else (lambda s: f"\n{s}\n" + "-" * len(s))
    L: list[str] = []
    L.append(h1("Warehouse report"))
    L.append(f"Generated: {snap.get('generated_at', '')}")
    L.append(h2("Summary"))
    L.append(f"- SKUs: {st.get('skus', 0)}")
    L.append(f"- Units on hand: {st.get('units', 0)}")
    L.append(f"- Inventory value: {money(st.get('value', 0))}")
    L.append(f"- Low stock: {st.get('low_count', 0)} | Out of stock: {st.get('out_count', 0)}")
    L.append(f"- Sold today: {st.get('sold_today_count', 0)} units "
             f"({money(st.get('sold_today_value', 0))})")

    L.append(h2("Needs restock"))
    if not low:
        L.append("Everything is at or above its reorder level.")
    elif md:
        L.append("| SKU | Name | Qty | Reorder | Status |")
        L.append("|-----|------|-----|---------|--------|")
        for it in low:
            L.append(f"| {it['sku']} | {it['name']} | {it['quantity']} | "
                     f"{it['reorder_level']} | {it['status']} |")
    else:
        for it in low:
            L.append(f"  {it['sku']:<10} {it['name'][:24]:<24} qty {it['quantity']:>4} "
                     f"(min {it['reorder_level']}) [{it['status']}]")

    L.append(h2("Top sellers (per week)"))
    if not top:
        L.append("No sales recorded yet.")
    else:
        for it in top:
            L.append(f"- {it['name']} — {it.get('spw', 0)}/week")

    L.append(h2("Sales, last 7 days"))
    if week:
        for w in week:
            try:
                wd = _WEEKDAYS[datetime.strptime(w["date"], "%Y-%m-%d").weekday()]
            except (ValueError, KeyError):
                wd = ""
            L.append(f"- {w.get('date', '')} ({wd}): {w.get('units', 0)} units, "
                     f"{money(w.get('value', 0))}")
    else:
        L.append("No data.")
    return "\n".join(L) + "\n"


def cmd_report(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Write (or print) a deterministic inventory + sales report."""
    snap = _build_snapshot(conn, history_limit=200)
    text = _render_report(snap, args.format)
    if args.out:
        out = Path(args.out)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        if args.json:
            _emit({"ok": True, "path": str(args.out),
                   "bytes": len(text.encode("utf-8"))})
        else:
            print(f"report written: {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def _parse_lines(raw: list[str]) -> tuple[list[tuple[str, int]], str | None]:
    lines: list[tuple[str, int]] = []
    for spec in raw:
        sku, eq, qty_s = spec.partition("=")
        if not eq or not sku.strip():
            return [], f"bad --line format (expect SKU=QTY): {spec}"
        try:
            qty = int(qty_s)
        except ValueError:
            return [], f"bad quantity in --line: {spec}"
        if qty < 1:
            return [], f"quantity must be >= 1: {spec}"
        lines.append((sku.strip(), qty))
    return lines, None


def cmd_sell(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Record a (possibly multi-line) sale atomically under one reference."""
    lines, problem = _parse_lines(args.line)
    if problem or not lines:
        _err(problem or "at least one --line SKU=QTY is required")
        return 1
    # Validate every line before touching anything: all-or-nothing.
    rows: dict[str, sqlite3.Row] = {}
    for sku, qty in lines:
        row = rows.get(sku) or _find(conn, sku)
        if row is None:
            _err(f"SKU not found: {sku}")
            return 1
        rows[sku] = row
    totals: dict[str, int] = {}
    for sku, qty in lines:
        totals[sku] = totals.get(sku, 0) + qty
    for sku, qty in totals.items():
        if rows[sku]["quantity"] - qty < 0:
            _err(f"insufficient stock for {sku}: have {rows[sku]['quantity']}, need {qty}")
            return 1

    reference = args.reference or _db.gen_reference("SALE")
    ts = _db.now()
    out_lines = []
    total_value = 0.0
    for sku, qty in totals.items():
        balance = rows[sku]["quantity"] - qty
        conn.execute("UPDATE items SET quantity = ?, updated_at = ? WHERE sku = ?",
                     (balance, ts, sku))
        _db.log_movement(conn, sku, "ship", -qty, balance,
                         reason=args.reason, reference=reference, commit=False)
        total_value += qty * float(rows[sku]["unit_price"])
        out_lines.append({"sku": sku, "qty": qty, "balance": balance})
    conn.commit()
    if args.json:
        _emit({"ok": True, "reference": reference, "lines": out_lines,
               "total_value": round(total_value, 2)})
    else:
        print(f"sold: {', '.join(f'{q}x {s}' for s, q in totals.items())} ref={reference}")
    return 0


def cmd_revert(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Undo a sale/receipt by writing compensating movements (ledger stays append-only)."""
    ref = args.reference
    origs = conn.execute(
        "SELECT * FROM movements WHERE reference = ? AND kind IN ('ship', 'receive') "
        "ORDER BY id", (ref,),
    ).fetchall()
    if not origs:
        _err(f"reference not found (or not revertible): {ref}")
        return 1
    already = conn.execute(
        "SELECT COUNT(*) FROM movements WHERE reference = ? AND kind = 'revert'", (ref,)
    ).fetchone()[0]
    if already:
        _err(f"reference already reverted: {ref}")
        return 1
    # Validate all compensations first: all-or-nothing.
    deltas: dict[str, int] = {}
    for m in origs:
        deltas[m["sku"]] = deltas.get(m["sku"], 0) - m["delta"]
    rows: dict[str, sqlite3.Row] = {}
    for sku, delta in deltas.items():
        row = _find(conn, sku)
        if row is None:
            _err(f"SKU no longer exists: {sku}")
            return 1
        if row["quantity"] + delta < 0:
            _err(f"cannot revert {ref}: {sku} would go negative "
                 f"({row['quantity']} {delta:+d})")
            return 1
        rows[sku] = row

    ts = _db.now()
    out_lines = []
    balances = {sku: rows[sku]["quantity"] for sku in rows}
    for m in origs:
        sku = m["sku"]
        balances[sku] += -m["delta"]
        conn.execute("UPDATE items SET quantity = ?, updated_at = ? WHERE sku = ?",
                     (balances[sku], ts, sku))
        _db.log_movement(conn, sku, "revert", -m["delta"], balances[sku],
                         reason=f"revert {m['kind']}", reference=ref, commit=False)
        out_lines.append({"sku": sku, "delta": -m["delta"], "balance": balances[sku]})
    conn.commit()
    if args.json:
        _emit({"ok": True, "reference": ref, "lines": out_lines})
    else:
        print(f"reverted: {ref} ({len(out_lines)} movement(s))")
    return 0


def cmd_mark_ordered(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    by = args.by or "You"
    conn.execute("UPDATE items SET ordered_by = ?, ordered_at = ?, updated_at = ? WHERE sku = ?",
                 (by, _db.now(), _db.now(), args.sku))
    _db.log_movement(conn, args.sku, "mark-ordered", 0, row["quantity"],
                     reason=f"ordered by {by}", commit=False)
    conn.commit()
    if args.json:
        _emit({"ok": True, "item": _db.item_dict(_find(conn, args.sku))})
    else:
        print(f"mark-ordered: {args.sku} by {by}")
    return 0


def cmd_unmark_ordered(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    row = _find(conn, args.sku)
    if row is None:
        _err(f"SKU not found: {args.sku}")
        return 1
    conn.execute("UPDATE items SET ordered_by = NULL, ordered_at = NULL, updated_at = ? "
                 "WHERE sku = ?", (_db.now(), args.sku))
    _db.log_movement(conn, args.sku, "unmark-ordered", 0, row["quantity"],
                     reason="order mark cleared", commit=False)
    conn.commit()
    if args.json:
        _emit({"ok": True, "item": _db.item_dict(_find(conn, args.sku))})
    else:
        print(f"unmark-ordered: {args.sku}")
    return 0


# ── argument parsing / dispatch ──────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Warehouse inventory (SQLite-backed).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="list items with optional filters")
    p.add_argument("--query", help="substring filter on sku/name")
    p.add_argument("--location", help="substring filter on location")
    p.add_argument("--low-only", action="store_true", help="only items at/below reorder level")
    p.add_argument("--min-price", type=float)
    p.add_argument("--max-price", type=float)
    p.add_argument("--sort", choices=sorted(_SORT_COLUMNS), default="sku")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("low-stock", help="list items at or below reorder level")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_low_stock)

    p = sub.add_parser("summary", help="aggregate KPIs (counts, units, value, low stock)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("valuation", help="inventory value grouped by location or sku")
    p.add_argument("--by", choices=["location", "sku"], default="location")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_valuation)

    p = sub.add_parser("history", help="movement ledger (newest first)")
    p.add_argument("--sku", help="restrict to one SKU")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_history)

    p = sub.add_parser("query", help="run a read-only SELECT against the DB")
    p.add_argument("--sql", required=True, help="a single SELECT/WITH statement")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_query)

    p = sub.add_parser("snapshot", help="single-call dashboard payload (always JSON)")
    p.add_argument("--today-start", help="ISO cutoff for the sold-today KPI (default: UTC midnight)")
    p.add_argument("--history-limit", type=int, default=50)
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("report", help="write a human-readable inventory + sales report")
    p.add_argument("--out", help="write to this file (relative -> cwd); omit to print")
    p.add_argument("--format", choices=["md", "txt"], default="md")
    p.add_argument("--json", action="store_true", help="emit a JSON {ok, path, bytes} summary")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("add", help="add a new item")
    p.add_argument("--sku", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--name-vi", help="Vietnamese display name")
    p.add_argument("--category")
    p.add_argument("--location", default="")
    p.add_argument("--quantity", type=int, required=True)
    p.add_argument("--unit-price", type=float, required=True)
    p.add_argument("--reorder-level", type=int, required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("update", help="patch fields on an existing item")
    p.add_argument("--sku", required=True)
    p.add_argument("--name")
    p.add_argument("--name-vi")
    p.add_argument("--category")
    p.add_argument("--location")
    p.add_argument("--quantity", type=int)
    p.add_argument("--unit-price", type=float)
    p.add_argument("--reorder-level", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("adjust", help="add a delta to quantity")
    p.add_argument("--sku", required=True)
    p.add_argument("--delta", type=int, required=True)
    p.add_argument("--reason")
    p.add_argument("--reference")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_adjust)

    p = sub.add_parser("receive", help="receive stock (positive movement; clears ordered mark)")
    p.add_argument("--sku", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--reason")
    p.add_argument("--reference")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_receive)

    p = sub.add_parser("ship", help="ship stock (negative movement)")
    p.add_argument("--sku", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--reason")
    p.add_argument("--reference")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ship)

    p = sub.add_parser("sell", help="record a sale: one ship movement per --line SKU=QTY")
    p.add_argument("--line", action="append", required=True, metavar="SKU=QTY")
    p.add_argument("--reason", default="sale")
    p.add_argument("--reference", help="override the generated SALE-… reference")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_sell)

    p = sub.add_parser("revert", help="undo a sale/receipt by reference (compensating movements)")
    p.add_argument("--reference", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_revert)

    p = sub.add_parser("mark-ordered", help="flag an item as reordered (pending arrival)")
    p.add_argument("--sku", required=True)
    p.add_argument("--by", help="who placed the order (default: You)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_mark_ordered)

    p = sub.add_parser("unmark-ordered", help="clear an item's reordered flag")
    p.add_argument("--sku", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_unmark_ordered)

    p = sub.add_parser("move", help="change an item's location")
    p.add_argument("--sku", required=True)
    p.add_argument("--location", required=True)
    p.set_defaults(fn=cmd_move)

    p = sub.add_parser("set-reorder", help="set an item's reorder level")
    p.add_argument("--sku", required=True)
    p.add_argument("--level", type=int, required=True)
    p.set_defaults(fn=cmd_set_reorder)

    p = sub.add_parser("remove", help="delete an item")
    p.add_argument("--sku", required=True)
    p.set_defaults(fn=cmd_remove)

    p = sub.add_parser("reset", help="empty the items and movements tables")
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("export", help="dump items or movements to csv/json")
    p.add_argument("--table", choices=["items", "movements"], default="items")
    p.add_argument("--format", choices=["csv", "json"], default="json")
    p.add_argument("--out", help="write to this path instead of stdout")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("import", help="bulk load items from csv/json (--file - reads stdin)")
    p.add_argument("--file", required=True)
    p.add_argument("--format", choices=["csv", "json"], default="csv")
    p.add_argument("--replace", action="store_true", help="clear items before importing")
    p.add_argument("--json", action="store_true", help="emit a JSON import summary")
    p.set_defaults(fn=cmd_import)

    p = sub.add_parser("migrate", help="one-shot import from the legacy inventory.csv")
    p.set_defaults(fn=cmd_migrate)

    return parser


def _validate_query(sql: str) -> str | None:
    """Return an error string if ``sql`` is not a safe single read-only statement."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "empty query"
    if ";" in stripped:
        return "only a single statement is allowed"
    head = stripped.lstrip("(").lstrip().split(None, 1)[0].lower()
    if head not in ("select", "with"):
        return "only SELECT / WITH queries are allowed"
    return None


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])

    if args.cmd == "query":
        problem = _validate_query(args.sql)
        if problem:
            _err(problem)
            return 1
        conn = _db.connect_readonly()
        try:
            return args.fn(conn, args)
        except sqlite3.Error as exc:
            _err(f"query failed: {exc}")
            return 1
        finally:
            conn.close()

    conn = _db.connect()
    try:
        return args.fn(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
