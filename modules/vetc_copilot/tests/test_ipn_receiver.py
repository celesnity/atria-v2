import renewals
from ipn_sig import ipn_sign
from autopilot import handle_ipn


def test_ipn_finalizes_pending(tmp_path):
    pend = tmp_path / "pending.jsonl"
    ren = tmp_path / "renewals.jsonl"
    renewals.append_pending(
        {
            "order_id": "ORD1",
            "vehicle_id": "VEH001",
            "col": "civil_liability_expiry",
            "new_expiry": "2027-08-15",
            "policy_id": "POL-1",
            "service_name": "Ins",
        },
        pend,
    )
    sig = ipn_sign("ORD1", "PAY1", "SUCCESS", "hmac")
    code, out = handle_ipn(
        {"order_id": "ORD1", "payment_id": "PAY1", "status": "SUCCESS", "signature": sig},
        "hmac",
        pending_path=pend,
        renewals_path=ren,
    )
    assert code == 200 and out["code"] == "00"
    assert len(renewals.load_renewals(ren)) == 1


def test_ipn_rejects_bad_signature(tmp_path):
    code, out = handle_ipn(
        {"order_id": "ORD1", "payment_id": "PAY1", "status": "SUCCESS", "signature": "bad"},
        "hmac",
        pending_path=tmp_path / "p.jsonl",
        renewals_path=tmp_path / "r.jsonl",
    )
    assert code == 401


def test_ipn_replay_is_idempotent(tmp_path):
    pend = tmp_path / "pending.jsonl"
    ren = tmp_path / "renewals.jsonl"
    renewals.append_pending(
        {
            "order_id": "ORD1",
            "vehicle_id": "VEH001",
            "col": "civil_liability_expiry",
            "new_expiry": "2027-08-15",
            "policy_id": "POL-1",
            "service_name": "Ins",
        },
        pend,
    )
    payload = {
        "order_id": "ORD1",
        "payment_id": "PAY1",
        "status": "SUCCESS",
        "signature": ipn_sign("ORD1", "PAY1", "SUCCESS", "hmac"),
    }
    handle_ipn(payload, "hmac", pending_path=pend, renewals_path=ren)
    handle_ipn(payload, "hmac", pending_path=pend, renewals_path=ren)
    assert len(renewals.load_renewals(ren)) == 1
