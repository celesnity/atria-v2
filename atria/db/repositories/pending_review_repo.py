"""CRUD for the pending_reviews table.

Persists UI-blocking review/approval requests so the user's response is
recorded even if the agent run that produced the request is gone (e.g.
after a container restart). The agent's in-process waiter cannot be
revived from the DB — a threading.Event lives only in memory — but the
WebSocket handler can still ack the user's click against a stored row.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atria.db.models import PendingReview
from atria.db.repositories.base import BaseRepository


def _flatten(model_instance) -> dict:
    return {c.name: getattr(model_instance, c.name) for c in model_instance.__table__.columns}


class PendingReviewRepository(BaseRepository):
    async def upsert(
        self,
        request_id: str,
        kind: str,
        session_id: Optional[str],
        user_id: Optional[int],
        request_data: Optional[dict[str, Any]],
    ) -> int:
        """Insert a pending review; if request_id already exists, leave it alone.

        Returning the row id either way.
        """
        async with self._sessionmaker() as session:
            stmt = (
                pg_insert(PendingReview)
                .values(
                    request_id=request_id,
                    kind=kind[:32],
                    session_id=session_id,
                    user_id=user_id,
                    request_data=request_data,
                    resolved=False,
                )
                .on_conflict_do_nothing(index_elements=["request_id"])
                .returning(PendingReview.id)
            )
            result = await session.execute(stmt)
            new_id = result.scalar_one_or_none()
            if new_id is None:
                # Conflict path — fetch existing row's id.
                existing = await session.execute(
                    select(PendingReview.id).where(PendingReview.request_id == request_id)
                )
                new_id = int(existing.scalar_one())
            await session.commit()
            return int(new_id)

    async def get_by_request_id(self, request_id: str) -> Optional[dict]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingReview).where(PendingReview.request_id == request_id)
            )
            obj = result.scalars().first()
            return _flatten(obj) if obj else None

    async def resolve(
        self,
        request_id: str,
        response_data: dict[str, Any],
    ) -> bool:
        """Mark a pending review resolved. Returns True iff a row was updated.

        Idempotent in the practical sense: if already resolved, returns False
        (so callers can distinguish "first ack" from "double-click").
        """
        async with self._sessionmaker() as session:
            stmt = (
                update(PendingReview)
                .where(
                    PendingReview.request_id == request_id,
                    PendingReview.resolved.is_(False),
                )
                .values(
                    resolved=True,
                    response_data=response_data,
                    resolved_at=func.now(),
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def list_unresolved(
        self,
        kind: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        async with self._sessionmaker() as session:
            stmt = select(PendingReview).where(PendingReview.resolved.is_(False))
            if kind:
                stmt = stmt.where(PendingReview.kind == kind)
            if session_id:
                stmt = stmt.where(PendingReview.session_id == session_id)
            stmt = stmt.order_by(PendingReview.created_at.desc())
            result = await session.execute(stmt)
            return [_flatten(obj) for obj in result.scalars().all()]
