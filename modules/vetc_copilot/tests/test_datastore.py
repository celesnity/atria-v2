from pathlib import Path
from datastore import load_dataset


def _seed(tmp: Path) -> Path:
    d = tmp / "data"
    d.mkdir()
    (d / "vehicles.csv").write_text(
        "vehicle_id,user_id,vehicle_type\nVEH001,U001,Car\nVEH002,U001,Motorbike\n",
        encoding="utf-8",
    )
    for name in ("users", "documents", "services", "knowledge", "eval_scenarios"):
        (d / f"{name}.csv").write_text("id\n", encoding="utf-8")
    return d


def test_vehicles_for_user(tmp_path):
    ds = load_dataset(_seed(tmp_path))
    assert [v["vehicle_id"] for v in ds.vehicles_for_user("U001")] == ["VEH001", "VEH002"]
    assert ds.vehicle("VEH002")["vehicle_type"] == "Motorbike"
