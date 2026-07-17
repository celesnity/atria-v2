"""Produce data layer. Reuses the shared `minder` Postgres INSTANCE but owns
only the ``pr_*`` tables. Track A — never imports `minder`, never writes Minder tables."""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("produce.db")

PR_DATABASE_URL = os.environ.get("PR_DATABASE_URL", "postgresql://minder:minder@db:5432/minder")

Base = declarative_base()

# Lazy engine — created on first use so importing this module (and the skeleton
# smoke tests) does not require the DB driver to be installed.
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
    """Create ONLY the module's own pr_* tables (checkfirst). Never touches Minder tables."""
    # Import epic models so they register on Base.metadata before create_all.
    from domain.config import models as _config  # noqa: F401
    from domain.work import models as _work  # noqa: F401
    from domain.wip import models as _wip  # noqa: F401
    from domain.downtime import models as _downtime  # noqa: F401
    from domain.scrap import models as _scrap  # noqa: F401
    from domain.oee import models as _oee  # noqa: F401
    from domain.handover import models as _handover  # noqa: F401
    from domain.sop import models as _sop  # noqa: F401
    from domain.exception import models as _exception  # noqa: F401
    from domain.setup import models as _setup  # noqa: F401
    Base.metadata.create_all(get_engine(), checkfirst=True)


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
