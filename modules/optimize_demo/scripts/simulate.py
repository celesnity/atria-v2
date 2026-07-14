#!/usr/bin/env python3
"""simulate.py -- Simulation-mode data source for the Optimize dashboard.

Reads the IIOT **fleet HTTP API** (a read-only JSON server, purpose-built for this
dashboard, that exposes 20 live machines) and returns:

  * ``machines`` -- each fleet machine mapped into the dashboard's own machine shape
    (``state/avail/perf/qual/oee/health/target/thru/temp/vib/runtime/since/defect/
    downMin/atRisk`` ...), so the dashboard renders live data through the *same*
    view code it uses for the static demo; and
  * ``scn`` -- a **recommendation derived from the live fleet** (the fleet API returns
    raw status only), in the exact object shape the Recommendation view consumes.

Transport: server-side ``urllib`` GET (no browser CORS/CSP concerns, stdlib only, no
third-party dependency). Contract (AtriaDash bridge):

    python scripts/simulate.py status   # JSON payload optional on stdin: {"url": "..."}
    -> {ok, connected, source, plant, simulation_minute, machines:[...], summary:{...},
        scn:{...}, ts}

Never raises on a dead simulator: a connection error/timeout yields
``{ok:true, connected:false, error:"..."}`` (exit 0) so the UI can show a clean
"simulator not connected" state. Fleet URL: ``IIOT_FLEET_URL`` env or the stdin
``url`` (default ``http://127.0.0.1:5050``).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = os.environ.get("IIOT_FLEET_URL") or "http://127.0.0.1:5050"
TIMEOUT = float(os.environ.get("IIOT_FLEET_TIMEOUT", "3"))

# Rolling telemetry history (gitignored data/). The fleet API is a live-evolving simulator but
# each snapshot is a single point; we buffer recent snapshots here so the live time-series charts
# (throughput line, vibration/temp dual-line, SPC) show real motion, and so the Ask-AI charts and
# the AI backend can reason over a trend rather than one frame. Compact + bounded; best-effort
# (a history read/write failure never breaks the status call).
HISTORY_MAX = 180  # samples retained on disk
HISTORY_WINDOW = 24  # samples returned to the UI
# Per-machine metrics captured per sample, in this order (kept short to bound file/response size).
_HIST_KEYS = ("oee", "thru", "temp", "vib", "health", "defect", "avail", "perf", "qual")


def _data_dir() -> Path:
    override = os.environ.get("OPTIMIZE_DATA_DIR")
    if override:
        return Path(override)
    root = os.environ.get("ATRIA_MODULE_ROOT")
    base = Path(root) if root else Path(__file__).resolve().parents[1]
    return base / "data"


def _history_path() -> Path:
    return _data_dir() / "history.jsonl"


def _append_history(minute, machines: list) -> None:
    """Append one compact sample; trim the file to the last HISTORY_MAX lines. Best-effort."""
    try:
        path = _history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        sample = {
            "m": minute,
            "d": {
                mm["id"]: [round(float(mm.get(k, 0) or 0), 4) for k in _HIST_KEYS]
                for mm in machines
            },
        }
        lines = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(sample, separators=(",", ":")))
        if len(lines) > HISTORY_MAX:
            lines = lines[-HISTORY_MAX:]
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)
    except (OSError, ValueError, TypeError):
        pass


def _load_history(window: int = HISTORY_WINDOW) -> list:
    try:
        path = _history_path()
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-window:]
        return [json.loads(ln) for ln in lines if ln.strip()]
    except (OSError, ValueError):
        return []


def build_history(machines: list, minute) -> dict:
    """Append the current frame and return {trends, series} over the recent window.

    - ``trends`` — fleet-level real series (oee %, throughput/hr, first-pass-yield %) per sample.
    - ``series`` — per-machine arrays keyed by metric, for the Ask-AI / analysis charts.
    """
    _append_history(minute, machines)
    samples = _load_history()
    if not samples:
        return {"trends": None, "series": {}, "samples": 0}
    idx = {k: i for i, k in enumerate(_HIST_KEYS)}
    oee_series, thru_series, fpy_series = [], [], []
    for s in samples:
        rows = list(s.get("d", {}).values())
        if not rows:
            continue
        oee_series.append(round(sum(r[idx["oee"]] for r in rows) / len(rows) * 100, 1))
        thru_series.append(round(sum(r[idx["thru"]] for r in rows)))
        fpy_series.append(round(100 - sum(r[idx["defect"]] for r in rows) / len(rows), 1))
    series: dict = {}
    for mm in machines:
        mid = mm["id"]
        arrs: dict = {k: [] for k in _HIST_KEYS}
        for s in samples:
            row = s.get("d", {}).get(mid)
            if row:
                for k in _HIST_KEYS:
                    arrs[k].append(row[idx[k]])
        series[mid] = arrs
    return {
        "trends": {"oee": oee_series, "thru": thru_series, "fpy": fpy_series},
        "series": series,
        "samples": len(samples),
    }


HEALTH_LIMIT = 0.70  # machine-health operating limit for a speed increase
# Modeled shift clock (deterministic; the fleet baseline carries no cumulative history).
SHIFT_HOURS = 8.0
ELAPSED_HOURS = 4.75
CLOCK_LABEL = "11:04"
VERSIONS = {
    "forecast_model": "production-forecast-0.1",
    "impact_model": "material-recovery-0.1",
    "ruleset": "operational-constraints-0.1",
    "optimizer": "weighted-ranking-0.1",
}


# ── HTTP ────────────────────────────────────────────────────────────────────
def _get(base: str, path: str):
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── mapping: fleet machine schema -> dashboard machine shape ────────────────
def map_machine(fm: dict) -> dict:
    idx = int(fm.get("index", 0))
    return {
        "id": fm.get("id"),
        "num": idx + 1,
        "n": idx + 1,
        "cell": fm.get("cell"),
        "type": fm.get("type"),
        "state": fm.get("status"),
        "avail": fm.get("availability", 0.0),
        "perf": fm.get("performance", 0.0),
        "qual": fm.get("quality", 0.0),
        "oee": fm.get("oee", 0.0),
        "health": fm.get("health", 0.0),
        "target": int(fm.get("target_per_hour", 0)),
        "thru": int(fm.get("throughput_per_hour", 0)),
        "temp": fm.get("temperature_c", 0.0),
        "vib": fm.get("vibration_mms", 0.0),
        "runtime": int(fm.get("runtime_hours", 0)),
        "since": int(fm.get("hours_since_service", 0)),
        "defect": fm.get("defect_rate", 0.0),
        "downMin": int(fm.get("downtime_minutes", 0)),
        "atRisk": bool(fm.get("at_risk")),
        "reason": fm.get("status_reason"),
        # Pass the simulator's immutable baseline + live-vs-baseline diff + warning codes straight
        # through so the Machines tab can show a live per-machine detail vs baseline (absent -> None).
        "baseline": fm.get("baseline"),
        "diff": fm.get("diff"),
        "warnings": fm.get("warning_codes") or [],
    }


# ── recommendation engine (derived from live telemetry) ─────────────────────
def _clamp01(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 2)


# A machine is "starved" when it is idle for lack of upstream product. The factory sim marks this
# ``material_starvation``; the laundry sim marks idle washers ``awaiting_product`` (empty intake
# queue). Both are recoverable by feeding product, so the recommendation treats them the same.
_STARVED_REASONS = ("material_starvation", "awaiting_product")


def _L(lang: str, en: str, vi: str) -> str:
    """Pick the English or Vietnamese variant. Prose is authored bilingually at the source so the
    dashboard renders the recommendation in the active language without a client-side dictionary."""
    return vi if lang == "vi" else en


def _is_starved(m: dict, intake: dict | None) -> bool:
    if m.get("reason") in _STARVED_REASONS:
        return True
    # Laundry: an idle washer while the intake queue is empty is starved for product.
    if m.get("state") == "idle" and intake is not None and int((intake or {}).get("queue_len", 1) or 0) == 0:
        return True
    return False


def intake_stats(intake: dict | None, machines: list) -> dict:
    """Real product-intake signal from the live fleet snapshot's ``intake`` block (laundry domain)."""
    intake = intake or {}
    supply = intake.get("supply") or {}
    supply_total = sum(int(v or 0) for v in supply.values())
    top_product = max(supply, key=lambda k: supply[k]) if supply else None
    starved = [m for m in machines if _is_starved(m, intake)]
    return {
        "present": bool(intake),
        "queue_len": int(intake.get("queue_len", 0) or 0),
        "in_progress": int(intake.get("in_progress", 0) or 0),
        "completed": int(intake.get("completed", 0) or 0),
        "supply": supply,
        "supply_total": supply_total,
        "top_product": top_product,
        "starved_count": len(starved),
    }


