"""Engine data layer. Owns only pr_* tables; never imports the old domain/*."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

PR_DATABASE_URL = os.environ.get("PR_DATABASE_URL", "postgresql://minder:minder@db:5432/minder")

Base = declarative_base()

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(PR_DATABASE_URL, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def init_db() -> None:
    """create_all for whatever engine models are currently imported."""
    from engine.core import scope as _scope  # noqa: F401

    Base.metadata.create_all(get_engine(), checkfirst=True)


def reset_for_tests(engine: Engine) -> None:
    """Rebind the module-global engine/session to a test engine (see tests fixture)."""
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextlib.contextmanager
def db_session() -> Iterator[Session]:
    get_engine()
    assert _SessionLocal is not None
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
