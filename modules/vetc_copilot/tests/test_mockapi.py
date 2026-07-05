import mockapi
import audit


def test_wallet_pay_is_deterministic():
    a = mockapi.wallet_pay(500000, "ORD-VEH001")
    b = mockapi.wallet_pay(500000, "ORD-VEH001")
    assert a["payment_status"] == "success"
    assert a == b  # derived from inputs, no randomness


def test_insurance_renew_returns_policy():
    r = mockapi.insurance_renew("VEH001", "SVC001", "2027-08-15")
    assert r["policy_id"].startswith("POL-")
    assert r["new_expiry"] == "2027-08-15"


def test_add_one_year_clamps_leap_day():
    assert mockapi.add_one_year("2024-02-29") == "2025-02-28"
    assert mockapi.add_one_year("2026-08-15") == "2027-08-15"


def test_audit_roundtrip(tmp_path):
    p = tmp_path / "audit.jsonl"
    audit.append_event({"type": "renew", "policy_id": "POL-X"}, p)
    audit.append_event({"type": "ask"}, p)
    events = audit.read_events(p)
    assert len(events) == 2 and events[0]["policy_id"] == "POL-X"
