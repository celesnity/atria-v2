"""Connector bootstraps and exposes a manifest with the produce name."""

from __future__ import annotations

import pytest

pytest.importorskip("minder_python_sdk")


def test_connector_identity():
    from agent.connector import conn

    assert conn.name == "produce"
    assert conn.default_autonomy == "medium"
