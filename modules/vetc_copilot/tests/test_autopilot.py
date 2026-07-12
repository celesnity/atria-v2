import json
from datetime import date
from datastore import Dataset
import autopilot


def _ds() -> Dataset:
    return Dataset(
        users=[{"user_id": "U001", "primary_vehicle_id": "VEH001"}],
        vehicles=[
            {
                "vehicle_id": "VEH001",
                "user_id": "U001",
                "vehicle_type": "Car",
                "fuel_type": "Gasoline",
                "vehicle_age_years": "8",
                "roadside_assistance_status": "Inactive",
                "inspection_expiry": "2026-07-20",
                "civil_liability_expiry": "2026-07-15",
                "registration_expiry": "2029-01-10",
            }
        ],
        documents=[],
        services=[
            {"service_id": "SVC001", "service_name": "Insurance"},
            {"service_id": "SVC002", "service_name": "Roadside"},
        ],
        knowledge=[
            {
                "knowledge_id": "K001",
                "question": "đăng kiểm khi nào",
                "answer": "Theo tuổi xe.",
                "topic": "Đăng kiểm",
            }
        ],
        eval_scenarios=[
            {
                "category": "Inspection Reminder",
                "user_id": "U001",
                "vehicle_id": "VEH001",
                "user_query": "khi nào đăng kiểm",
                "task_type": "AI Assistant QA",
            }
        ],
    )


def test_api_dispatch_radar():
    out = autopilot.api_dispatch("radar", {"user": "U001"}, _ds(), date(2026, 7, 5))
    assert out["vehicles"][0]["vehicle_id"] == "VEH001"


def test_api_dispatch_privacy_block():
    out = autopilot.api_dispatch(
        "radar", {"user": "U002", "as_user": "U001"}, _ds(), date(2026, 7, 5)
    )
    assert out.get("error")


def test_run_eval_covers_scenarios():
    results = autopilot.run_eval(_ds(), date(2026, 7, 5))
    assert len(results) == 1 and results[0]["category"] == "Inspection Reminder"


def test_main_radar_prints_json(capsys):
    # main loads default data/; monkeypatch below not needed for smoke
    rc = autopilot.main(
        ["--data", "MISSING_DIR", "radar", "--user", "U001", "--today", "2026-07-05"]
    )
    # With a missing data dir the dataset is empty; command still returns 0 and prints JSON.
    assert rc == 0
    json.loads(capsys.readouterr().out)
