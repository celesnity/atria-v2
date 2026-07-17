"""E2 Thực thi có hướng dẫn & e-SOP — logic thuần trên DB.

Phiên bản hoá SOP, chỉ phát hành bản duyệt (P-EXEC-06); phát hành bản mới sẽ
retire bản approved cũ. Xác nhận bước có poka-yoke: chặn nếu giá trị ngoài
[min,max] hoặc bỏ qua bước required chưa xong (P-EXEC-02/03/04).
"""

from __future__ import annotations

from sqlalchemy import select

import events
from db import db_session, now

from .models import PrSop, PrSopVersion, PrStepConfirm


class SopError(Exception):
    """Vi phạm luật nghiệp vụ E2 (poka-yoke, phát hành sai...)."""


# --- SOP + version (P-EXEC-06) --------------------------------------------------
def list_sops() -> list[dict]:
    """All SOPs (for pickers)."""
    with db_session() as s:
        return [r.as_dict() for r in s.scalars(select(PrSop).order_by(PrSop.id)).all()]


def create_sop(code: str, title: str, operation_id: int | None = None) -> dict:
    with db_session() as s:
        sop = PrSop(code=code, title=title, operation_id=operation_id)
        s.add(sop)
        s.flush()
        return sop.as_dict()


def add_draft_version(sop_id: int, steps: list[dict]) -> dict:
    with db_session() as s:
        latest = s.scalars(
            select(PrSopVersion)
            .where(PrSopVersion.sop_id == sop_id)
            .order_by(PrSopVersion.version.desc())
        ).first()
        nxt = (latest.version + 1) if latest else 1
        v = PrSopVersion(sop_id=sop_id, version=nxt, status="draft", steps=steps)
        s.add(v)
        s.flush()
        return v.as_dict()


def publish_version(version_id: int) -> dict:
    """Phát hành bản duyệt; retire bản approved trước đó của cùng SOP."""
    with db_session() as s:
        v = s.get(PrSopVersion, version_id)
        if v is None:
            raise SopError(f"sop version {version_id} không tồn tại")
        if v.status == "retired":
            raise SopError("không phát hành bản đã retired")
        for prev in s.scalars(
            select(PrSopVersion).where(
                PrSopVersion.sop_id == v.sop_id, PrSopVersion.status == "approved"
            )
        ).all():
            prev.status = "retired"
        v.status = "approved"
        v.published_at = now()
        s.flush()
        return v.as_dict()


def released_version(sop_id: int) -> dict | None:
    """Bản approved hiện hành cho operator xem (P-EXEC-01)."""
    with db_session() as s:
        v = s.scalars(
            select(PrSopVersion).where(
                PrSopVersion.sop_id == sop_id, PrSopVersion.status == "approved"
            )
        ).first()
        return v.as_dict() if v else None


# --- Step confirm + poka-yoke (P-EXEC-02/03/04) ---------------------------------
def confirm_step(
    job_id: int, sop_version_id: int, step_index: int, value: float | None = None
) -> dict:
    with db_session() as s:
        v = s.get(PrSopVersion, sop_version_id)
        if v is None:
            raise SopError(f"sop version {sop_version_id} không tồn tại")
        steps = v.steps or []
        if step_index < 0 or step_index >= len(steps):
            raise SopError(f"step_index {step_index} ngoài phạm vi")
        spec = steps[step_index]

        # Poka-yoke: giá trị đo phải trong [min, max] nếu spec định nghĩa.
        lo, hi = spec.get("min"), spec.get("max")
        if (lo is not None or hi is not None) and value is None:
            raise SopError("bước yêu cầu nhập giá trị đo")
        if value is not None:
            if lo is not None and value < lo:
                raise SopError(f"giá trị {value} < ngưỡng dưới {lo} (poka-yoke)")
            if hi is not None and value > hi:
                raise SopError(f"giá trị {value} > ngưỡng trên {hi} (poka-yoke)")

        # Chặn bỏ qua: mọi bước required trước đó phải đã confirm (P-EXEC-03).
        done = {
            c.step_index
            for c in s.scalars(
                select(PrStepConfirm).where(PrStepConfirm.job_id == job_id)
            ).all()
        }
        for i in range(step_index):
            if steps[i].get("required") and i not in done:
                raise SopError(f"chưa hoàn thành bước bắt buộc {i} trước khi làm bước {step_index}")

        c = PrStepConfirm(
            job_id=job_id, sop_version_id=sop_version_id, step_index=step_index, value=value
        )
        s.add(c)
        s.flush()
        result = c.as_dict()
        events.emit("step.confirmed", result)
        return result


def diff_last_version(sop_id: int) -> dict:
    """So sánh bản approved hiện hành với bản gần nhất trước đó (P-EXEC-05).

    Trả tên bước được thêm / bỏ / đổi để operator không làm theo bản cũ.
    """
    with db_session() as s:
        versions = s.scalars(
            select(PrSopVersion)
            .where(PrSopVersion.sop_id == sop_id)
            .order_by(PrSopVersion.version.desc())
        ).all()
        if not versions:
            raise SopError(f"SOP {sop_id} chưa có version nào")
        current = versions[0]
        prev = versions[1] if len(versions) > 1 else None
        cur_steps = {st.get("name"): st for st in (current.steps or [])}
        prev_steps = {st.get("name"): st for st in (prev.steps or [])} if prev else {}
        added = [n for n in cur_steps if n not in prev_steps]
        removed = [n for n in prev_steps if n not in cur_steps]
        changed = [n for n in cur_steps if n in prev_steps and cur_steps[n] != prev_steps[n]]
        return {
            "sop_id": sop_id,
            "current_version": current.version,
            "previous_version": prev.version if prev else None,
            "added": added,
            "removed": removed,
            "changed": changed,
        }


def job_progress(job_id: int) -> list[dict]:
    with db_session() as s:
        stmt = (
            select(PrStepConfirm)
            .where(PrStepConfirm.job_id == job_id)
            .order_by(PrStepConfirm.step_index)
        )
        return [r.as_dict() for r in s.scalars(stmt).all()]
