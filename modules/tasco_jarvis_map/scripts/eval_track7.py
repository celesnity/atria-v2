"""Track-7 Group Drive eval — gates the AI coordinator against the dataset gold.

The simulator/detector (group_drive.py) never reads Trip Events at runtime; this
harness replays every trip and compares the rule-based detections, regroup
recommendations, voice parsing and alert priorities against the gold sheets.

Type matching honesty boundary: the dataset's three "separation" labels
(Falling Behind / Group Split / Delay Building) describe the same physical
signal — a member's spatial/temporal gap growing — named by narrative context.
Detections match those three as a FAMILY; every other type must match exactly.
Exact-type agreement is also reported (informative, not gated).

Gates (exit 1 if any fails):
  1. detection_recall   == 100% of trace-derivable gold events (external ones
                           — weather — must be surfaced too, reported apart)
  2. detection_precision >= 0.80 (false-alarm cap across all 5 trips)
  3. regroup_top1       == 100% (gold recommended_poi_id, where present)
  4. voice_intent       == 8/8; structured-action field match >= 7/8
  5. priority_ordering  == 100% pairwise (gold High > Medium > Low)
  6. determinism        — same seed twice -> identical canonical JSON SHA1

Run with PYTHONUTF8=1. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import load_json  # noqa: E402
import group_drive as gd  # noqa: E402

FAMILY = set(gd.SEPARATION_FAMILY)
GOLD_TYPE = {
    "Wrong Turn": "wrong_turn", "Falling Behind": "falling_behind",
    "Heavy Rain Ahead": "heavy_rain", "GPS Weak Signal": "gps_loss",
    "Unexpected Stop": "unexpected_stop", "Delay Building": "delay_building",
    "Rest Request": "rest_request", "Low Battery": "low_battery",
    "Group Split": "group_split",
}
T_TOL = 15  # minutes; one trace sampling step
SEED = 42


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _timeline(trip: str, seed: int = SEED) -> dict:
    return gd.cmd_timeline(_Args(trip=trip, seed=seed))


def _match(det: dict, ev: dict) -> bool:
    gt = GOLD_TYPE[ev["event_type"]]
    member_ok = det["member_id"] == ev["member_id"] or ev["member_id"] == "ALL"
    time_ok = abs(det["t"] - ev["timestamp_min"]) <= T_TOL
    type_ok = det["type"] == gt or (det["type"] in FAMILY and gt in FAMILY)
    return member_ok and time_ok and type_ok


def main() -> int:
    t7 = load_json("track7.json")
    gold = t7["trip_events"]
    trips = [t["trip_id"] for t in t7["trips"]]

    results: dict[str, dict] = {}
    matched_pairs: list[tuple[dict, dict]] = []
    n_pred_trace = n_matched = n_exact = 0
    external_surfaced = external_gold = 0
    misses: list[str] = []
    extras: list[str] = []

    for trip in trips:
        tl = _timeline(trip)
        dets = tl["detections"]
        g = [e for e in gold if e["trip_id"] == trip]
        used: set[int] = set()
        for ev in g:
            hit = next((i for i, d in enumerate(dets)
                        if i not in used and _match(d, ev)), None)
            is_ext = bool(ev["injection"].get("external"))
            external_gold += is_ext
            if hit is None:
                misses.append(f"{ev['event_id']} {ev['event_type']}")
                continue
            used.add(hit)
            det = dets[hit]
            if is_ext:
                external_surfaced += 1
            else:
                n_matched += 1
            n_exact += det["type"] == GOLD_TYPE[ev["event_type"]]
            matched_pairs.append((det, ev))
        for i, d in enumerate(dets):
            if d["source"] == "trace":
                n_pred_trace += 1
                if i not in used:
                    extras.append(f"{trip} {d['type']}@{d['t']} {d['member_id']}")

    gold_trace = sum(1 for e in gold if not e["injection"].get("external"))
    recall = n_matched / gold_trace
    precision = (n_matched / n_pred_trace) if n_pred_trace else 0.0
    results["detection"] = {
        "recall": round(recall, 3), "precision": round(precision, 3),
        "matched": n_matched, "gold_trace": gold_trace,
        "false_alarms": len(extras), "misses": misses, "extras": extras,
        "exact_type_agreement": f"{n_exact}/{len(matched_pairs)}",
        "external_surfaced": f"{external_surfaced}/{external_gold}",
    }

    # 3. regroup top-1
    poi_hits = poi_total = 0
    poi_misses = []
    for det, ev in matched_pairs:
        want = ev.get("recommended_poi_id")
        if not want:
            continue
        poi_total += 1
        got = (det.get("recommend") or {}).get("poi_id")
        if got == want:
            poi_hits += 1
        else:
            poi_misses.append(f"{ev['event_id']}: got {got} want {want}")
    results["regroup"] = {"top1": f"{poi_hits}/{poi_total}", "misses": poi_misses}

    # 4. voice
    v_intent = v_action = 0
    v_misses = []
    for vc in t7["voice_commands"]:
        for text in (vc["input_text_vi"], vc["input_text_en"]):
            out = gd.cmd_voice(_Args(text=text, trip="TRIP001", lang="vi"))
            i_ok = out["intent"] == vc["expected_intent"]
            want = vc["expected_structured_action"]
            act = out["structured_action"] or {}
            a_ok = all(act.get(k) == v for k, v in want.items())
            v_intent += i_ok
            v_action += a_ok
            if not (i_ok and a_ok):
                v_misses.append(f"{vc['command_id']} ({text[:30]}...)")
    results["voice"] = {"intent": f"{v_intent}/16", "action": f"{v_action}/16",
                        "misses": v_misses}

    # 5. priority ordering vs gold severity (pairwise over matched detections)
    sev_rank = {"High": 3, "Medium": 2, "Low": 1}
    ord_ok = ord_total = 0
    for i in range(len(matched_pairs)):
        for j in range(i + 1, len(matched_pairs)):
            (da, ea), (db, eb) = matched_pairs[i], matched_pairs[j]
            ra, rb = sev_rank[ea["severity"]], sev_rank[eb["severity"]]
            if ra == rb:
                continue
            ord_total += 1
            ord_ok += (da["priority"] > db["priority"]) == (ra > rb)
    results["priority"] = {"pairwise": f"{ord_ok}/{ord_total}"}

    # 6. determinism
    a = json.dumps(_timeline("TRIP001"), sort_keys=True, ensure_ascii=False)
    b = json.dumps(_timeline("TRIP001"), sort_keys=True, ensure_ascii=False)
    sha_a = hashlib.sha1(a.encode("utf-8")).hexdigest()
    results["determinism"] = {"sha1": sha_a[:12],
                              "identical": sha_a == hashlib.sha1(
                                  b.encode("utf-8")).hexdigest()}

    gates = {
        "detection_recall==1.0": recall == 1.0,
        "detection_precision>=0.8": precision >= 0.8,
        "external_surfaced": external_surfaced == external_gold,
        "regroup_top1==100%": poi_hits == poi_total,
        "voice_intent==16/16": v_intent == 16,
        "voice_action>=14/16": v_action >= 14,
        "priority_pairwise==100%": ord_ok == ord_total,
        "determinism": results["determinism"]["identical"],
    }

    print(json.dumps(results, indent=2, ensure_ascii=False))
    print()
    ok = True
    for name, passed in gates.items():
        print(f"GATE ({name}): {'PASS' if passed else 'FAIL'}")
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
