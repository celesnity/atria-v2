"""module_template data layer. Reuses the shared `minder` Postgres INSTANCE but
owns only the mt_* tables; reads Minder tables read-only. Never imports `minder`."""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
from typing import Iterator

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("module_template.db")

MT_DATABASE_URL = os.environ.get("MT_DATABASE_URL", "postgresql://minder:minder@db:5432/minder")

engine = create_engine(MT_DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class MtJob(Base):
    __tablename__ = "mt_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(64), nullable=False, default="demo")
    status = Column(String(16), nullable=False, default="queued")  # queued|running|done|error
    pct = Column(Integer, nullable=False, default=0)
    params_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "pct": self.pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MtMedia(Base):
    __tablename__ = "mt_media"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    s3_key = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "s3_key": self.s3_key,
            "content_type": self.content_type,
            "size": self.size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def init_db() -> None:
    """Create ONLY the module's own mt_* tables (checkfirst). Never touches Minder tables."""
    Base.metadata.create_all(engine, checkfirst=True)


@contextlib.contextmanager
def db_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# --- read-only Minder reads (best-effort; degrade on schema drift) ---------------
def list_conversations(limit: int = 10) -> list[dict]:
    sql = text(
        "SELECT id, title, mode, status, created_at FROM conversations "
        "WHERE is_deleted = false ORDER BY id DESC LIMIT :limit"
    )
    try:
        with engine.connect() as c:
            return [
                dict(r._mapping) | {"created_at": str(r._mapping["created_at"])}
                for r in c.execute(sql, {"limit": limit})
            ]
    except Exception as exc:  # noqa: BLE001 — read-only best-effort
        logger.warning("read conversations failed (degrading): %s", exc)
        return []


def count_artifacts() -> int:
    try:
        with engine.connect() as c:
            return int(
                c.execute(text("SELECT count(*) FROM artifacts WHERE is_deleted = false")).scalar()
                or 0
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("count artifacts failed (degrading): %s", exc)
        return 0


def recent_artifacts(limit: int = 10) -> list[dict]:
    sql = text(
        "SELECT id, title, type, created_at FROM artifacts WHERE is_deleted = false "
        "ORDER BY id DESC LIMIT :limit"
    )
    try:
        with engine.connect() as c:
            return [
                dict(r._mapping) | {"created_at": str(r._mapping["created_at"])}
                for r in c.execute(sql, {"limit": limit})
            ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("read artifacts failed (degrading): %s", exc)
        return []
