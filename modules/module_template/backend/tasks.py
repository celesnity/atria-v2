"""The module_template background task. Runs in the Celery worker; updates the
DB, reverse-pushes a live progress block, and attaches a result artifact. Uses
the SDK's AtriaClient — never imports `atria`."""
from __future__ import annotations

import json
import logging
import time

from celery_app import celery_app
import db

logger = logging.getLogger("module_template.tasks")


def _client():
    """Build an AtriaClient from env (announce config); None if unconfigured."""
    from atria_module_sdk.announce import resolve_announce_config
    from atria_module_sdk.client import AtriaClient
    cfg = resolve_announce_config()
    return AtriaClient("module_template", cfg) if cfg is not None else None


@celery_app.task(name="module_template.run_job")
def run_job(job_id: int, session_id: str | None, steps: int) -> dict:
    steps = max(1, int(steps))
    with db.db_session() as s:
        job = s.get(db.MtJob, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        job.status = "running"; job.pct = 0

    client = _client() if session_id else None
    bid = None
    try:
        if client and session_id:
            bid = client.push_block(session_id, "./ShowcaseBlock", {"kind": "job", "pct": 0})
        for i in range(1, steps + 1):
            time.sleep(1)
            pct = int(i / steps * 100)
            with db.db_session() as s:
                job = s.get(db.MtJob, job_id)
                job.pct = pct; job.status = "running" if i < steps else "done"
            if client and session_id and bid:
                try:
                    client.update_block(session_id, bid, {"kind": "job", "pct": pct, "done": i == steps})
                except Exception as exc:  # noqa: BLE001 — reverse-push best-effort
                    logger.warning("run_job block update failed: %s", exc)
        with db.db_session() as s:
            job = s.get(db.MtJob, job_id)
            job.status = "done"; job.result_json = json.dumps({"steps": steps})
        if client and session_id:
            try:
                client.push_artifact(session_id, f"job_{job_id}_report.md",
                                     f"# Job {job_id}\n\ncompleted {steps} steps.\n".encode())
            except Exception as exc:  # noqa: BLE001
                logger.warning("run_job artifact push failed: %s", exc)
        return {"ok": True, "job_id": job_id}
    except Exception as exc:  # noqa: BLE001 — mark error, never crash the worker
        logger.exception("run_job failed")
        with db.db_session() as s:
            job = s.get(db.MtJob, job_id)
            if job:
                job.status = "error"; job.result_json = json.dumps({"error": str(exc)})
        return {"ok": False, "error": str(exc)}
