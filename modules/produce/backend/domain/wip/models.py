"""E3 WIP & bước sản xuất — pr_* models.

pr_job (instance thực thi của task, start/end timestamp tự động — P-WIP-01),
pr_job_step (timing từng step), pr_count (sản lượng tại station — P-WIP-02),
pr_station_status (trạng thái station hiện tại — P-WIP-03),
pr_lot_link (gắn QR/barcode lot vào job — P-WIP-06, truy xuất nguồn gốc).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db import Base, now

JOB_STATES = ("running", "done", "aborted")
STATION_STATES = ("idle", "running", "down", "blocked", "setup")


class PrJob(Base):
    __tablename__ = "pr_job"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("pr_task.id"), nullable=False)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=True)
    operator_id = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)  # tự động
    ended_at = Column(DateTime(timezone=True), nullable=True)  # tự động khi complete

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "station_id": self.station_id,
            "operator_id": self.operator_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class PrJobStep(Base):
    __tablename__ = "pr_job_step"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=False)
    seq = Column(Integer, nullable=False, default=0)
    name = Column(String(128), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "seq": self.seq,
            "name": self.name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class PrCount(Base):
    """Sản lượng ghi tại station (P-WIP-02)."""

    __tablename__ = "pr_count"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=True)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=False)
    qty = Column(Integer, nullable=False, default=0)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "station_id": self.station_id,
            "qty": self.qty,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class PrStationStatus(Base):
    """Trạng thái hiện tại của station (P-WIP-03). Một hàng / station, cập nhật tại chỗ."""

    __tablename__ = "pr_station_status"
    station_id = Column(Integer, ForeignKey("pr_station.id"), primary_key=True)
    status = Column(String(16), nullable=False, default="idle")
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)

    def as_dict(self) -> dict:
        return {
            "station_id": self.station_id,
            "status": self.status,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PrLotLink(Base):
    """Gắn mã QR/barcode của vật tư hoặc lot vào job (P-WIP-06)."""

    __tablename__ = "pr_lot_link"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=False)
    code = Column(String(128), nullable=False)  # nội dung QR/barcode
    kind = Column(String(32), nullable=False, default="lot")  # 'lot' | 'material' | ...
    scanned_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "code": self.code,
            "kind": self.kind,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
        }
