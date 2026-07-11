"""Hands: execute a renewal end-to-end over the mock APIs (consent-gated)."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # type: ignore[import-not-found]
import mockapi  # type: ignore[import-not-found]
from guardrails import ADVISORY_NOTE, consent_gate  # type: ignore[import-not-found]

# Illustrative demo amounts (VND). Real pricing comes from the insurer/inspection
# partner. Must be > 0 — the VETC payment gateway rejects a 0-amount charge.
PRICES: dict[str, int] = {"SVC001": 500700, "SVC002": 300000, "SVC003": 340000}

# service id -> (expiry column it renews)
_EXPIRY_COL = {"SVC001": "civil_liability_expiry", "SVC003": "inspection_expiry"}


def renew(
    ds,
    user_id: str,
    vehicle_id: str,
    service_id: str,
    today: date,
    consent: bool = True,
    audit_path: str | Path | None = None,
) -> dict:
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

    # Real VETC gateway when credentials are configured; else the mock path below.
    from vetc_config import load_vetc_config  # local import: optional integration

    vcfg = load_vetc_config()
    if vcfg.configured:
        return _renew_via_vetc(
            vcfg, service, vehicle_id, service_id, amount, old_expiry, new_expiry, today, audit_path
        )

    pay = mockapi.wallet_pay(amount, f"ORD-{vehicle_id}-{service_id}")
    renewal = mockapi.insurance_renew(vehicle_id, service_id, new_expiry)

    if new_expiry:
        vehicle[col] = new_expiry
    ds.documents.append(
        {
            "document_id": renewal["policy_id"],
            "vehicle_id": vehicle_id,
            "document_type": "Insurance",
            "document_name": service.get("service_name", service_id),
            "status": "Valid",
            "issue_date": today.isoformat(),
            "expiry_date": new_expiry,
            "uploaded": "Yes",
            "notes": "Gia hạn qua Auto-Pilot (mô phỏng)",
        }
    )
    receipt = {
        "ok": True,
        "service_id": service_id,
        "service_name": service.get("service_name", service_id),
        "policy_id": renewal["policy_id"],
        "amount": amount,
        "txn_id": pay["txn_id"],
        "old_expiry": old_expiry,
        "new_expiry": new_expiry,
        "wallet_updated": True,
        "simulated": True,
        "advisory": ADVISORY_NOTE,
    }
    audit.append_event(
        {
            "type": "renew",
            **{
                k: receipt[k]
                for k in ("service_id", "policy_id", "amount", "old_expiry", "new_expiry")
            },
        },
        audit_path,
    )
    return receipt


def _renew_via_vetc(
    cfg,
    service: dict,
    vehicle_id: str,
    service_id: str,
    amount: int,
    old_expiry: str,
    new_expiry: str,
    today: date,
    audit_path: str | Path | None,
) -> dict:
    """Initiate a REAL payment on the VETC gateway (VMA Payment).

    Records a pending renewal and passes ``ipn_url`` so the gateway can push a
    signed IPN back to finalize it. The policy is finalized only after the IPN
    confirms payment, so the wallet is not updated here.
    """
    from vetc_client import VetcClient, VetcError  # local import: optional integration
    from renewals import append_pending  # local import: runtime persistence

    service_name = service.get("service_name", service_id)
    policy_id = f"POL-{vehicle_id}-{service_id}"
    order_id = f"ORD-{vehicle_id}-{service_id}-{today.isoformat()}"
    metadata = {
        "provider_name": "VETC",
        "service_name": service_name,
        "product_code": service_id,
        "product_name": service_name,
        "merchant_service": "vetc_copilot",
        "ipn_url": os.environ.get("VETC_IPN_URL", ""),
    }
    try:
        payment = VetcClient(cfg).init_payment(
            order_id, amount, f"Gia hạn {service_name}", metadata, idempotency_key=order_id
        )
    except VetcError as exc:
        return {"ok": False, "reason": f"Lỗi thanh toán VETC: {exc}"}

    append_pending({
        "order_id": order_id, "vehicle_id": vehicle_id, "service_id": service_id,
        "col": _EXPIRY_COL.get(service_id, "civil_liability_expiry"), "new_expiry": new_expiry,
        "amount": amount, "service_name": service_name, "policy_id": policy_id,
        "payment_id": payment.get("id"),
    })
    audit.append_event(
        {"type": "renew_init", "service_id": service_id, "order_id": order_id,
         "payment_id": payment.get("id"), "amount": amount, "gateway": "vetc"},
        audit_path,
    )
    return {
        "ok": True, "service_id": service_id, "service_name": service_name, "amount": amount,
        "order_id": order_id, "payment_id": payment.get("id"), "policy_id": policy_id,
        "status": payment.get("status", "CREATED"),
        "provider_payload": payment.get("provider_payload"),
        "old_expiry": old_expiry, "new_expiry": new_expiry, "wallet_updated": False,
        "pending_user_confirmation": True, "simulated": False, "advisory": ADVISORY_NOTE,
        "note": (
            "Đã khởi tạo thanh toán trên cổng VETC. Hoàn tất trong ứng dụng VETC; "
            "giấy tờ cập nhật sau khi có xác nhận thanh toán (IPN)."
        ),
    }
