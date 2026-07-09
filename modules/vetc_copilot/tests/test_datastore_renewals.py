from datastore import Dataset, apply_renewals


def _ds() -> Dataset:
    return Dataset(
        vehicles=[
            {"vehicle_id": "VEH001", "user_id": "U001", "civil_liability_expiry": "2026-08-15"}
        ],
        documents=[],
    )


def test_apply_renewals_bumps_expiry_and_adds_policy():
    ds = _ds()
    apply_renewals(
        ds,
        [
            {
                "order_id": "ORD1",
                "vehicle_id": "VEH001",
                "col": "civil_liability_expiry",
                "new_expiry": "2027-08-15",
                "policy_id": "POL-1",
                "document_name": "Ins",
            }
        ],
    )
    assert ds.vehicle("VEH001")["civil_liability_expiry"] == "2027-08-15"
    docs = ds.documents_for_vehicle("VEH001")
    assert len(docs) == 1 and docs[0]["document_id"] == "POL-1"


def test_apply_renewals_dedup_by_policy_id():
    ds = _ds()
    r = [
        {
            "order_id": "ORD1",
            "vehicle_id": "VEH001",
            "col": "civil_liability_expiry",
            "new_expiry": "2027-08-15",
            "policy_id": "POL-1",
            "document_name": "Ins",
        }
    ]
    apply_renewals(ds, r)
    apply_renewals(ds, r)
    assert len(ds.documents_for_vehicle("VEH001")) == 1
