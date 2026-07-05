from datetime import date
from datastore import Dataset
from brain import recommend, ask


def _ds() -> Dataset:
    return Dataset(
        users=[{"user_id": "U001", "primary_vehicle_id": "VEH001"}],
        vehicles=[{"vehicle_id": "VEH001", "user_id": "U001", "vehicle_type": "Car",
                   "fuel_type": "Gasoline", "vehicle_age_years": "8",
                   "roadside_assistance_status": "Inactive",
                   "inspection_expiry": "2026-07-20", "civil_liability_expiry": "2026-07-15",
                   "registration_expiry": "2029-01-10"}],
        services=[
            {"service_id": "SVC001", "service_name": "Civil Liability Insurance Renewal",
             "context_to_recommend": "insurance expiring"},
            {"service_id": "SVC002", "service_name": "Roadside Assistance",
             "context_to_recommend": "old vehicle"},
        ],
        knowledge=[{"knowledge_id": "K001", "question": "Khi nào cần đăng kiểm",
                    "answer": "Theo tuổi xe.", "topic": "Đăng kiểm"}],
    )


def test_recommend_flags_insurance_and_roadside():
    recs = recommend(_ds(), "U001", date(2026, 7, 5))
    ids = {r["service_id"] for r in recs}
    assert "SVC001" in ids  # insurance expiring in 10 days
    assert "SVC002" in ids  # age 8 > 7 and roadside inactive


def test_ask_offline_is_grounded_and_cited():
    out = ask(_ds(), "U001", "Khi nào cần đăng kiểm?", date(2026, 7, 5), client=None)
    assert "K001" in out["citations"]
    assert out["advisory"]
    assert out["source"] == "offline"


def test_ask_uncovered_question_abstains():
    out = ask(_ds(), "U001", "zzz qqq www", date(2026, 7, 5), client=None)
    assert out["citations"] == []
    assert out["needs_review"] is True
