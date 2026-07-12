"""SQLite engine/session factory for the ai_workspace module (SQLAlchemy 2.0 sync).

Self-contained: a single SQLite file under the module's ``data/`` directory,
never the core app's PostgreSQL. Path is overridable via ``AIW_DB_PATH`` so
tests can point at a temp file.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def default_db_path() -> str:
    """Return ``AIW_DB_PATH`` if set, else ``<module>/data/ai_workspace.db``."""
    override = os.environ.get("AIW_DB_PATH")
    if override:
        return override
    return str(Path(__file__).resolve().parent.parent / "data" / "ai_workspace.db")


_engines: dict[str, Engine] = {}


def get_engine(path: str | None = None) -> Engine:
    """Return (and cache) a SQLite engine for ``path``."""
    target = path or default_db_path()
    if target not in _engines:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        _engines[target] = create_engine(f"sqlite:///{target}", future=True)
    return _engines[target]


def get_sessionmaker(path: str | None = None) -> sessionmaker:
    """Return a sessionmaker bound to the engine for ``path``."""
    return sessionmaker(bind=get_engine(path), future=True, expire_on_commit=False)


@contextmanager
def session_scope(path: str | None = None) -> Iterator[Session]:
    """Transactional session scope: commit on success, rollback on error."""
    session = get_sessionmaker(path)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(path: str | None = None) -> None:
    """Create all tables (ORM-first, no migrations — mirrors the core app)."""
    from models import Base  # local import; scripts dir is on sys.path

    Base.metadata.create_all(get_engine(path))


def reset_db(path: str | None = None) -> None:
    """Drop and recreate all tables (used by the idempotent seeder)."""
    from models import Base

    engine = get_engine(path)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
