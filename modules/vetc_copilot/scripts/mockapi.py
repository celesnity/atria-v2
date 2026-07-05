"""In-process mock of the challenge platform APIs (deterministic, labelled simulated)."""
from __future__ import annotations

from datetime import date, datetime


def add_one_year(iso: str) -> str:
    """Return the ISO date one year later; Feb-29 clamps to Feb-28."""
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        return date(d.year + 1, 2, 28).isoformat()


def wallet_pay(amount: int, order_id: str) -> dict:
    """Simulate a VETC Wallet payment. Deterministic txn id derived from the order."""
    return {"payment_status": "success", "txn_id": f"TXN-{order_id}", "amount": amount,
            "simulated": True}


def insurance_renew(vehicle_id: str, service_id: str, new_expiry: str) -> dict:
    """Simulate an insurance renewal, returning a policy id and the new expiry."""
    return {"status": "success", "policy_id": f"POL-{vehicle_id}-{service_id}",
            "new_expiry": new_expiry, "simulated": True}


def roadside_activate(vehicle_id: str) -> dict:
    """Simulate roadside-assistance activation for a vehicle."""
    return {"status": "activated", "vehicle_id": vehicle_id, "simulated": True}
