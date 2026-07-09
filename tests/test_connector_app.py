"""Contract tests for the maintenance_copilot connector service.

These import the service module directly (not over HTTP) with the pipeline
mocked, so they run without qdrant/llm sidecars.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "modules/maintenance_copilot/backend"


def _load_service():
    """Import backend/service.py with its pipeline dir on sys.path."""
    sys.path.insert(0, str(BACKEND / "pipeline"))
    spec = importlib.util.spec_from_file_location("mc_service", BACKEND / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unavailable_payload_is_low_confidence_review_required():
    svc = _load_service()
    card = svc.unavailable_payload("why is the APU inop?", "qdrant")
    assert card["confidence"] == 0.0
    assert card["confidence_band"] == "low"
    assert card["review_required"] is True
    assert card["citations"] == []
    assert card["validation_warnings"] == ["service_unavailable:qdrant"]


def test_unavailable_suffix_names_service():
    svc = _load_service()
    assert "{service}" in svc.UNAVAILABLE_SUFFIX
    assert "Do NOT" in svc.UNAVAILABLE_SUFFIX
