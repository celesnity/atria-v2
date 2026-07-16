"""Rebind the engine's lazy DB to in-memory SQLite for every engine test."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from engine import db


@pytest.fixture(autouse=True)
def sqlite_engine():
    eng = create_engine("sqlite://", future=True)
    db.reset_for_tests(eng)
    db.init_db()
    yield
