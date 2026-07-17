"""E11 Config & master data — pr_* SQLAlchemy models (nền tảng).

Bao trọn: line/station/operation (P-CFG-01), master data part có phiên bản
(P-CFG-02), skill & phân quyền task (P-CFG-03), ngưỡng cảnh báo (P-CFG-04).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from db import Base, now


class PrLine(Base):
    __tablename__ = "pr_line"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "name": self.name, "active": self.active}


class PrStation(Base):
    __tablename__ = "pr_station"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    code = Column(String(32), nullable=False)
    name = Column(String(128), nullable=False)
    seq = Column(Integer, nullable=False, default=0)  # thứ tự station trên line
    __table_args__ = (UniqueConstraint("line_id", "code", name="uq_station_line_code"),)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "code": self.code,
            "name": self.name,
            "seq": self.seq,
        }


class PrOperation(Base):
    __tablename__ = "pr_operation"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=True)
    code = Column(String(64), nullable=False)  # operation ID (master data)
    name = Column(String(128), nullable=False)
    steps = Column(JSON, nullable=False, default=list)  # [{name, required, ...}] — P-CFG-01
    # Kỹ năng bắt buộc để làm operation này (P-CFG-03); null = ai cũng làm được.
    required_skill_id = Column(Integer, ForeignKey("pr_skill.id"), nullable=True)
    __table_args__ = (UniqueConstraint("line_id", "code", name="uq_operation_line_code"),)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "station_id": self.station_id,
            "code": self.code,
            "name": self.name,
            "steps": self.steps or [],
            "required_skill_id": self.required_skill_id,
        }


class PrPart(Base):
    """Master data part — có phiên bản (P-CFG-02). Mỗi (code, version) là một bản ghi."""

    __tablename__ = "pr_part"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    name = Column(String(128), nullable=False)
    ideal_cycle_time = Column(Float, nullable=True)  # giây/đơn vị — nền OEE
    __table_args__ = (UniqueConstraint("code", "version", name="uq_part_code_version"),)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "version": self.version,
            "name": self.name,
            "ideal_cycle_time": self.ideal_cycle_time,
        }


class PrSkill(Base):
    __tablename__ = "pr_skill"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)

    def as_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "name": self.name}


class PrOperatorSkill(Base):
    """Ai được phép làm operation nào (P-CFG-03)."""

    __tablename__ = "pr_operator_skill"
    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String(64), nullable=False)  # id operator (từ host/nhân sự)
    skill_id = Column(Integer, ForeignKey("pr_skill.id"), nullable=False)
    __table_args__ = (UniqueConstraint("operator_id", "skill_id", name="uq_operator_skill"),)

    def as_dict(self) -> dict:
        return {"id": self.id, "operator_id": self.operator_id, "skill_id": self.skill_id}


class PrThreshold(Base):
    """Ngưỡng cảnh báo theo line (P-CFG-04): downtime quá X phút, OEE dưới Y%."""

    __tablename__ = "pr_threshold"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    metric = Column(String(32), nullable=False)  # 'downtime_minutes' | 'oee_pct' | ...
    op = Column(String(4), nullable=False, default=">")  # '>' | '<' | '>=' | '<='
    value = Column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("line_id", "metric", name="uq_threshold_line_metric"),)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "metric": self.metric,
            "op": self.op,
            "value": self.value,
        }
