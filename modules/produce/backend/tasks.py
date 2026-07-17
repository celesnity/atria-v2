"""Produce Celery tasks (Track A). Periodic OEE snapshotting — pure roll-up over
the module's own data; never imports minder."""

from __future__ import annotations

from celery_app import celery_app
from domain.oee import service as oee_service


@celery_app.task(name="produce.oee_snapshot")
def oee_snapshot(shift_id: int, total_count: int) -> dict:
    """Compute and return the current OEE snapshot for a shift (P-OEE-03 backend)."""
    return oee_service.shift_oee(shift_id, total_count)
