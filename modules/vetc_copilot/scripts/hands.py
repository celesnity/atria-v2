"""Hands: execute a renewal end-to-end over the mock APIs (consent-gated)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # type: ignore[import-not-found]
import mockapi  # type: ignore[import-not-found]
from guardrails import ADVISORY_NOTE, consent_gate  # type: ignore[import-not-found]

# Illustrative demo amounts (VND). Real pricing comes from the insurer partner.
PRICES: dict[str, int] = {"SVC001": 500700, "SVC002": 300000, "SVC003": 0}

# service id -> (expiry column it renews)
_EXPIRY_COL = {"SVC001": "civil_liability_expiry", "SVC003": "inspection_expiry"}


def renew(ds, user_id: str, vehicle_id: str, service_id: str, today: date,
          consent: bool = True, audit_path: str | Path | None = None) -> dict:
    """Run consent -> pay -> renew -> update wallet -> audit; return a receipt.

    Args:
        ds: The loaded Dataset (updated in place on success).
        user_id: Owner initiating the renewal.
        vehicle_id: Vehicle to renew.
        service_id: Service being renewed (must be in the catalog).
        today: Reference date (unused for the +1y math but kept for audit context).
        consent: Whether the user explicitly consented to the transaction.
        audit_path: Optional audit-log override (tests inject a temp path).

    Returns:
        A receipt dict; ``{"ok": False, "reason": ...}`` when blocked.
    """
    ok, reason = consent_gate(consent)
    if not ok:
        return {"ok": False, "reason": reason}
    vehicle = ds.vehicle(vehicle_id)
    if not vehicle or vehicle.get("user_id") != user_id:
        return {"ok": False, "reason": "Không tìm thấy xe hợp lệ cho người dùng này."}
    service = next((s for s in ds.services if s.get("service_id") == service_id), None)
    if not service:
        return {"ok": False, "reason": "Dịch vụ không tồn tại."}

    col = _EXPIRY_COL.get(service_id, "civil_liability_expiry")
    old_expiry = vehicle.get(col, "")
    new_expiry = mockapi.add_one_year(old_expiry) if old_expiry else ""
    amount = PRICES.get(service_id, 0)

    pay = mockapi.wallet_pay(amount, f"ORD-{vehicle_id}-{service_id}")
    renewal = mockapi.insurance_renew(vehicle_id, service_id, new_expiry)

    if new_expiry:
        vehicle[col] = new_expiry
    ds.documents.append({
        "document_id": renewal["policy_id"], "vehicle_id": vehicle_id,
        "document_type": "Insurance", "document_name": service.get("service_name", service_id),
        "status": "Valid", "issue_date": today.isoformat(), "expiry_date": new_expiry,
        "uploaded": "Yes", "notes": "Gia hạn qua Auto-Pilot (mô phỏng)",
    })
    receipt = {
        "ok": True, "service_id": service_id, "service_name": service.get("service_name", service_id),
        "policy_id": renewal["policy_id"], "amount": amount, "txn_id": pay["txn_id"],
        "old_expiry": old_expiry, "new_expiry": new_expiry, "wallet_updated": True,
        "simulated": True, "advisory": ADVISORY_NOTE,
    }
    audit.append_event({"type": "renew", **{k: receipt[k] for k in
                        ("service_id", "policy_id", "amount", "old_expiry", "new_expiry")}}, audit_path)
    return receipt
