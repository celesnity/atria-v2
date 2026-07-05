"""Load the materialized CSVs into an in-memory dataset (the mock 'platform')."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


@dataclass
class Dataset:
    """All P5 tables loaded as lists of string-valued dict rows."""

    users: list[dict[str, str]] = field(default_factory=list)
    vehicles: list[dict[str, str]] = field(default_factory=list)
    documents: list[dict[str, str]] = field(default_factory=list)
    services: list[dict[str, str]] = field(default_factory=list)
    knowledge: list[dict[str, str]] = field(default_factory=list)
    eval_scenarios: list[dict[str, str]] = field(default_factory=list)

    def user(self, uid: str) -> dict[str, str] | None:
        """Return the user row for ``uid`` or ``None``."""
        return next((u for u in self.users if u.get("user_id") == uid), None)

    def vehicle(self, vid: str) -> dict[str, str] | None:
        """Return the vehicle row for ``vid`` or ``None``."""
        return next((v for v in self.vehicles if v.get("vehicle_id") == vid), None)

    def vehicles_for_user(self, uid: str) -> list[dict[str, str]]:
        """Return all vehicle rows owned by ``uid``, in file order."""
        return [v for v in self.vehicles if v.get("user_id") == uid]

    def documents_for_vehicle(self, vid: str) -> list[dict[str, str]]:
        """Return all document rows for ``vid``, in file order."""
        return [d for d in self.documents if d.get("vehicle_id") == vid]


def apply_renewals(ds: Dataset, renewals: list[dict]) -> None:
    """Overlay finalized renewals onto vehicles/documents (dedup by policy_id).

    Bumps the vehicle's expiry column and appends the policy document. The
    committed CSVs are untouched; this reflects runtime IPN-confirmed renewals.
    """
    existing = {d.get("document_id") for d in ds.documents}
    for r in renewals:
        pid = r.get("policy_id")
        vehicle = ds.vehicle(r.get("vehicle_id", ""))
        col, new_expiry = r.get("col"), r.get("new_expiry")
        if vehicle and col and new_expiry:
            vehicle[col] = new_expiry
        if pid and pid not in existing:
            existing.add(pid)
            ds.documents.append(
                {
                    "document_id": pid,
                    "vehicle_id": r.get("vehicle_id"),
                    "document_type": "Insurance",
                    "document_name": r.get("document_name") or pid,
                    "status": "Valid",
                    "issue_date": "",
                    "expiry_date": new_expiry or "",
                    "uploaded": "Yes",
                    "notes": "Gia hạn qua cổng VETC (đã xác nhận IPN)",
                }
            )


def load_dataset(data_dir: str | Path | None = None) -> Dataset:
    """Load all CSVs from ``data_dir`` (default: module ``data/``) into a Dataset.

    Also overlays IPN-confirmed renewals from ``renewals.jsonl`` so every reader
    reflects completed payments without mutating the committed CSVs.
    """
    base = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
    ds = Dataset(
        users=_read_csv(base / "users.csv"),
        vehicles=_read_csv(base / "vehicles.csv"),
        documents=_read_csv(base / "documents.csv"),
        services=_read_csv(base / "services.csv"),
        knowledge=_read_csv(base / "knowledge.csv"),
        eval_scenarios=_read_csv(base / "eval_scenarios.csv"),
    )
    from renewals import load_renewals  # local import: optional runtime overlay

    apply_renewals(ds, load_renewals(base / "renewals.jsonl"))
    return ds
