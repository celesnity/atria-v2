from datetime import date
from radar import urgency, deadlines_for_vehicle


def test_urgency_buckets():
    assert urgency(-1) == "overdue"
    assert urgency(3) == "urgent"
    assert urgency(20) == "soon"
    assert urgency(90) == "ok"
    assert urgency(None) == "unknown"


def test_motorbike_has_no_inspection_deadline():
    car = {"vehicle_type": "Car", "inspection_expiry": "2026-07-20",
           "civil_liability_expiry": "", "registration_expiry": ""}
    moto = {"vehicle_type": "Motorbike", "inspection_expiry": "2026-07-20",
            "civil_liability_expiry": "", "registration_expiry": ""}
    today = date(2026, 7, 5)
    car_kinds = {d["kind"] for d in deadlines_for_vehicle(car, today)}
    moto_kinds = {d["kind"] for d in deadlines_for_vehicle(moto, today)}
    assert "inspection" in car_kinds
    assert "inspection" not in moto_kinds
