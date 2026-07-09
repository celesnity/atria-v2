from renewals import append_pending, find_pending, finalize, load_renewals


def test_pending_roundtrip(tmp_path):
    p = tmp_path / "pending.jsonl"
    append_pending({"order_id": "ORD1", "vehicle_id": "VEH001", "policy_id": "POL-1"}, p)
    assert find_pending("ORD1", p)["vehicle_id"] == "VEH001"
    assert find_pending("NOPE", p) is None


def test_finalize_is_idempotent(tmp_path):
    rp = tmp_path / "renewals.jsonl"
    pend = {"order_id": "ORD1", "vehicle_id": "VEH001", "col": "civil_liability_expiry",
            "new_expiry": "2027-08-15", "policy_id": "POL-1", "service_name": "Ins"}
    assert finalize("ORD1", pend, rp) is True
    assert finalize("ORD1", pend, rp) is False  # duplicate ignored
    rows = load_renewals(rp)
    assert len(rows) == 1 and rows[0]["new_expiry"] == "2027-08-15"
