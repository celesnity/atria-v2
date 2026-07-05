from datetime import date
from datastore import Dataset
from hands import renew
import audit


def _ds() -> Dataset:
    return Dataset(
        users=[{"user_id": "U001"}],
        vehicles=[
            {
                "vehicle_id": "VEH001",
                "user_id": "U001",
                "vehicle_type": "Car",
                "civil_liability_expiry": "2026-08-15",
            }
        ],
        documents=[],
        services=[{"service_id": "SVC001", "service_name": "Civil Liability Insurance Renewal"}],
    )


def test_renew_happy_path_updates_wallet(tmp_path):
    ds = _ds()
    p = tmp_path / "audit.jsonl"
    r = renew(ds, "U001", "VEH001", "SVC001", date(2026, 7, 5), consent=True, audit_path=p)
    assert r["ok"] is True
    assert r["new_expiry"] == "2027-08-15"
    assert r["policy_id"].startswith("POL-")
    assert ds.vehicle("VEH001")["civil_liability_expiry"] == "2027-08-15"
    assert any(d["document_type"] == "Insurance" for d in ds.documents_for_vehicle("VEH001"))
    assert audit.read_events(p)[0]["type"] == "renew"


def test_renew_blocked_without_consent():
    r = renew(_ds(), "U001", "VEH001", "SVC001", date(2026, 7, 5), consent=False)
    assert r["ok"] is False and r["reason"]
