"""Import the Track-7 Group Drive dataset (xlsx) into module data JSONs.

Dev-time tool (needs pandas + openpyxl from the repo venv); runtime code only ever
reads the committed JSON, so the module itself stays stdlib-only. Converts all
sheets to snake_case JSON and — crucially — translates each Trip Event row into a
STRUCTURED TELEMETRY INJECTION. The 15-minute GPS samples do not carry most event
signals (e.g. "4.8 km behind" while the traces show 0.63 km), so the events sheet
is the scenario script: at simulation time the injections are overlaid on the
interpolated trace baseline, and the detection rules consume only that telemetry
stream — never the event labels. The events themselves remain the eval gold.

Also derives the demo *user personas* (data/users.json): 8 distinct people taken
from the Trip Members sheet (dedup by name, favouring variety of role / vehicle /
privacy / voice). Colors: the four Marlow Bay v3 member colors + four more in the
same muted family; U01 is always the v3 "You" blue #5d8bc4.

Usage (run with PYTHONUTF8=1):
  python import_track7.py --xlsx "<path to ai_maps_track7_dataset_participants.xlsx>"
                          [--out ../data/track7.json] [--users ../data/users.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

MODULE_DIR = Path(__file__).resolve().parent.parent

# v3 member colors first (You-blue, pink, amber, green), then 4 more muted tones
# in the same family for the remaining personas.
PALETTE = ["#5d8bc4", "#d86f9c", "#c9862e", "#5f9e6e",
           "#8b6fd8", "#c4574a", "#4f8f8b", "#a0729c"]

# Personas kept for the demo user pool: real-named TRIP001 family + the most
# distinctive leaders/personas from the other trips (variety of vehicle, privacy,
# voice). Selection is by member_id, names come from the sheet (data-derived).
PERSONA_SLOTS = ["M001", "M002", "M003", "M004", "M005", "M010", "M013", "M017"]


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.rename(columns={c: _snake(str(c)) for c in df.columns})
    out = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if pd.isna(v):
                clean[k] = None
            elif hasattr(v, "item"):          # numpy scalar -> python
                clean[k] = v.item()
            elif isinstance(v, pd.Timestamp):
                clean[k] = v.isoformat(sep=" ")
            else:
                clean[k] = v
        out.append(clean)
    return out


def _yes(v) -> bool:
    return str(v or "").strip().lower() in ("yes", "y", "true", "1")


_PRIVACY = {"all members": "all", "leader only": "leader_only",
            "temporary sharing": "temporary"}


# ── Trip Event -> structured telemetry injection ────────────────────────────
# The injection describes WHAT THE SENSORS WOULD SHOW, derived from the event
# type + numbers regex-extracted from observed_signal. Detection rules never see
# the event_type; they see only these sensor effects on the tick stream.

# Unit-aware extraction: vehicle labels ("Bike 2", "EV 3", "KM62") pollute a
# bare-number regex, so only unit-tagged quantities are trusted.
_KM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*km\b", re.I)
_MIN_RE = re.compile(r"\+?\s*(\d+(?:\.\d+)?)\s*min(?:ute)?s?\b", re.I)


def _km_of(text: str) -> float | None:
    m = _KM_RE.search(text or "")
    return float(m.group(1)) if m else None


def _min_of(text: str) -> float | None:
    m = _MIN_RE.search(text or "")
    return float(m.group(1)) if m else None


def _injection(ev: dict) -> dict:
    """Map one Trip Events row to sensor effects around ev['timestamp_min']."""
    etype = (ev.get("event_type") or "").strip().lower()
    sig = ev.get("observed_signal") or ""
    t = int(ev["timestamp_min"])
    inj: dict = {"t": t, "member_id": ev["member_id"], "channels": {}}
    ch = inj["channels"]
    km, mins = _km_of(sig), _min_of(sig)

    if etype == "wrong turn":
        # off-route + the ETA gap the signal reports (default modest)
        ch["route_status"] = {"value": "off_route", "duration_min": 12}
        ch["eta_gap_min"] = {"value": mins if mins is not None else 10.0,
                             "ramp_min": 4}
    elif etype in ("falling behind", "group split"):
        if km is not None:
            ch["distance_from_leader_km"] = {"value": km, "ramp_min": 10}
        if mins is not None:
            ch["eta_gap_min"] = {"value": mins, "ramp_min": 10}
        if km is None and mins is None:  # be explicit rather than silently weak
            ch["eta_gap_min"] = {"value": 8.0, "ramp_min": 10}
    elif etype == "delay building":
        ch["eta_gap_min"] = {"value": mins if mins is not None else 10.0,
                             "ramp_min": 8}
    elif etype == "gps weak signal":
        ch["gps_silent"] = {"duration_min": int(mins or 5)}
    elif etype == "unexpected stop":
        dur = int(mins or 6)
        ch["speed_kmh"] = {"value": 0.0, "duration_min": dur}
        ch["route_status"] = {"value": "stopped", "duration_min": dur}
    elif etype == "low battery":
        ch["route_status"] = {"value": "needs_charging", "duration_min": 20}
        ch["battery_pct"] = {"value": 12.0}
    elif etype == "rest request":
        # a member MESSAGE, not a sensor change
        ch["member_message"] = {"text_vi": "Tôi cần nghỉ 10 phút",
                                "text_en": "I need a break"}
    elif etype == "heavy rain ahead":
        inj["external"] = True
        ch["weather"] = {"kind": "heavy_rain", "scope": "route"}
    else:
        inj["unmapped"] = True
    return inj


def build(xlsx: Path) -> tuple[dict, dict]:
    xl = pd.ExcelFile(xlsx)
    sheets = {s: _records(xl.parse(s)) for s in xl.sheet_names}

    events = sheets.get("Trip Events", [])
    for ev in events:
        ev["injection"] = _injection(ev)

    voice = sheets.get("Voice Commands", [])
    for vc in voice:
        raw = vc.get("expected_structured_action")
        if isinstance(raw, str):
            try:
                vc["expected_structured_action"] = json.loads(raw)
            except ValueError:
                pass  # keep as string; eval will flag it

    track7 = {
        "meta": {
            "source": xlsx.name,
            "source_sha1": hashlib.sha1(xlsx.read_bytes()).hexdigest(),
            "note": ("Synthetic Track-7 dataset (see README sheet). Injections are "
                     "the scenario script derived from observed_signal; detection "
                     "rules consume telemetry only, events stay eval gold."),
        },
        "readme": sheets.get("README", []),
        "trips": sheets.get("Group Trips", []),
        "members": sheets.get("Trip Members", []),
        "waypoints": sheets.get("Route Waypoints", []),
        "regroup_pois": sheets.get("Regroup POIs", []),
        "traces": sheets.get("GPS Traces", []),
        "trip_events": events,
        "voice_commands": voice,
        "eval_scenarios": sheets.get("Public Evaluation", []),
    }

    by_id = {m["member_id"]: m for m in track7["members"]}
    users = []
    for i, mid in enumerate(PERSONA_SLOTS):
        m = by_id[mid]
        name = str(m["member_name"])
        users.append({
            "user_id": f"U{i + 1:02d}",
            "name": name,
            "initial": name.split()[-1][0].upper(),
            "color": PALETTE[i],
            "vehicle_pref": m["vehicle_type"],
            "privacy_pref": _PRIVACY.get(str(m["privacy_setting"]).lower(), "all"),
            "voice_enabled": _yes(m["voice_enabled"]),
            "source_member_id": mid,
        })
    users_doc = {"users": users, "count": len(users)}
    return track7, users_doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Track-7 xlsx -> module data JSONs")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--out", default=str(MODULE_DIR / "data" / "track7.json"))
    ap.add_argument("--users", default=str(MODULE_DIR / "data" / "users.json"))
    args = ap.parse_args()

    xlsx = Path(args.xlsx)
    if not xlsx.exists():
        print(json.dumps({"ok": False, "error": f"xlsx not found: {xlsx}"}))
        return 2
    track7, users_doc = build(xlsx)

    Path(args.out).write_text(
        json.dumps(track7, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.users).write_text(
        json.dumps(users_doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps({
        "ok": True, "out": args.out, "users": args.users,
        "counts": {k: len(v) for k, v in track7.items()
                   if isinstance(v, list)},
        "personas": [u["name"] for u in users_doc["users"]],
        "injections_mapped": sum(1 for e in track7["trip_events"]
                                 if not e["injection"].get("unmapped")),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