def pick_target(machines: list, intake: dict | None = None) -> dict:
    """The line most worth a recovery recommendation.

    Priority: a product-starved line (recoverable by feeding product) -> an at-risk running line ->
    the worst-OEE running line -> the worst-OEE line.
    """
    starved = [m for m in machines if _is_starved(m, intake)]
    if starved:
        return sorted(starved, key=lambda m: -m["target"])[0]
    at_risk = [m for m in machines if m.get("atRisk")]
    if at_risk:
        return sorted(at_risk, key=lambda m: m["oee"])[0]
    running = [m for m in machines if m.get("state") == "running"]
    pool = running or machines
    return sorted(pool, key=lambda m: m["oee"])[0]


_RISK_W = {"low": 0.12, "medium": 0.4, "high": 0.82}


def build_scn(machines: list, intake: dict | None = None, lang: str = "en") -> dict:
    stx = intake_stats(intake, machines)
    is_laundry = stx["present"]
    m = pick_target(machines, intake)
    remaining = SHIFT_HOURS - ELAPSED_HOURS
    rate_t = m["target"]
    rate_now = m["thru"]
    healthy_rate = rate_t * 0.92
    down_h = m["downMin"] / 60.0
    starved = _is_starved(m, intake)

    # Modeled shift projection (baseline carries no cumulative output).
    if rate_now > 0:
        current = round(rate_now * ELAPSED_HOURS)
    else:  # stopped/starved now -> produced at a healthy rate before the stoppage
        current = max(0, round(healthy_rate * max(0.0, ELAPSED_HOURS - down_h)))
    forecast_base = round(current + rate_now * remaining)  # no action: continue as-is
    target = round(rate_t * SHIFT_HOURS)
    gap = forecast_base - target
    shortfall = max(1, -gap)
    attain_before = _clamp01(forecast_base / target if target else 0.0)
    health_ok = m["health"] >= HEALTH_LIMIT
    line = m["id"]

    # Loss breakdown. Starvation dominates when the fleet is product-starved (empty intake queue).
    starve_frac = 0.55 if (starved or stx["starved_count"] > 0) else 0.42
    rest = 1.0 - starve_frac

    def loss(kind, short, frac):
        units = round(shortfall * frac)
        return {"type": kind, "short": short, "min": round(units / max(rate_t, 1) * 60), "units": units}

    starve_type = _L(lang, "Product starvation" if is_laundry else "Material starvation",
                     "Thiếu sản phẩm" if is_laundry else "Thiếu vật tư")
    losses = [
        loss(starve_type, _L(lang, "Product" if is_laundry else "Material",
                             "Sản phẩm" if is_laundry else "Vật tư"), starve_frac),
        loss(_L(lang, "Micro-stops", "Dừng vặt"), _L(lang, "Micro-stop", "Dừng vặt"), rest * 0.5),
        loss(_L(lang, "Reduced speed", "Giảm tốc độ"), _L(lang, "Reduced", "Giảm tốc"), rest * 0.32),
        loss(_L(lang, "Quality hold", "Giữ chất lượng"), _L(lang, "Quality", "Chất lượng"), rest * 0.18),
    ]

    # Grounded recovery for the feed action: the starved machines' recoverable output if fed now
    # (real starved targets over the remaining shift), NOT a blind fraction of a synthetic shortfall.
    starved_targets = sum(x["target"] for x in machines if _is_starved(x, intake))
    if starved_targets:
        feed_recovery = max(1, min(shortfall, round(starved_targets * remaining * 0.30)))
    else:
        feed_recovery = round(shortfall * 0.44)
    release_count = max(1, stx["starved_count"])

    def mk(aid, kind, typ, pre, em, post, detail, recovered, cost, risk, approval, feasible, conf,
           why, rejection=None):
        rec = recovered if feasible else 0
        fa = forecast_base + rec
        return {
            "id": aid, "kind": kind, "headPre": pre, "headEm": em, "headPost": post,
            "type": typ, "detail": detail, "recovered": rec, "cost": cost, "risk": risk,
            "feasible": feasible, "approval": approval,
            "attainAfter": _clamp01(fa / target if target else 0.0), "confidence": conf,
            "forecastAfter": fa, "why": why, "rejection": rejection,
        }

    speed_rej = _L(
        lang,
        "Machine health {:.2f} is below the {:.2f} operating limit -- prohibited by the "
        "asset-health constraint.".format(m["health"], HEALTH_LIMIT),
        "Tình trạng máy {:.2f} thấp hơn ngưỡng vận hành {:.2f} -- bị cấm bởi ràng buộc sức khỏe "
        "thiết bị.".format(m["health"], HEALTH_LIMIT),
    )

    # The primary recovery action reads the real intake signal for laundry (release product into the
    # intake queue), grounded in the live queue/supply/starved-count; falls back to material delivery.
    if is_laundry:
        feed = mk(
            "A_material", "release",
            _L(lang, "Release product to intake", "Thả sản phẩm vào intake"),
            _L(lang, "Release product for", "Thả sản phẩm cho"), line, "",
            _L(lang, "Release {} product batch(es) into the intake queue -- urgent".format(release_count),
               "Thả {} mẻ sản phẩm vào hàng đợi intake -- khẩn".format(release_count)),
            feed_recovery, _L(lang, "Low", "Thấp"), "low", None, True, 0.84,
            _L(lang,
               "The intake queue is empty and {} washer(s) sit idle awaiting product; releasing product "
               "restores feed and recovers the biggest block of lost output (supply on hand: {} batches).".format(
                   stx["starved_count"], stx["supply_total"]),
               "Hàng đợi intake trống và {} máy giặt đang nhàn rỗi chờ sản phẩm; thả sản phẩm khôi phục "
               "nguồn cấp và thu hồi phần sản lượng mất lớn nhất (tồn kho: {} mẻ).".format(
                   stx["starved_count"], stx["supply_total"])),
        )
    else:
        feed = mk(
            "A_material", "release",
            _L(lang, "Prioritize material delivery", "Ưu tiên giao vật tư"),
            _L(lang, "Prioritize material for", "Ưu tiên vật tư cho"), line, "",
            _L(lang, "Dispatch the next pallet to " + line + " -- urgent",
               "Điều pallet kế tiếp tới " + line + " -- khẩn"),
            feed_recovery, _L(lang, "Low", "Thấp"), "low", None, True, 0.84,
            _L(lang,
               "Material starvation is the binding constraint on " + line + "; expediting the pallet "
               "restores feed and recovers the biggest block of lost output.",
               "Thiếu vật tư là ràng buộc chính trên " + line + "; đẩy nhanh pallet khôi phục nguồn cấp "
               "và thu hồi phần sản lượng mất lớn nhất."),
        )

    catalog = [
        feed,
        mk("A_reseq", "reseq",
           _L(lang, "Change job sequence", "Đổi thứ tự công việc"),
           _L(lang, "Resequence", "Sắp lại"), _L(lang, "jobs", "công việc"),
           _L(lang, "on " + line, "trên " + line),
           _L(lang, "Run the line-side job first", "Chạy công việc tại chỗ trước"),
           round(shortfall * 0.34), _L(lang, "Low", "Thấp"), "medium",
           _L(lang, "Planner", "Điều độ"), True, 0.72,
           _L(lang, "A line-side job can run now while the constraint clears, avoiding idle wait.",
              "Một công việc tại chỗ có thể chạy ngay trong khi ràng buộc được giải tỏa, tránh chờ nhàn rỗi.")),
        mk("A_operator", "operator",
           _L(lang, "Reassign operator", "Điều chuyển nhân sự"),
           _L(lang, "Move an operator", "Điều một nhân sự"), _L(lang, "to", "tới"), line,
           _L(lang, "Authorized - temporary", "Được duyệt - tạm thời"),
           round(shortfall * 0.26), _L(lang, "Medium", "Trung bình"), "medium",
           _L(lang, "Supervisor", "Giám sát"), True, 0.70,
           _L(lang, "A neighbouring line has temporary spare, certified labour for this cell.",
              "Chuyền lân cận có nhân sự dự phòng tạm thời, đủ chứng chỉ cho cụm này.")),
        mk("A_speed", "speed",
           _L(lang, "Increase machine speed", "Tăng tốc độ máy"),
           _L(lang, "Increase", "Tăng"), _L(lang, "line speed", "tốc độ chuyền"),
           _L(lang, "on " + line, "trên " + line),
           _L(lang, "+8% throughput", "+8% sản lượng"),
           round(shortfall * 0.5), _L(lang, "Low", "Thấp"), "high",
           (None if health_ok else _L(lang, "Not allowed", "Không cho phép")), health_ok, 0.66,
           _L(lang, "Raising the rate closes the gap fastest while the machine is healthy.",
              "Tăng nhịp giúp khép khoảng thiếu nhanh nhất khi máy còn khỏe."),
           None if health_ok else speed_rej),
    ]
    # Situation-fit: the feed action leads when starved/down, else resequence leads.
    if not (starved or m["state"] == "down"):
        catalog[0], catalog[1] = catalog[1], catalog[0]

    def score(a):
        if not a["feasible"]:
            return 0.0
        return round(
            0.5 * (a["recovered"] / shortfall)
            + 0.3 * a["confidence"]
            + 0.2 * (1 - _RISK_W.get(a["risk"], 0.5)),
            3,
        )

    ranked = sorted(catalog, key=lambda a: (a["feasible"], score(a)), reverse=True)
    no_action = mk(
        "ACT-000", "no_action",
        _L(lang, "No action", "Không hành động"),
        _L(lang, "Continue", "Tiếp tục"), _L(lang, "no action", "không hành động"), "",
        _L(lang, "Continue as-is", "Giữ nguyên"), 0, _L(lang, "None", "Không"), "high", None, True, 0.9,
        _L(lang, "Baseline -- output drifts to the current forecast with no intervention.",
           "Cơ sở -- sản lượng trôi theo dự báo hiện tại nếu không can thiệp."),
    )
    ordered = ranked + [no_action]
    # Stable public ids: ACT-001 = recommended (dashboard default-selects ACT-001).
    for i, a in enumerate(ordered):
        a["score"] = score(a)
        if a["id"] != "ACT-000":
            a["id"] = "ACT-%03d" % (i + 1)

    supply_label = _L(lang, "Product supply" if is_laundry else "Material status",
                      "Nguồn sản phẩm" if is_laundry else "Trạng thái vật tư")
    queue_label = _L(lang, "Intake queue" if is_laundry else "Forklift availability",
                     "Hàng đợi intake" if is_laundry else "Xe nâng sẵn sàng")
    return {
        "recId": "REC-LIVE-" + str(line),
        "line": line,
        "wo": "WO-" + str(4500 + m["num"]),
        "shift": "SHIFT-A",
        "clockLabel": CLOCK_LABEL,
        "target": target,
        "current": current,
        "forecastBase": forecast_base,
        "gap": gap,
        "attainBefore": attain_before,
        "minutesRemaining": round(remaining * 60),
        "cycleExpected": 12,
        "cycleActual": round(12 / max(m["perf"], 0.5), 1),
        "machineHealth": m["health"],
        "losses": losses,
        "alternatives": ordered,
        "intake": stx,
        "constraints": [
            {"c": supply_label, "r": "passed"},
            {"c": queue_label, "r": "passed"},
            {"c": _L(lang, "Operator authorization", "Ủy quyền vận hành"), "r": "passed"},
            {"c": _L(lang, "Safety route open", "Tuyến an toàn mở"), "r": "passed"},
            {"c": _L(lang, "Machine health limit", "Giới hạn sức khỏe máy"),
             "r": "passed" if health_ok else "failed"},
        ],
        "evidence": [
            "EV-" + str(m["runtime"] % 10000),
            "EV-" + str((m["runtime"] + 7) % 10000),
            "EV-" + str(m["downMin"] + 8100),
        ],
        "versions": VERSIONS,
        "targetMachine": line,
    }


