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


def test_renew_uses_real_vetc_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("VETC_CLIENT_ID", "cid")
    monkeypatch.setenv("VETC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("VETC_IPN_URL", "http://vetc-copilot:8770/ipn")
    pending_path = tmp_path / "pending.jsonl"
    import renewals

    monkeypatch.setattr(renewals, "_data_dir", lambda: tmp_path)
    captured = {}
    import vetc_client

    class _FakeVetc:
        def __init__(self, cfg):
            pass

        def init_payment(self, order_id, amount, description, metadata, idempotency_key=None):
            captured["ipn_url"] = metadata.get("ipn_url")
            captured["order_id"] = order_id
            return {"id": "pay_1", "status": "CREATED", "provider_payload": {"signature": "SIG"}}

    monkeypatch.setattr(vetc_client, "VetcClient", _FakeVetc)
    ds = _ds()
    r = renew(ds, "U001", "VEH001", "SVC001", date(2026, 7, 5), consent=True, audit_path=tmp_path / "a.jsonl")
    assert r["ok"] is True and r["simulated"] is False and r["pending_user_confirmation"] is True
    assert r["policy_id"] == "POL-VEH001-SVC001"
    assert captured["ipn_url"] == "http://vetc-copilot:8770/ipn"
    assert renewals.find_pending(captured["order_id"], pending_path)["policy_id"] == "POL-VEH001-SVC001"
