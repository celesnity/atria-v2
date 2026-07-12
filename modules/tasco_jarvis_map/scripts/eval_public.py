"""Public-Evaluation harness (Track-7) — the 15 challenge scenarios.

The xlsx "Public Evaluation" sheet (imported as track7.json `eval_scenarios`) is
the challenge's own scenario set: 15 natural-language user queries, each with a
trip_id + member_id + expected_focus + task_type. This harness feeds every query
through the AI Trip Coordinator (`group_drive.cmd_coordinate`) and asserts a
deterministic, structured-field check per row — no LLM, no network, fully
offline and reproducible (single seed -> byte-identical JSON).

Gate: passed == 15/15 AND the coordinator is deterministic. Exit 1 otherwise.

Run:  PYTHONUTF8=1 ../../.venv/Scripts/python.exe scripts/eval_public.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import group_drive as gd  # noqa: E402
from _data import load_json  # noqa: E402

SEED = 42
SEPARATION = gd.SEPARATION_FAMILY


def _run(trip: str, member: str, text: str) -> dict:
    return gd.cmd_coordinate(SimpleNamespace(trip=trip, member=member, text=text,
                                             seed=SEED))


def _rec_id(r: dict):
    return (r.get("recommend") or {}).get("poi_id")


def _rec_safe(r: dict) -> float:
    return float((r.get("recommend") or {}).get("safe_stop_score") or 0)


# ── per-row checks, keyed by the scenario's `category` (unique per row) ───────
def _create(r):
    g = r.get("group") or {}
    return (r["intent"] == "create_trip" and bool(g.get("join_code"))
            and len(g.get("members") or []) >= 1 and bool(r.get("route")))


def _route_deviation(r):
    s = r.get("situation") or {}
    return s.get("type") == "wrong_turn" and _rec_id(r) == "POI001"


def _falling_behind(r):
    s = r.get("situation") or {}
    return (s.get("type") in SEPARATION and _rec_id(r) == "POI001"
            and s.get("priority") is not None)


def _regroup(r):
    return _rec_id(r) == "POI001" and _rec_safe(r) >= 0.7


def _voice(r):
    return (r.get("structured_action") or {}).get("action") == "report_wrong_turn"


def _unexpected_stop(r):
    s = r.get("situation") or {}
    return s.get("type") == "unexpected_stop" and s.get("severity") == "high"


def _gps_weak(r):
    s = r.get("situation") or {}
    return (s.get("type") == "gps_loss" and r.get("false_emergency_avoided") is True
            and r.get("intent") != "emergency")


def _corporate(r):
    s = r.get("situation") or {}
    return s.get("type") in SEPARATION and _rec_id(r) == "POI006"


def _rest(r):
    return ((r.get("structured_action") or {}).get("action") == "request_rest_stop"
            and _rec_id(r) == "POI007")


def _unsafe_stop(r):
    return _rec_id(r) == "POI007" and _rec_safe(r) >= 0.7


def _ev_charging(r):
    return _rec_id(r) == "POI009"


def _privacy(r):
    p = r.get("privacy") or {}
    return (p.get("mode") == "leader_only"
            and {"pause_sharing", "leave_group"} <= set(p.get("options") or []))


def _summary(r):
    s = r.get("summary") or {}
    return ("events_total" in s and "regroups" in s
            and "safety_incidents" in s and bool(s.get("per_member")))


def _prioritization(r):
    p = r.get("prioritized") or []
    return (len(p) >= 2 and p[0]["category"] in {"weather", "safety", "deviation"}
            and p[-1]["category"] == "social")


def _predictive(r):
    return (r.get("predictive") or {}).get("proactive") is True and _rec_id(r)


CHECKS = {
    "Create Group Trip": _create,
    "Route Deviation": _route_deviation,
    "Falling Behind": _falling_behind,
    "Regroup Recommendation": _regroup,
    "Voice Command": _voice,
    "Unexpected Stop": _unexpected_stop,
    "GPS Weak Signal": _gps_weak,
    "Corporate Convoy": _corporate,
    "Rest Request": _rest,
    "Unsafe Stop": _unsafe_stop,
    "EV Charging": _ev_charging,
    "Privacy": _privacy,
    "Trip Summary": _summary,
    "Alert Prioritization": _prioritization,
    "Predictive Risk": _predictive,
}


def main() -> int:
    scenarios = load_json("track7.json")["eval_scenarios"]
    rows, passed = [], 0
    for sc in scenarios:
        cat = sc["category"]
        check = CHECKS.get(cat)
        resp = _run(sc["trip_id"], sc["member_id"], sc["user_query_or_scenario"])
        ok = bool(check and check(resp))
        passed += ok
        rows.append({
            "category": cat, "trip": sc["trip_id"], "member": sc["member_id"],
            "task_type": sc["task_type"], "intent": resp.get("intent"),
            "recommend": _rec_id(resp), "pass": ok,
            "reason": None if ok else f"check failed (intent={resp.get('intent')})",
        })

    # determinism: same seed -> identical canonical JSON for every scenario
    det = True
    for sc in scenarios:
        a = _run(sc["trip_id"], sc["member_id"], sc["user_query_or_scenario"])
        b = _run(sc["trip_id"], sc["member_id"], sc["user_query_or_scenario"])
        if json.dumps(a, sort_keys=True, ensure_ascii=False) != \
                json.dumps(b, sort_keys=True, ensure_ascii=False):
            det = False
            break

    report = {"total": len(scenarios), "passed": passed, "determinism": det,
              "rows": rows}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    all_ok = passed == len(scenarios) and det
    print(f"\nGATE (public_eval {passed}/{len(scenarios)}):",
          "PASS" if passed == len(scenarios) else "FAIL")
    print("GATE (determinism):", "PASS" if det else "FAIL")
    print("\nRESULT:", "PASS" if all_ok else "REVIEW")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