# ── command ─────────────────────────────────────────────────────────────────
def handle_status(payload: dict) -> dict:
    base = (payload or {}).get("url") or DEFAULT_URL
    ts = datetime.now(timezone.utc).isoformat()
    try:
        snap = _get(base, "/api/fleet/snapshot")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return {
            "ok": True,
            "connected": False,
            "source": base,
            "error": "{}: {}".format(type(exc).__name__, exc),
            "ts": ts,
        }
    try:
        summary = _get(base, "/api/fleet/summary")
    except Exception:  # summary is optional; snapshot already succeeded
        summary = None
    machines = [map_machine(fm) for fm in snap.get("machines", [])]
    intake = snap.get("intake")  # laundry domain: fleet-level product-intake queue/supply
    lang = (payload or {}).get("lang") or "en"
    scn = build_scn(machines, intake, lang) if machines else None
    minute = snap.get("simulation_minute", 0)
    hist = build_history(machines, minute) if machines else {"trends": None, "series": {}}
    return {
        "ok": True,
        "connected": True,
        "source": base,
        "plant": snap.get("plant"),
        "simulation_minute": minute,
        "machines": machines,
        "summary": summary,
        "scn": scn,
        "intake": intake,
        "trends": hist.get("trends"),
        "history": hist.get("series"),
        "ts": ts,
    }


