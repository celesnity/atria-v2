"""Deadline detection over vehicle rows (deterministic, no LLM)."""
from __future__ import annotations

from datetime import date, datetime

_URGENT_DAYS = 7
_SOON_DAYS = 30
_MOTORBIKE_TYPES = {"motorbike", "xe máy", "xe may", "motorcycle"}

# expiry column -> (kind, human label). Order defines display order.
_FIELDS = [
    ("inspection_expiry", "inspection", "Đăng kiểm"),
    ("civil_liability_expiry", "insurance", "Bảo hiểm TNDS"),
    ("registration_expiry", "registration", "Đăng ký xe"),
]


def parse_date(s: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date, tolerating blanks/None. Returns None if unparseable."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def urgency(days: int | None) -> str:
    """Bucket days-to-expiry into an urgency label."""
    if days is None:
        return "unknown"
    if days < 0:
        return "overdue"
    if days <= _URGENT_DAYS:
        return "urgent"
    if days <= _SOON_DAYS:
        return "soon"
    return "ok"


def _is_motorbike(vehicle: dict) -> bool:
    return str(vehicle.get("vehicle_type", "")).strip().lower() in _MOTORBIKE_TYPES


def deadlines_for_vehicle(vehicle: dict, today: date) -> list[dict]:
    """Return each applicable deadline for a vehicle, sorted most-urgent first.

    Motorbikes skip the inspection deadline (đăng kiểm not required). Blank or
    unparseable dates yield an ``unknown`` entry rather than a false deadline.
    """
    out: list[dict] = []
    for col, kind, label in _FIELDS:
        if kind == "inspection" and _is_motorbike(vehicle):
            continue
        expiry = parse_date(vehicle.get(col, ""))
        days = (expiry - today).days if expiry else None
        out.append({
            "kind": kind, "label": label,
            "expiry": expiry.isoformat() if expiry else None,
            "days_to_expiry": days, "urgency": urgency(days),
        })
    order = {"overdue": 0, "urgent": 1, "soon": 2, "ok": 3, "unknown": 4}
    return sorted(out, key=lambda d: (order[d["urgency"]], d["days_to_expiry"] is None,
                                      d["days_to_expiry"] if d["days_to_expiry"] is not None else 0))


def radar_for_user(ds, user_id: str, today: date) -> dict:
    """Return every vehicle's deadlines for a user."""
    vehicles = []
    for v in ds.vehicles_for_user(user_id):
        vehicles.append({
            "vehicle_id": v.get("vehicle_id"),
            "vehicle_type": v.get("vehicle_type"),
            "deadlines": deadlines_for_vehicle(v, today),
        })
    return {"user_id": user_id, "vehicles": vehicles}
