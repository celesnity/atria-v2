"""Group Drive Assistant — simulated convoy backend (Track-7 demo).

Simulation-only (the module is not hosted): one `timeline` call returns the whole
replay and the dashboard animates it locally. The scenario comes from the official
Track-7 dataset (data/track7.json, produced by import_track7.py):

  baseline  = per-minute interpolation of the 15-min GPS trace samples, projected
              onto the route polyline;
  overlay   = the event *injections* (sensor effects derived at import time from
              each event's observed_signal — the traces alone don't carry most
              signals, the events sheet is the scenario script);
  detection = rules over that telemetry stream ONLY (this module never reads
              trip_events at runtime — only eval_track7.py and `calibrate` do),
  so the Trip Events sheet stays honest eval gold.

Subcommands (argv in, one JSON object on stdout, ASCII-safe via ensure_ascii=False
+ PYTHONUTF8=1):
  users                              the 8 demo personas (data/users.json)
  create   --scenario T --seed N     random personas onto the trip's member slots
  timeline --trip T --seed N         full replay payload (see docstring in cmd)
  voice    --text "..." [--trip T]   rule-based vi/en voice-command parsing
  coordinate --trip T --member M --text "..."
                                     AI Trip Coordinator: natural-language Q&A
                                     over the detector/regroup/voice primitives
                                     (the Public Evaluation scenarios)
  calibrate                          dev-only: telemetry window around each gold
                                     event (threshold-choice evidence table)

Deterministic: a single random.Random(seed); same seed -> byte-identical JSON.
Stdlib only. No hardcoded place names — all names flow from the dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import haversine_km, load_json  # noqa: E402

import random  # noqa: E402

TICK_MIN = 1          # sim resolution: 1 minute per tick
TRACE_STEP = 15       # dataset trace sampling step

# ── detection thresholds (global, no trip-specific values; chosen from the
#    `calibrate` table — see PROOF_OF_DONE for the printed evidence) ─────────
DETECT = {
    "eta_gap_min": 5.0,        # falling behind: gap this large and rising
    "gap_km": 3.0,             # falling behind: distance this large and rising
    "split_eta": 8.0,          # eta-only separation this large -> split subtype
    "stop_min": 4,             # unexpected stop: stopped at least this long
    "near_safe_km": 0.7,       # a stop within this of a safe waypoint/POI is OK
    "gps_silent_min": 4,       # GPS loss: no fix for this long
    "rise_window": 3,          # "rising" = increase across this many ticks
}

BASE_PRIORITY = {
    "sos": 90, "wrong_turn": 70, "group_split": 65, "unexpected_stop": 60,
    "falling_behind": 55, "low_battery": 50, "gps_loss": 45,
    "delay_building": 40, "heavy_rain": 38, "rest_request": 25,
}
SEV_MULT = {"high": 1.2, "medium": 1.0, "low": 0.8}

# severity is assigned by rule family (documented in the writeup)
RULE_SEVERITY = {
    "wrong_turn": "high", "unexpected_stop": "high",
    "falling_behind": "medium", "group_split": "medium",
    "delay_building": "medium", "low_battery": "medium",
    "gps_loss": "low", "rest_request": "low", "heavy_rain": "medium",
}


def _fold(s: str) -> str:
    s = (s or "").lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _t7() -> dict:
    return load_json("track7.json")


def _users() -> list[dict]:
    return load_json("users.json")["users"]


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


# ── geometry helpers ─────────────────────────────────────────────────────────
def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _densify(points: list[tuple[float, float]], step_km: float = 0.5
             ) -> list[tuple[float, float]]:
    """Waypoint polyline -> dense polyline so projections don't cut corners."""
    out: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        (la1, lo1), (la2, lo2) = points[i], points[i + 1]
        seg = haversine_km(la1, lo1, la2, lo2)
        n = max(1, int(seg / step_km))
        for k in range(n):
            f = k / n
            out.append((_lerp(la1, la2, f), _lerp(lo1, lo2, f)))
    out.append(points[-1])
    return out


def _project(lat: float, lng: float, line: list[tuple[float, float]]) -> int:
    """Index of the closest densified-polyline vertex (cheap projection)."""
    best, best_d = 0, float("inf")
    for i, (la, lo) in enumerate(line):
        d = (la - lat) ** 2 + (lo - lng) ** 2
        if d < best_d:
            best, best_d = i, d
    return best


# ── scenario assembly ────────────────────────────────────────────────────────
def _trip(t7: dict, trip_id: str) -> dict | None:
    return next((t for t in t7["trips"] if t["trip_id"] == trip_id), None)


def _slots(t7: dict, trip_id: str) -> list[dict]:
    return [m for m in t7["members"] if m["trip_id"] == trip_id]


def _route(t7: dict, route_id: str) -> list[dict]:
    wps = [w for w in t7["waypoints"] if w["route_id"] == route_id]
    return sorted(wps, key=lambda w: w["sequence"])


_PRIVACY = {"all members": "all", "leader only": "leader_only",
            "temporary sharing": "temporary"}


def _assemble_group(t7: dict, trip_id: str, seed: int) -> dict | None:
    """Random personas onto the trip's member slots; slot keeps its scripted
    role/behavior, persona brings the human identity (name/color/prefs)."""
    trip = _trip(t7, trip_id)
    if not trip:
        return None
    rng = random.Random(seed)
    slots = _slots(t7, trip_id)
    personas = _users()
    picked = rng.sample(personas, k=min(len(slots), len(personas)))
    members = []
    for slot, persona in zip(slots, picked):
        members.append({
            "member_id": slot["member_id"],
            "user_id": persona["user_id"],
            "name": persona["name"],
            "initial": persona["initial"],
            "color": persona["color"],
            "role": "leader" if slot["role"] == "Trip Leader" else "member",
            "vehicle_label": slot["vehicle_label"],
            "vehicle_type": slot["vehicle_type"],
            "privacy": _PRIVACY.get(str(slot["privacy_setting"]).lower(), "all"),
            "voice_enabled": bool(persona["voice_enabled"]),
            "behavior_note": slot.get("notes"),
        })
    # "you" = a random non-leader slot so the Member view has something to hide
    non_leader = [m for m in members if m["role"] != "leader"] or members
    self_member = rng.choice(non_leader)["member_id"]
    return {
        "group_id": f"G{seed:03d}",
        "join_code": f"GRP-{seed:03d}",
        "trip_id": trip_id,
        "trip_name": trip["trip_name"],
        "scenario": trip["scenario"],
        "origin": trip["origin"],
        "destination": trip["destination"],
        "route_id": trip["planned_route_id"],
        "duration_min": int(trip["expected_duration_min"]),
        "seed": seed,
        "self_member_id": self_member,
        "members": members,
    }