def _post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# How an approved recovery action actuates the live simulator. The fleet console recommends
# production actions; on the demo simulator we express "recover this machine" as a real control
# call so the approved decision visibly changes the live telemetry (the machine recovers on the
# next poll). Map: default = service the target machine (which also un-trips a fault-stopped one).
def _actuation_for(action: str, machine: str) -> tuple[str, dict]:
    action = (action or "service").lower()
    if action in ("resolve", "resolve_fault", "clear"):
        return "/api/fleet/machines/{}/resolve-fault".format(machine), {}
    if action in ("speed", "increase_speed"):
        return "/api/fleet/control/speed", {"minutes_per_sec": 2.0}
    # default: full service -> restores condition and returns a tripped machine to running.
    return "/api/fleet/machines/{}/maintenance".format(machine), {"action": "full_service"}


def handle_actuate(payload: dict) -> dict:
    """Push an approved recommendation to the live simulator (the "approve to the machine" loop)."""
    base = (payload or {}).get("url") or DEFAULT_URL
    machine = str((payload or {}).get("machine") or "").strip().upper()
    action = ((payload or {}).get("action") or "service").lower()
    ts = datetime.now(timezone.utc).isoformat()

    # Laundry: an approved "release product" recovery actuates the REAL intake queue -- it releases
    # product batches into intake so the starved washers resume on the next poll. Product/count come
    # from the payload or default to the top-supply product.
    if action in ("release", "product", "material", "intake"):
        try:
            intk = _get(base, "/api/fleet/intake")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            intk = {}
        supply = (intk or {}).get("supply") or {}
        product = (payload or {}).get("product") or (
            max(supply, key=lambda k: supply[k]) if supply else "towels"
        )
        count = int((payload or {}).get("count") or 1)
        try:
            resp = _post(base, "/api/fleet/intake/release", {"product": product, "count": count})
            return {
                "ok": True, "connected": True, "actuated": True, "machine": machine or "-",
                "action": "release", "endpoint": "/api/fleet/intake/release",
                "product": product, "count": count, "response": resp, "ts": ts,
            }
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return {
                "ok": True, "connected": False, "actuated": False, "machine": machine or "-",
                "action": "release", "endpoint": "/api/fleet/intake/release",
                "error": "{}: {}".format(type(exc).__name__, exc), "ts": ts,
            }

    if not machine:
        return {"ok": True, "actuated": False, "error": "no machine id", "ts": ts}
    endpoint, body = _actuation_for(action, machine)
    try:
        resp = _post(base, endpoint, body)
        return {
            "ok": True,
            "connected": True,
            "actuated": True,
            "machine": machine,
            "action": action,
            "endpoint": endpoint,
            "response": resp,
            "ts": ts,
        }
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return {
            "ok": True,
            "connected": False,
            "actuated": False,
            "machine": machine,
            "action": action,
            "endpoint": endpoint,
            "error": "{}: {}".format(type(exc).__name__, exc),
            "ts": ts,
        }


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if cmd == "status":
        out = handle_status(payload)
    elif cmd == "actuate":
        out = handle_actuate(payload)
    elif cmd in ("ping", "health"):
        base = (payload or {}).get("url") or DEFAULT_URL
        try:
            out = {"ok": True, "connected": True, "health": _get(base, "/health")}
        except Exception as exc:
            out = {"ok": True, "connected": False, "error": str(exc)}
    else:
        sys.stdout.write(json.dumps({"ok": False, "error": "unknown command: " + repr(cmd)}))
        return 2
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
