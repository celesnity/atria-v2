"""E6 Cycle time & OEE — pr_* models.

pr_production_order: chuẩn để so sánh — ideal cycle time + target count cho ca
(P-OEE-02). OEE (Availability × Performance × Quality) tính runtime từ E3/E4/E5,
không lưu bảng riêng ở MVP (snapshot tính on-demand).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer

from db import Base, now


class PrProductionOrder(Base):
    __tablename__ = "pr_production_order"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=False)
    part_id = Column(Integer, ForeignKey("pr_part.id"), nullable=True)
    ideal_cycle_time = Column(Float, nullable=False)  # giây/đơn vị
    target_count = Column(Integer, nullable=False, default=0)
    planned_minutes = Column(Float, nullable=False, default=0.0)  # thời gian sản xuất kế hoạch
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "shift_id": self.shift_id,
            "part_id": self.part_id,
            "ideal_cycle_time": self.ideal_cycle_time,
            "target_count": self.target_count,
            "planned_minutes": self.planned_minutes,
        }