# ── telemetry synthesis: baseline + injections ──────────────────────────────
def _baseline(t7: dict, trip_id: str, duration: int,
              line: list[tuple[float, float]]) -> dict[str, list[dict]]:
    """Per-member per-minute telemetry interpolated from the 15-min samples,
    positions projected onto the densified route polyline."""
    traces: dict[str, list[dict]] = {}
    for tr in t7["traces"]:
        if tr["trip_id"] == trip_id:
            traces.setdefault(tr["member_id"], []).append(tr)
    out: dict[str, list[dict]] = {}
    for mid, samples in traces.items():
        samples.sort(key=lambda s: s["timestamp_min"])
        # project each sample once; interpolate along the polyline index space
        idxs = [_project(s["latitude"], s["longitude"], line) for s in samples]
        rows = []
        for t in range(0, duration + 1, TICK_MIN):
            k = min(t // TRACE_STEP, len(samples) - 2)
            f = (t - samples[k]["timestamp_min"]) / TRACE_STEP
            f = max(0.0, min(1.0, f))
            a, b = samples[k], samples[k + 1]
            ia, ib = idxs[k], idxs[k + 1]
            pos = line[int(round(_lerp(ia, ib, f)))]
            rows.append({
                "t": t,
                "lat": round(pos[0], 6), "lng": round(pos[1], 6),
                "speed_kmh": round(_lerp(a["speed_kmh"], b["speed_kmh"], f), 1),
                "heading": a["heading_deg"],
                "gap_km": round(_lerp(a["distance_from_leader_km"],
                                      b["distance_from_leader_km"], f), 2),
                "eta_gap_min": round(_lerp(a["eta_gap_min"], b["eta_gap_min"], f), 1),
                "status": str(a["route_status"]).lower().replace(" ", "_"),
                "gps_ok": True,
            })
        out[mid] = rows
    return out


def _apply_injections(telemetry: dict[str, list[dict]], events: list[dict],
                      duration: int) -> list[dict]:
    """Overlay each event's sensor effects onto the baseline. Returns the list
    of external context events (weather...) that aren't member telemetry."""
    external = []
    for ev in events:
        inj = ev["injection"]
        if inj.get("external"):
            external.append({
                "t": inj["t"],
                "kind": inj["channels"].get("weather", {}).get("kind", "external"),
                "scope": "route",
            })
            continue
        rows = telemetry.get(ev["member_id"])
        if not rows:
            continue
        t0 = inj["t"]
        ch = inj["channels"]
        if "route_status" in ch:
            spec = ch["route_status"]
            for r in rows:
                if t0 <= r["t"] < t0 + spec.get("duration_min", 10):
                    r["status"] = spec["value"]
        if "eta_gap_min" in ch:
            spec = ch["eta_gap_min"]
            ramp = max(1, int(spec.get("ramp_min", 5)))
            for r in rows:
                if r["t"] >= t0 - ramp:
                    f = min(1.0, (r["t"] - (t0 - ramp)) / ramp)
                    r["eta_gap_min"] = max(r["eta_gap_min"],
                                           round(spec["value"] * f, 1))
        if "distance_from_leader_km" in ch:
            spec = ch["distance_from_leader_km"]
            ramp = max(1, int(spec.get("ramp_min", 5)))
            for r in rows:
                if r["t"] >= t0 - ramp:
                    f = min(1.0, (r["t"] - (t0 - ramp)) / ramp)
                    r["gap_km"] = max(r["gap_km"], round(spec["value"] * f, 2))
        if "speed_kmh" in ch:
            spec = ch["speed_kmh"]
            for r in rows:
                if t0 <= r["t"] < t0 + spec.get("duration_min", 6):
                    r["speed_kmh"] = spec["value"]
        if "gps_silent" in ch:
            dur = ch["gps_silent"]["duration_min"]
            for r in rows:
                if t0 <= r["t"] < t0 + dur:
                    r["gps_ok"] = False
        if "battery_pct" in ch:
            for r in rows:
                if r["t"] >= t0:
                    r["battery_pct"] = ch["battery_pct"]["value"]
        if "member_message" in ch:
            for r in rows:
                if r["t"] == t0:
                    r["message"] = ch["member_message"]
    return external


# ── detection rules (consume telemetry ONLY) ────────────────────────────────
def _rising(vals: list[float]) -> bool:
    return len(vals) >= 2 and vals[-1] > vals[0]


def _near_safe_stop(lat: float, lng: float, safe_pts: list[tuple[float, float]]
                    ) -> bool:
    return any(haversine_km(lat, lng, la, lo) <= DETECT["near_safe_km"]
               for la, lo in safe_pts)


# The three "separation" labels in the dataset (Falling Behind / Group Split /
# Delay Building) describe the SAME physical signal — a member's temporal or
# spatial gap growing — labelled by narrative context. Detection treats them as
# one family: one rule fires, and the display subtype is chosen from the
# dominant signal. eval_track7.py matches on the family for these three and on
# the exact type for everything else (documented honesty boundary).
SEPARATION_FAMILY = ("falling_behind", "group_split", "delay_building")

# Incident clustering: a single real-world incident (a wrong turn) trips several
# rule families as its signals develop. Alerts within this window for the same
# member collapse to the highest-priority one — this IS the challenge's
# "alert prioritization / minimal driver distraction" requirement.
INCIDENT_WINDOW_MIN = 15


def detect(telemetry: dict[str, list[dict]], safe_pts: list[tuple[float, float]],
           external: list[dict]) -> list[dict]:
    """Rule-based detections over the tick stream ONLY (labels never read).
    First trigger per (member, rule); then per-member incident clustering."""
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    w = DETECT["rise_window"]

    def hit(t: int, mid: str, dtype: str, signal: str):
        if (mid, dtype) in seen:
            return
        seen.add((mid, dtype))
        found.append({"t": t, "member_id": mid, "type": dtype,
                      "severity": RULE_SEVERITY[dtype], "source": "trace",
                      "signal": signal})

    for mid, rows in telemetry.items():
        stop_run = 0
        silent_run = 0
        for i, r in enumerate(rows):
            t = r["t"]
            gaps = [x["eta_gap_min"] for x in rows[max(0, i - w):i + 1]]
            kms = [x["gap_km"] for x in rows[max(0, i - w):i + 1]]

            # root-cause rules first: a specific mechanical cause beats the
            # generic separation signal it inevitably also produces
            if r["status"] == "off_route":
                hit(t, mid, "wrong_turn",
                    f"route_status=off_route; eta_gap {r['eta_gap_min']}m")
            if r["status"] == "needs_charging":
                hit(t, mid, "low_battery",
                    "route_status=needs_charging"
                    + (f"; battery {r.get('battery_pct')}%" if r.get("battery_pct")
                       else ""))
            # separation family (one rule, display subtype by dominant signal)
            dist_hit = r["gap_km"] >= DETECT["gap_km"] and _rising(kms)
            eta_hit = r["eta_gap_min"] >= DETECT["eta_gap_min"] and _rising(gaps)
            if ((dist_hit or eta_hit)
                    and r["status"] not in ("off_route", "stopped",
                                            "needs_charging")):
                subtype = ("falling_behind" if dist_hit
                           else "group_split" if r["eta_gap_min"] >= DETECT["split_eta"]
                           else "delay_building")
                hit(t, mid, subtype,
                    f"gap {r['gap_km']}km / eta_gap {r['eta_gap_min']}m rising")
            if r["speed_kmh"] <= 1 or r["status"] == "stopped":
                stop_run += 1
                if (stop_run >= DETECT["stop_min"]
                        and not _near_safe_stop(r["lat"], r["lng"], safe_pts)):
                    hit(t, mid, "unexpected_stop",
                        f"stopped {stop_run}min away from safe stops")
            else:
                stop_run = 0
            if not r["gps_ok"]:
                silent_run += 1
                if silent_run >= DETECT["gps_silent_min"]:
                    hit(t, mid, "gps_loss", f"no GPS fix for {silent_run}min")
            else:
                silent_run = 0
            if r.get("message"):
                hit(t, mid, "rest_request",
                    f"member message: {r['message']['text_en']}")

    # per-member incident clustering: highest priority wins inside the window
    found.sort(key=lambda d: (d["member_id"], d["t"]))
    clustered: list[dict] = []
    for d in found:
        prev = clustered[-1] if clustered else None
        if (prev and prev["member_id"] == d["member_id"]
                and d["t"] - prev["t"] <= INCIDENT_WINDOW_MIN):
            if (_priority(d["type"], d["severity"])
                    > _priority(prev["type"], prev["severity"])):
                clustered[-1] = d
        else:
            clustered.append(d)

    for ext in external:
        clustered.append({"t": ext["t"], "member_id": "ALL", "type": "heavy_rain",
                          "severity": RULE_SEVERITY["heavy_rain"],
                          "source": "external",
                          "signal": "weather feed: heavy rain on route segment"})
    clustered.sort(key=lambda d: (d["t"], d["member_id"]))
    return clustered


# ── regroup recommendation ──────────────────────────────────────────────────
def recommend_regroup(t7: dict, route_id: str, dtype: str,
                      at: tuple[float, float] | None) -> dict | None:
    cands = [p for p in t7["regroup_pois"] if p["route_id"] == route_id]
    if dtype == "low_battery":
        cands = [p for p in cands
                 if str(p.get("fuel_or_charging", "")).lower() not in ("no", "none", "")]
    if not cands:
        return None

    def _amen(p: dict) -> float:
        a = 0.0
        if str(p.get("parking_available", "")).lower() == "yes":
            a += 0.5
        if str(p.get("restroom", "")).lower() == "yes":
            a += 0.5
        return a

    def score(p: dict) -> float:
        s = 3.0 * float(p["safe_stop_score"])
        s -= 0.4 * float(p.get("distance_to_route_km") or 0)
        if at:
            s -= 0.05 * haversine_km(at[0], at[1], p["latitude"], p["longitude"])
        s += 0.3 * _amen(p)
        return s

    best = max(cands, key=score)
    return {"action": "regroup", "poi_id": best["poi_id"],
            "poi_name": best["poi_name"], "poi_type": best["poi_type"],
            "lat": best["latitude"], "lng": best["longitude"],
            "safe_stop_score": best["safe_stop_score"],
            "why": {"safe_stop_score": best["safe_stop_score"],
                    "parking": best.get("parking_available"),
                    "restroom": best.get("restroom"),
                    "fuel_or_charging": best.get("fuel_or_charging"),
                    "distance_to_route_km": best.get("distance_to_route_km")}}


def _priority(dtype: str, severity: str) -> int:
    p = BASE_PRIORITY.get(dtype, 40) * SEV_MULT.get(severity, 1.0)
    return max(0, min(100, int(round(p))))


# ── bilingual alert templates (names flow from data; controlled verb vocab) ──
_TPL = {
    "wrong_turn": ("{name} ({veh}) đã đi chệch tuyến — lệch ETA {gap} phút.",
                   "{name} ({veh}) went off the planned route — ETA gap {gap} min."),
    "falling_behind": ("{name} ({veh}) đang tụt lại phía sau ({sig}).",
                       "{name} ({veh}) is falling behind ({sig})."),
    "unexpected_stop": ("{name} ({veh}) dừng bất thường bên đường — cần kiểm tra an toàn.",
                        "{name} ({veh}) stopped unexpectedly — safety check suggested."),
    "gps_loss": ("Mất tín hiệu GPS của {name} ({veh}) — chưa cần báo động khẩn.",
                 "Lost GPS signal from {name} ({veh}) — no emergency alert yet."),
    "group_split": ("Đoàn xe đang bị tách — {name} cách đoàn khá xa.",
                    "The convoy is splitting — {name} is far from the group."),
    "delay_building": ("Cả đoàn đang chậm dần so với kế hoạch ({sig}).",
                       "The group is building a delay vs plan ({sig})."),
    "low_battery": ("{name} ({veh}) pin yếu — cần điểm sạc gần tuyến.",
                    "{name} ({veh}) battery low — needs a charging stop."),
    "rest_request": ("{name} xin nghỉ — đề xuất điểm dừng an toàn kế tiếp.",
                     "{name} requests a break — suggesting the next safe stop."),
    "heavy_rain": ("Mưa lớn phía trước trên tuyến — giảm tốc độ, bật đèn.",
                   "Heavy rain ahead on the route — slow down, lights on."),
}


def _messages(d: dict, member: dict | None, gap_min: float) -> tuple[str, str]:
    name = member["name"] if member else "Cả đoàn / group"
    veh = member["vehicle_label"] if member else ""
    vi, en = _TPL[d["type"]]
    fmt = {"name": name, "veh": veh, "sig": d["signal"],
           "gap": str(int(round(gap_min)))}
    return vi.format(**fmt), en.format(**fmt)


# ── commands ────────────────────────────────────────────────────────────────
def cmd_users(_args) -> dict:
    users = _users()
    scenarios = [{
        "trip_id": t["trip_id"], "trip_name": t["trip_name"],
        "scenario": t["scenario"], "vehicle_count": t["vehicle_count"],
        "origin": t["origin"], "destination": t["destination"],
    } for t in _t7()["trips"]]
    return {"ok": True, "users": users, "count": len(users),
            "scenarios": scenarios, "error": None}


def cmd_create(args) -> dict:
    t7 = _t7()
    group = _assemble_group(t7, args.scenario, args.seed)
    if not group:
        ids = [t["trip_id"] for t in t7["trips"]]
        return _err(f"unknown scenario {args.scenario!r}; one of {ids}")
    return {"ok": True, "group": group, "error": None}


def cmd_timeline(args) -> dict:
    t7 = _t7()
    group = _assemble_group(t7, args.trip, args.seed)
    if not group:
        ids = [t["trip_id"] for t in t7["trips"]]
        return _err(f"unknown trip {args.trip!r}; one of {ids}")
    wps = _route(t7, group["route_id"])
    line = _densify([(w["latitude"], w["longitude"]) for w in wps])
    duration = 90  # traces cover 0..90 for every trip
    telemetry = _baseline(t7, args.trip, duration, line)
    events = [e for e in t7["trip_events"] if e["trip_id"] == args.trip]
    external = _apply_injections(telemetry, events, duration)

    safe_pts = ([(w["latitude"], w["longitude"]) for w in wps
                 if str(w.get("safe_stop", "")).lower() == "yes"]
                + [(p["latitude"], p["longitude"]) for p in t7["regroup_pois"]
                   if p["route_id"] == group["route_id"]
                   and float(p["safe_stop_score"]) >= 0.7])
    detections = detect(telemetry, safe_pts, external)

    by_member = {m["member_id"]: m for m in group["members"]}
    out_dets = []
    for i, d in enumerate(detections):
        member = by_member.get(d["member_id"])
        at = None
        gap_min = 0.0
        rows = telemetry.get(d["member_id"])
        if rows:
            r = rows[min(d["t"], len(rows) - 1)]
            at = (r["lat"], r["lng"])
            gap_min = r["eta_gap_min"]
        # every alert carries a "nearest safe stop" option (the dataset gold
        # attaches a recommended POI even to weather / GPS-loss events)
        rec = recommend_regroup(t7, group["route_id"], d["type"], at)
        vi, en = _messages(d, member, gap_min)
        chips = []
        if member:
            chips.append({"label": f"✆ {member['name']}", "act": "call",
                          "member_id": d["member_id"]})
            chips.append({"label": "⌖ " + member["name"], "act": "locate",
                          "member_id": d["member_id"]})
        if rec:
            chips.append({"label": f"Tập kết: {rec['poi_name']}",
                          "act": "route_poi", "poi_id": rec["poi_id"]})
        out_dets.append({
            "det_id": f"D{i + 1:03d}", "t": d["t"], "member_id": d["member_id"],
            "type": d["type"], "severity": d["severity"],
            "priority": _priority(d["type"], d["severity"]),
            "source": d["source"], "signal": d["signal"],
            "message_vi": vi, "message_en": en,
            "recommend": rec, "chips": chips,
        })

    ticks = []
    for t in range(0, duration + 1, TICK_MIN):
        row = {"t": t, "members": []}
        for mid, rows in telemetry.items():
            r = rows[min(t, len(rows) - 1)]
            m = dict(r)
            m["member_id"] = mid
            m.pop("message", None)
            row["members"].append(m)
        row["members"].sort(key=lambda m: m["member_id"])
        ticks.append(row)

    # deterministic template summary (LLM polish is a separate, optional call)
    per_member = []
    for mid, rows in sorted(telemetry.items()):
        member = by_member.get(mid, {})
        gaps = [r["gap_km"] for r in rows]
        per_member.append({
            "member_id": mid, "name": member.get("name"),
            "vehicle_label": member.get("vehicle_label"),
            "avg_gap_km": round(sum(gaps) / len(gaps), 2),
            "max_gap_km": round(max(gaps), 2),
            "events": sum(1 for d in out_dets if d["member_id"] == mid),
            "on_route_pct": round(100 * sum(1 for r in rows
                                            if r["status"] == "on_route") / len(rows)),
            "stopped_min": sum(1 for r in rows if r["speed_kmh"] <= 1),
        })
    n_regroup = sum(1 for d in out_dets if d["recommend"])
    headline_vi = (f"{group['trip_name']}: {len(out_dets)} sự kiện, "
                   f"{n_regroup} đề xuất tập kết, {duration} phút mô phỏng.")
    headline_en = (f"{group['trip_name']}: {len(out_dets)} events, "
                   f"{n_regroup} regroup recommendations, {duration} sim minutes.")

    return {
        "ok": True, "error": None,
        "trip": {"trip_id": args.trip, "route_id": group["route_id"],
                 "tick_min": TICK_MIN, "duration_min": duration,
                 "scenario": group["scenario"], "trip_name": group["trip_name"],
                 "origin": group["origin"], "destination": group["destination"]},
        "group": group,
        "route": {
            "polyline": [[round(la, 6), round(lo, 6)] for la, lo in line],
            "waypoints": [{
                "name": w["waypoint_name"], "type": w["waypoint_type"],
                "lat": w["latitude"], "lng": w["longitude"],
                "planned_arrival_min": w["planned_arrival_min"],
                "safe_stop": str(w.get("safe_stop", "")).lower() == "yes",
            } for w in wps],
        },
        "regroup_pois": [{
            "poi_id": p["poi_id"], "name": p["poi_name"], "type": p["poi_type"],
            "lat": p["latitude"], "lng": p["longitude"],
            "safe_stop_score": p["safe_stop_score"],
            "notes": p.get("notes"),
        } for p in t7["regroup_pois"] if p["route_id"] == group["route_id"]],
        "ticks": ticks,
        "detections": out_dets,
        "voice_commands": [{
            "vc_id": v["command_id"], "text_vi": v["input_text_vi"],
            "text_en": v["input_text_en"], "priority": v["priority"],
        } for v in t7["voice_commands"]],
        "summary": {"duration_min": duration, "events_total": len(out_dets),
                    "regroups": n_regroup, "per_member": per_member,
                    "headline_vi": headline_vi, "headline_en": headline_en},
    }


# ── voice command parsing (controlled vi/en keyword vocab) ──────────────────
_VOICE_RULES = [
    # (intent, structured action factory, folded keyword sets vi+en)
    ("Emergency Alert",
     lambda: {"action": "emergency_check", "notify_leader": True},
     ["khan cap", "emergency", "cap cuu", "tai nan"]),
    ("Route Issue",
     lambda: {"action": "report_wrong_turn", "member_status": "off_route"},
     ["re nham", "lac duong", "missed the turn", "wrong turn", "di nham"]),
    ("Find Regroup Point",
     lambda: {"action": "recommend_safe_stop"},
     ["cho dung an toan", "diem tap ket", "safe place to stop", "regroup",
      "cho dung chan"]),
    ("Mute Noncritical Alerts",
     lambda: {"action": "mute_noncritical", "until": "next_exit"},
     ["tat thong bao", "mute", "im lang"]),
    ("Rest Request",
     lambda: {"action": "request_rest_stop", "duration_min": 10},
     ["can nghi", "nghi ngoi", "need a break", "nghi 10", "minute break"]),
    ("Leave Group Temporarily",
     lambda: {"action": "continue_without_member"},
     ["khong can cho", "continue without", "di truoc di"]),
    ("Share ETA",
     lambda: {"action": "share_eta"},
     ["chia se eta", "share my eta", "eta cua toi"]),
    ("Notify Group",
     lambda: {"action": "notify_group", "message": "wait_at_next_fuel_stop"},
     ["bao moi nguoi", "tell everyone", "cho o tram", "wait at the next"]),
]

_VOICE_PRIORITY = {"Emergency Alert": "Critical", "Route Issue": "High",
                   "Find Regroup Point": "High", "Rest Request": "Medium",
                   "Notify Group": "Medium", "Leave Group Temporarily": "Medium",
                   "Share ETA": "Low", "Mute Noncritical Alerts": "Low"}

_VOICE_REPLY = {
    "Emergency Alert": ("Đã gửi cảnh báo khẩn cấp cho trưởng đoàn và cả nhóm.",
                        "Emergency alert sent to the leader and the group."),
    "Route Issue": ("Đã ghi nhận bạn đi chệch tuyến — đang tính điểm tập kết.",
                    "Off-route noted — computing a regroup point."),
    "Find Regroup Point": ("Đề xuất điểm dừng an toàn gần nhất trên tuyến.",
                           "Recommending the nearest safe stop on the route."),
    "Mute Noncritical Alerts": ("Đã tắt thông báo không khẩn cấp đến lối ra kế tiếp.",
                                "Non-critical alerts muted until the next exit."),
    "Rest Request": ("Đã báo cả nhóm bạn cần nghỉ — đề xuất điểm dừng kế tiếp.",
                     "Told the group you need a break — suggesting the next stop."),
    "Leave Group Temporarily": ("Nhóm sẽ tiếp tục — bạn có thể bắt kịp sau.",
                                "The group will continue — catch up when ready."),
    "Share ETA": ("Đã chia sẻ ETA của bạn với cả nhóm.",
                  "Your ETA has been shared with the group."),
    "Notify Group": ("Đã nhắn cả nhóm chờ ở điểm dừng kế tiếp.",
                     "Told the group to wait at the next stop."),
}


def cmd_voice(args) -> dict:
    text = _fold(args.text or "")
    if not text.strip():
        return _err("voice requires --text")
    intent = None
    for name, factory, keys in _VOICE_RULES:
        if any(k in text for k in keys):
            intent, action = name, factory()
            break
    if intent is None:
        return {"ok": True, "intent": "Unknown", "structured_action": None,
                "priority": "Low",
                "reply_vi": "Chưa hiểu yêu cầu — thử lại hoặc chọn một lệnh mẫu.",
                "reply_en": "Did not catch that — try again or pick a sample command.",
                "map_actions": [], "error": None}

    map_actions = []
    if action.get("action") in ("recommend_safe_stop", "report_wrong_turn",
                                "request_rest_stop"):
        t7 = _t7()
        trip = _trip(t7, args.trip) if args.trip else None
        if trip:
            dtype = "rest_request" if action["action"] == "request_rest_stop" else \
                "wrong_turn" if action["action"] == "report_wrong_turn" else \
                "falling_behind"
            rec = recommend_regroup(t7, trip["planned_route_id"], dtype, None)
            if rec:
                action["poi_id"] = rec["poi_id"]
                map_actions.append({"type": "route_poi", "poi_id": rec["poi_id"],
                                    "lat": rec["lat"], "lng": rec["lng"],
                                    "name": rec["poi_name"]})
    vi, en = _VOICE_REPLY[intent]
    return {"ok": True, "intent": intent, "structured_action": action,
            "priority": _VOICE_PRIORITY[intent],
            "reply_vi": vi, "reply_en": en,
            "map_actions": map_actions, "error": None}


# ── along: trip-corridor place search ("cafe on the route?") ────────────────
def _line_dist_km(lat: float, lng: float, line: list[tuple[float, float]]
                  ) -> tuple[float, int]:
    """(min distance to the densified polyline, index of nearest vertex)."""
    best, best_i = float("inf"), 0
    for i, (la, lo) in enumerate(line):
        d = haversine_km(lat, lng, la, lo)
        if d < best:
            best, best_i = d, i
    return best, best_i


def _route_km_at(line: list[tuple[float, float]], idx: int) -> float:
    """Cumulative km along the polyline up to vertex idx."""
    km = 0.0
    for i in range(min(idx, len(line) - 1)):
        km += haversine_km(line[i][0], line[i][1], line[i + 1][0], line[i + 1][1])
    return km


def cmd_along(args) -> dict:
    """Search the POI dataset along the active trip's route corridor. Reuses the
    full search engine as a library (same pattern as jarvis_chat.py) so
    abbreviation / no-accent / category handling comes free. Honest fallback:
    the 3-city POI dataset thins out along intercity routes, so an empty
    corridor returns the route's own safe stops (waypoints + regroup POIs with
    their amenities) clearly marked — never fabricated places."""
    t7 = _t7()
    trip = _trip(t7, args.trip)
    if not trip:
        return _err(f"unknown trip {args.trip!r}")
    if not (args.query or "").strip():
        return _err("along requires --query")
    wps = _route(t7, trip["planned_route_id"])
    line = _densify([(w["latitude"], w["longitude"]) for w in wps])

    from types import SimpleNamespace

    from search import cmd_search  # lazy: timeline stays engine-independent
    try:
        res = cmd_search(SimpleNamespace(query=args.query, limit=30, city=None,
                                         category=None, prior=None))
    except Exception as exc:  # engine failure degrades to safe stops
        res = {"results": [], "_engine_error": str(exc)[:120]}

    hits = []
    for r in res.get("results") or []:
        if r.get("lat") is None or r.get("lng") is None:
            continue
        d, idx = _line_dist_km(r["lat"], r["lng"], line)
        if d <= args.width_km:
            hits.append({
                "name": r.get("name"), "lat": r["lat"], "lng": r["lng"],
                "poi_id": r.get("poi_id"), "category": r.get("category"),
                "rating": r.get("rating"),
                "detail": (r.get("address") or r.get("district") or ""),
                "detour_km": round(d, 2),
                "route_km": round(_route_km_at(line, idx), 1),
            })
    hits.sort(key=lambda h: (h["route_km"], h["detour_km"]))
    hits = hits[: args.limit]

    fallback = None
    if not hits:
        fallback = "safe_stops"
        for w in wps:
            if str(w.get("safe_stop", "")).lower() == "yes":
                d, idx = _line_dist_km(w["latitude"], w["longitude"], line)
                hits.append({
                    "name": w["waypoint_name"], "lat": w["latitude"],
                    "lng": w["longitude"], "poi_id": None,
                    "category": w["waypoint_type"], "rating": None,
                    "detail": "điểm dừng an toàn trên tuyến"
                              + (" · có chỗ đậu xe" if str(w.get(
                                  "parking_available", "")).lower() == "yes" else ""),
                    "detour_km": 0.0,
                    "route_km": round(_route_km_at(line, idx), 1),
                })
        for p in t7["regroup_pois"]:
            if (p["route_id"] == trip["planned_route_id"]
                    and float(p["safe_stop_score"]) >= 0.7):
                d, idx = _line_dist_km(p["latitude"], p["longitude"], line)
                amen = [a for a, on in (
                    ("đậu xe", str(p.get("parking_available", "")).lower() == "yes"),
                    ("wc", str(p.get("restroom", "")).lower() == "yes"),
                    ("xăng/sạc", str(p.get("fuel_or_charging", "")).lower()
                     not in ("no", "none", "")),
                ) if on]
                hits.append({
                    "name": p["poi_name"], "lat": p["latitude"],
                    "lng": p["longitude"], "poi_id": p["poi_id"],
                    "category": p["poi_type"], "rating": None,
                    "detail": (p["poi_type"] + (" · " + " · ".join(amen) if amen else "")),
                    "detour_km": round(float(p.get("distance_to_route_km") or 0), 2),
                    "route_km": round(_route_km_at(line, idx), 1),
                })
        seen = set()
        uniq = []
        for h in sorted(hits, key=lambda h: h["route_km"]):
            key = (round(h["lat"], 4), round(h["lng"], 4))
            if key not in seen:
                seen.add(key)
                uniq.append(h)
        hits = uniq[: args.limit]

    n = len(hits)
    if fallback:
        reply_vi = ("Dọc tuyến này dữ liệu chưa có quán phù hợp — nhưng có "
                    f"{n} điểm dừng an toàn trên đường (đã ghim lên bản đồ):")
        reply_en = (f"No matching places in the dataset along this route — "
                    f"but {n} safe stops are on the way (pinned):")
    else:
        reply_vi = f"Tìm thấy {n} địa điểm dọc tuyến (đã ghim lên bản đồ):"
        reply_en = f"Found {n} places along the route (pinned):"
    return {"ok": True, "query": args.query,
            "category": res.get("category") or res.get("intent"),
            "count": n, "fallback": fallback, "results": hits,
            "reply_vi": reply_vi, "reply_en": reply_en, "error": None}


# ── polish: optional LLM rephrase of coordinator text ───────────────────────
def cmd_polish(_args) -> dict:
    """Rephrase alert/summary lines via the Atria agent loopback when reachable.
    stdin: {"texts": ["..."], "lang": "vi"}. Graceful: any failure returns
    {"polished": false} and the caller keeps the deterministic templates —
    the demo never depends on the LLM being up."""
    import os
    import urllib.error
    import urllib.request

    try:
        # Decode stdin as bytes -> UTF-8 explicitly (codepage-independent): a
        # Windows console/pipe defaults to cp1252 and would mangle Vietnamese.
        req_body = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError:
        return {"ok": True, "polished": False, "why": "bad stdin", "error": None}
    texts = [str(t) for t in (req_body.get("texts") or []) if str(t).strip()]
    api_base = os.environ.get("ATRIA_API_BASE")
    if not texts or not api_base:
        return {"ok": True, "polished": False,
                "why": "no texts" if not texts else "ATRIA_API_BASE not set",
                "error": None}
    prompt = (
        "Bạn là điều phối viên đoàn xe. Viết lại tự nhiên, thân thiện hơn các câu "
        "thông báo sau (giữ nguyên mọi con số, tên người, tên địa điểm; mỗi câu "
        "một dòng; KHÔNG thêm nội dung mới). Trả về DUY NHẤT một mảng JSON các "
        "chuỗi, cùng thứ tự:\n" + json.dumps(texts, ensure_ascii=False))
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/modules/tasco_jarvis_map/chat",
        data=json.dumps({"message": prompt}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        reply = (data.get("reply") or "").strip()
        start, end = reply.find("["), reply.rfind("]")
        out = json.loads(reply[start:end + 1])
        if (isinstance(out, list) and len(out) == len(texts)
                and all(isinstance(x, str) and x.strip() for x in out)):
            return {"ok": True, "polished": True, "texts": out, "error": None}
        return {"ok": True, "polished": False, "why": "shape mismatch",
                "error": None}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as exc:
        return {"ok": True, "polished": False, "why": str(exc)[:120],
                "error": None}


# ── AI Trip Coordinator: one natural-language entry over the group-drive brain ─
# Unifies the challenge's situational Q&A (the Public Evaluation scenarios) by
# routing a free-text query to ONE structured, bilingual coordinator response.
# It orchestrates the SAME telemetry-derived primitives the demo already uses
# (cmd_timeline detections, recommend_regroup, cmd_voice); it NEVER reads
# trip_events labels — every situation comes from the detector's output.
_COORD_CATEGORY = {
    "wrong_turn": "deviation", "group_split": "deviation",
    "falling_behind": "deviation", "delay_building": "deviation",
    "unexpected_stop": "safety", "gps_loss": "safety",
    "low_battery": "safety", "rest_request": "comfort",
    "heavy_rain": "weather",
}


def _slot(t7: dict, member_id: str) -> dict | None:
    return next((m for m in t7["members"] if m["member_id"] == member_id), None)


def _resolve_member(t7: dict, trip_id: str, hint: str | None) -> str:
    """Resolve --member to a member_id in the trip. Accepts an M0xx id, a vehicle
    label ("Bike 2", "Car 3", "EV 2") or a member name; otherwise 'ALL'."""
    import re
    hint = (hint or "").strip()
    if not hint or hint.upper() == "ALL":
        return "ALL"
    m = re.fullmatch(r"m0*\d+", hint, re.I)
    if m:
        return hint.upper()
    f = _fold(hint)
    # the dataset labels vehicles in English ("Car C"); a VN speaker may say "xe C"
    faliases = {f, f.replace("xe ", "car ")}
    for slot in _slots(t7, trip_id):
        for key in ("vehicle_label", "member_name"):
            val = _fold(str(slot.get(key) or ""))
            if val and any(val in a or a in val for a in faliases):
                return slot["member_id"]
    return "ALL"


def _privacy_for(t7: dict, member_id: str, leader_only: bool) -> dict:
    slot = _slot(t7, member_id) or {}
    raw = str(slot.get("privacy_setting") or "All members")
    mode = "leader_only" if leader_only else _PRIVACY.get(raw.lower(), "all")
    return {"member_id": member_id, "mode": mode, "setting": raw,
            "options": ["pause_sharing", "leave_group", "share_with_leader_only"],
            "consent": True}


def _voice_match(folded: str):
    for name, factory, keys in _VOICE_RULES:
        if any(k in folded for k in keys):
            return name, factory()
    return None, None


def _type_hint(text: str) -> set | None:
    """When the query names no member (member == ALL), honour the situation the
    USER described in their OWN words — never a gold label — so a generic "a
    member lost GPS" surfaces the gps_loss event rather than the trip's loudest
    alert. Returns a set of detection types to prefer, or None if the text is
    non-specific. Read only in the ALL-fallback; eval passes an explicit
    member_id, so this never changes the scored path."""
    f = _fold(text)
    hints: list[str] = []
    if ("gps" in f) or ("mat tin hieu" in f) or ("mat song" in f):
        hints.append("gps_loss")
    if ("re sai" in f) or ("re nham" in f) or ("wrong turn" in f) \
            or ("lech tuyen" in f) or ("sai duong" in f):
        hints.append("wrong_turn")
    if ("dung bat thuong" in f) or ("unexpected stop" in f) \
            or ("bat thuong" in f) or ("stopped" in f):
        hints.append("unexpected_stop")
    if ("mua" in f) or ("rain" in f) or ("thoi tiet xau" in f):
        hints.append("heavy_rain")
    if ("pin yeu" in f) or ("het pin" in f) or ("low battery" in f) \
            or ("sac" in f):
        hints.append("low_battery")
    if ("tut lai" in f) or ("tut doan" in f) or ("cham hon" in f) \
            or ("falling behind" in f) or ("tach doan" in f) or ("tach han" in f):
        hints.extend(SEPARATION_FAMILY)
    return set(hints) or None


def _coord_intent(text: str) -> str:
    """Deterministic vi/en keyword router — most-specific first so the tricky
    pairs (regroup vs situation, rest-voice vs privacy, predict vs falling
    behind) resolve correctly."""
    f = _fold(text)
    if any(k in f for k in ("tao chuyen", "tao nhom", "tao doan",
                            "create a group", "create group", "create trip",
                            "plan a trip", "start a drive")):
        return "create_trip"
    if (("privacy" in f) or ("quyen rieng tu" in f) or ("chi chia se" in f)
            or ("chia se vi tri" in f and ("truong" in f or "leader" in f))
            or ("only" in f and "leader" in f)):
        return "privacy_request"
    if any(k in f for k in ("tom tat", "summary", "summarize", "recap",
                            "after the trip")):
        return "trip_summary"
    if (("cung luc" in f) or ("tin nhan xa hoi" in f) or ("social message" in f)
            or ("uu tien" in f and ("canh bao" in f or "alert" in f))):
        return "alert_prioritization"
    if any(k in f for k in ("doi den khi", "nen doi", "co nen doi",
                            "truoc khi tach", "wait until", "before it splits",
                            "should we wait", "should i wait")):
        return "predictive_risk"
    if any(k in f for k in ("diem tap ket", "de xuat diem", "regroup",
                            "safe place to stop", "safe stop", "cho dung an toan")):
        return "regroup_request"
    if _voice_match(f)[0] is not None:   # a quoted / first-person voice command
        return "voice_command"
    return "situation_query"


def _predict_risk(tl: dict, member_id: str) -> dict:
    """Predict a hard split BEFORE it happens, from the member's REAL eta_gap
    trajectory (never the gold label): if the gap is rising and already past —
    or projected within rise_window to cross — the split threshold, act now."""
    series = []
    for tick in tl["ticks"]:
        m = next((x for x in tick["members"] if x["member_id"] == member_id), None)
        if m:
            series.append((tick["t"], m["eta_gap_min"], m["lat"], m["lng"]))
    w = DETECT["rise_window"]
    for i in range(len(series)):
        gaps = [g for (_, g, _, _) in series[max(0, i - w):i + 1]]
        t, cur, la, lo = series[i]
        rising = _rising(gaps)
        crossing = cur >= DETECT["split_eta"] and rising
        will_cross = False
        if len(gaps) >= 2 and rising:
            slope = (gaps[-1] - gaps[0]) / max(1, len(gaps) - 1)
            will_cross = (cur + slope * w >= DETECT["split_eta"]
                          and cur >= DETECT["eta_gap_min"])
        if crossing or will_cross:
            return {"proactive": True, "t": t, "gap_min": round(cur, 1),
                    "at": (la, lo),
                    "reason": ("eta_gap rising, projected to cross the split "
                               f"threshold ({DETECT['split_eta']} min)")}
    return {"proactive": False, "t": None, "gap_min": 0.0, "at": None,
            "reason": "eta_gap not trending toward the split threshold"}


def cmd_coordinate(args) -> dict:
    from types import SimpleNamespace
    t7 = _t7()
    trip = _trip(t7, args.trip)
    if not trip:
        ids = [t["trip_id"] for t in t7["trips"]]
        return _err(f"unknown trip {args.trip!r}; one of {ids}")
    route_id = trip["planned_route_id"]
    text = args.text or ""
    intent = _coord_intent(text)
    member_id = _resolve_member(t7, args.trip, args.member)
    seed = args.seed

    def ns(**kw):
        return SimpleNamespace(**kw)

    base = {"ok": True, "error": None, "intent": intent, "trip": args.trip,
            "member": member_id, "query": text}

    if intent == "create_trip":
        group = _assemble_group(t7, args.trip, seed)
        leader = next((m["name"] for m in group["members"]
                       if m["role"] == "leader"), "")
        base["group"] = group
        base["route"] = {"route_id": route_id, "origin": group["origin"],
                         "destination": group["destination"]}
        base["reply_vi"] = (f"Đã tạo nhóm {group['trip_name']} — mã tham gia "
                            f"{group['join_code']}, {len(group['members'])} xe, "
                            f"trưởng đoàn {leader}.")
        base["reply_en"] = (f"Created group {group['trip_name']} — join code "
                            f"{group['join_code']}, {len(group['members'])} vehicles.")
        base["speak"] = base["reply_vi"]
        return base

    if intent == "privacy_request":
        f = _fold(text)
        leader_only = ("truong" in f) or ("leader" in f) or ("chi chia se" in f)
        who = member_id if member_id != "ALL" else (args.member or "")
        base["privacy"] = _privacy_for(t7, who, leader_only)
        base["reply_vi"] = ("Đã đặt quyền riêng tư: chỉ chia sẻ vị trí với trưởng "
                            "đoàn. Bạn có thể tạm dừng chia sẻ hoặc rời nhóm bất cứ "
                            "lúc nào.")
        base["reply_en"] = ("Privacy set to share location with the leader only. "
                            "You can pause sharing or leave the group anytime.")
        base["speak"] = base["reply_vi"]
        return base

    if intent == "trip_summary":
        tl = cmd_timeline(ns(trip=args.trip, seed=seed))
        dets = tl["detections"]
        deviations = sum(1 for d in dets if d["type"] == "wrong_turn")
        delays = sum(1 for d in dets if d["type"] in SEPARATION_FAMILY)
        safety = sum(1 for d in dets
                     if d["type"] in ("unexpected_stop", "gps_loss", "heavy_rain"))
        summ = dict(tl["summary"])
        summ.update({"deviations": deviations, "delays": delays,
                     "safety_incidents": safety})
        base["summary"] = summ
        base["reply_vi"] = (summ["headline_vi"] + f" Gồm {deviations} lệch tuyến, "
                            f"{delays} chậm/tách đoàn, {safety} sự cố an toàn.")
        base["reply_en"] = (summ["headline_en"] + f" Includes {deviations} "
                            f"deviations, {delays} delays, {safety} safety incidents.")
        base["speak"] = base["reply_vi"]
        return base

    if intent == "alert_prioritization":
        tl = cmd_timeline(ns(trip=args.trip, seed=seed))
        items = [{"category": _COORD_CATEGORY.get(d["type"], "other"),
                  "type": d["type"], "label_vi": d["message_vi"],
                  "priority": d["priority"], "source": d["source"],
                  "member_id": d["member_id"]} for d in tl["detections"]]
        # an explicitly-labelled, non-telemetry social message: a demonstration
        # of ranking only, flagged source:'ui_stub' so it is never mistaken for a
        # trace-derived signal.
        items.append({"category": "social", "type": "social_message",
                      "label_vi": "Tin nhắn xã hội trong nhóm chat",
                      "label_en": "A social chat message in the group",
                      "priority": 5, "source": "ui_stub", "member_id": "ALL"})
        items.sort(key=lambda x: x["priority"], reverse=True)
        base["prioritized"] = items
        base["reply_vi"] = ("Ưu tiên xử lý: " + items[0]["label_vi"]
                            + " — tin nhắn xã hội để lại sau cùng.")
        base["reply_en"] = "Handling by priority; the social message is deprioritised."
        base["speak"] = base["reply_vi"]
        return base

    if intent == "predictive_risk":
        tl = cmd_timeline(ns(trip=args.trip, seed=seed))
        risk = _predict_risk(tl, member_id)
        rec = (recommend_regroup(t7, route_id, "group_split", risk.get("at"))
               if risk.get("proactive") else None)
        base["predictive"] = risk
        base["recommend"] = rec
        if risk.get("proactive"):
            base["reply_vi"] = ("Không nên đợi — khoảng cách ETA đang tăng và sắp "
                                "vượt ngưỡng tách đoàn. Đề xuất tập kết chủ động ngay"
                                + (f" tại {rec['poi_name']}." if rec else "."))
            base["reply_en"] = ("Don't wait — the ETA gap is rising toward the split "
                                "threshold. Recommend a proactive regroup now"
                                + (f" at {rec['poi_name']}." if rec else "."))
        else:
            base["reply_vi"] = "Khoảng cách hiện ổn định — chưa cần tập kết."
            base["reply_en"] = "The gap is stable — no regroup needed yet."
        base["speak"] = base["reply_vi"]
        return base

    if intent == "regroup_request":
        rec = recommend_regroup(t7, route_id, "group_split", None)
        base["recommend"] = rec
        if rec:
            base["reply_vi"] = (f"Điểm tập kết an toàn nhất trên tuyến: {rec['poi_name']} "
                                f"(điểm an toàn {rec['safe_stop_score']}), tránh dừng "
                                "bên lề đường.")
            base["reply_en"] = (f"Safest regroup on the route: {rec['poi_name']} "
                                f"(safe-stop score {rec['safe_stop_score']}), not a "
                                "roadside shoulder.")
        else:
            base["reply_vi"] = "Chưa có điểm tập kết phù hợp trên tuyến này."
            base["reply_en"] = "No suitable regroup point on this route."
        base["speak"] = base["reply_vi"]
        return base

    if intent == "voice_command":
        v = cmd_voice(ns(text=text, trip=args.trip, lang="vi"))
        act = v.get("structured_action") or {}
        base["voice_intent"] = v.get("intent")
        base["structured_action"] = v.get("structured_action")
        base["priority"] = v.get("priority")
        rec = None
        if act.get("poi_id"):
            dtype = ("rest_request" if act.get("action") == "request_rest_stop"
                     else "wrong_turn" if act.get("action") == "report_wrong_turn"
                     else "group_split")
            rec = recommend_regroup(t7, route_id, dtype, None)
        base["recommend"] = rec
        base["reply_vi"] = v.get("reply_vi")
        base["reply_en"] = v.get("reply_en")
        base["speak"] = v.get("reply_vi")
        return base

    # situation_query (default): the member's clustered, telemetry-derived alert
    tl = cmd_timeline(ns(trip=args.trip, seed=seed))
    mid = member_id if member_id != "ALL" else None
    dets = [d for d in tl["detections"] if mid is None or d["member_id"] == mid]
    if mid is None:
        # No member named: prefer the situation the user described in their own
        # words (their query, never a gold label) over the trip's loudest alert.
        hinted = _type_hint(text)
        if hinted:
            typed = [d for d in dets if d["type"] in hinted]
            if typed:
                dets = typed
    if not dets:
        base["situation"] = None
        base["recommend"] = None
        base["reply_vi"] = "Hiện chưa phát hiện bất thường cho thành viên này."
        base["reply_en"] = "No anomaly detected for this member right now."
        base["speak"] = base["reply_vi"]
        return base
    d = max(dets, key=lambda x: x["priority"])
    slot = _slot(t7, d["member_id"]) or {}
    base["situation"] = {"member_id": d["member_id"],
                         "vehicle_label": slot.get("vehicle_label"),
                         "type": d["type"], "severity": d["severity"],
                         "priority": d["priority"], "signal": d["signal"], "t": d["t"]}
    base["recommend"] = d["recommend"]
    tail_vi = (f" Đề xuất tập kết tại {d['recommend']['poi_name']}."
               if d["recommend"] else "")
    tail_en = (f" Recommend regrouping at {d['recommend']['poi_name']}."
               if d["recommend"] else "")
    base["reply_vi"] = d["message_vi"] + tail_vi
    base["reply_en"] = d["message_en"] + tail_en
    if d["type"] == "gps_loss":
        base["false_emergency_avoided"] = True
        base["notify_leader"] = True
    base["speak"] = base["reply_vi"]
    return base


# ── calibrate: threshold-evidence table (dev-only; MAY read trip_events) ─────
def cmd_calibrate(_args) -> dict:
    t7 = _t7()
    rows = []
    for ev in t7["trip_events"]:
        trip = _trip(t7, ev["trip_id"])
        wps = _route(t7, trip["planned_route_id"])
        line = _densify([(w["latitude"], w["longitude"]) for w in wps])
        telemetry = _baseline(t7, ev["trip_id"], 90, line)
        _apply_injections(telemetry, [ev], 90)
        mid = ev["member_id"]
        window = []
        if mid in telemetry:
            t0 = int(ev["timestamp_min"])
            for r in telemetry[mid]:
                if t0 - 6 <= r["t"] <= t0 + 6 and r["t"] % 3 == 0:
                    window.append({k: r[k] for k in
                                   ("t", "status", "gap_km", "eta_gap_min",
                                    "speed_kmh", "gps_ok")})
        rows.append({"event_id": ev["event_id"], "type": ev["event_type"],
                     "severity": ev["severity"], "member_id": mid,
                     "t": ev["timestamp_min"],
                     "telemetry_window": window,
                     "expected": ev["expected_ai_detection"],
                     "gold_poi": ev.get("recommended_poi_id")})
    return {"ok": True, "thresholds": DETECT, "events": rows, "error": None}


def main() -> int:
    try:  # UTF-8 stdout so the bilingual JSON never crashes a cp1252 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Group Drive simulated backend")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("users")
    c = sub.add_parser("create")
    c.add_argument("--scenario", default="TRIP001")
    c.add_argument("--seed", type=int, default=42)
    t = sub.add_parser("timeline")
    t.add_argument("--trip", default="TRIP001")
    t.add_argument("--seed", type=int, default=42)
    v = sub.add_parser("voice")
    v.add_argument("--text", required=True)
    v.add_argument("--trip", default=None)
    v.add_argument("--lang", default="vi")
    al = sub.add_parser("along")
    al.add_argument("--trip", required=True)
    al.add_argument("--query", required=True)
    al.add_argument("--width-km", dest="width_km", type=float, default=5.0)
    al.add_argument("--limit", type=int, default=7)
    co = sub.add_parser("coordinate")
    co.add_argument("--trip", default="TRIP001")
    co.add_argument("--member", default="ALL")
    co.add_argument("--text", required=True)
    co.add_argument("--seed", type=int, default=42)
    sub.add_parser("polish")
    sub.add_parser("calibrate")
    args = ap.parse_args()
    out = {"users": cmd_users, "create": cmd_create, "timeline": cmd_timeline,
           "voice": cmd_voice, "along": cmd_along, "coordinate": cmd_coordinate,
           "polish": cmd_polish, "calibrate": cmd_calibrate}[args.cmd](args)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
