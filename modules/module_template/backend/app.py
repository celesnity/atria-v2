"""module_template — a runnable showcase of the atria-module-sdk surface.

Each tool demonstrates exactly one SDK capability. Pure/fake logic; never imports
``atria``. Ask the agent to "show what the module SDK can do" and it will call these.
"""

from __future__ import annotations

import logging
import threading

from pydantic import BaseModel, Field

from atria_module_sdk import Connector, card
from atria_module_sdk.client import AtriaClientError

import service
import db
import media
import tasks

logger = logging.getLogger("module_template")

conn = Connector(
    "module_template",
    version="1",
    display_name="Module Template",
    public_base_env="MT_PUBLIC_BASE",
    dashboard_dist_env="MT_DASHBOARD_DIST",
    min_core_version="2",
)

conn.expose_block("./ShowcaseBlock")


def _block(props: dict) -> dict:
    """Federated block descriptor for this module's ShowcaseBlock component."""
    return conn.block("./ShowcaseBlock", props, title="module_template")


# --- 1. params_model: typed, validated parameters -------------------------------
class TemplateQuery(BaseModel):
    topic: str = Field(description="What to search the demo corpus for.")
    limit: int = Field(default=3, ge=1, le=5, description="Max results (1–5).")


@conn.tool(
    "template_typed_query",
    description="Demo: pydantic params_model — typed, schema-validated input.",
    params_model=TemplateQuery,
    card_type="template_card",
)
def template_typed_query(topic: str, limit: int = 3):
    res = service.search(topic, limit)
    return {
        "output": res,
        "card": card(
            f"Found {res['count']} results for {topic!r}.",
            card_type="template_card",
            confidence=0.9,
        ),
    }


# --- 2. card(): the generic card renderer --------------------------------------
@conn.tool(
    "template_card",
    description="Demo: return a generic card().",
    parameters={"type": "object", "properties": {"note": {"type": "string"}}},
)
def template_card(note: str = "hello from module_template"):
    return {
        "output": note,
        "card": card(
            note,
            card_type="template_card",
            confidence=0.7,
            validation_warnings=["this is a demo card"],
        ),
    }


# --- 3. conn.block(): a federated React block ----------------------------------
@conn.tool(
    "template_block",
    description="Demo: render the module's own federated React block.",
    parameters={"type": "object", "properties": {"topic": {"type": "string"}}},
)
def template_block(topic: str = "demo"):
    res = service.search(topic, 3)
    return {
        "output": f"Rendered a federated ShowcaseBlock for {topic!r}.",
        "blocks": [_block({"kind": "block", "topic": topic, "results": res["results"]})],
    }


# --- 4. streaming + mid-stream block event -------------------------------------
@conn.tool(
    "template_stream",
    streaming=True,
    description="Demo: a streaming tool — progress events, a mid-stream block, a final.",
    parameters={"type": "object", "properties": {"topic": {"type": "string"}}},
)
def template_stream(topic: str = "demo"):
    yield {"event": "progress", "message": "searching…", "pct": 30}
    res = service.search(topic, 3)
    yield {
        "event": "block",
        "block": _block({"kind": "stream", "topic": topic, "results": res["results"]}),
    }
    yield {"event": "progress", "message": "finishing…", "pct": 80}
    yield {"event": "final", "success": True, "output": f"streamed {res['count']} results"}


# --- 5. requires_auth: gate on an authenticated principal ----------------------
@conn.tool(
    "template_secure",
    requires_auth=True,
    description="Demo: requires_auth — only runs for an authenticated user.",
)
def template_secure(principal=None):
    who = getattr(principal, "username", "unknown")
    return {
        "output": f"authenticated call by {who}",
        "card": card(f"Secure action performed for {who}.", card_type="template_card"),
    }


# --- 6. reverse-push: an async job pushing a live progress block ---------------
@conn.tool(
    "template_async_job",
    description="Demo: start a background job that reverse-pushes a live progress block.",
    parameters={"type": "object", "properties": {"steps": {"type": "integer"}}},
)
def template_async_job(steps: int = 3, session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to push into"}

    def _run(sid: str, n: int) -> None:
        try:
            client = conn.atria_client()
        except AtriaClientError as exc:
            logger.warning("async job: atria client unavailable: %s", exc)
            return
        import time

        try:
            bid = client.push_block(sid, "./ShowcaseBlock", {"kind": "job", "pct": 0})
            for i in range(1, n + 1):
                time.sleep(1)
                client.update_block(
                    sid, bid, {"kind": "job", "pct": int(i / n * 100), "done": i == n}
                )
        except Exception as exc:  # noqa: BLE001 — isolated demo job; keep logs clean
            logger.warning("async job: reverse-push failed: %s", exc)

    threading.Thread(
        target=_run, args=(session_id, max(1, int(steps))), name="module_template-job", daemon=True
    ).start()
    return {"output": f"started a {steps}-step background job; watch the block update live."}


# --- 7. push_artifact: attach a report to the conversation ---------------------
@conn.tool(
    "template_export",
    description="Demo: push_artifact — attach a generated report to the conversation.",
    parameters={"type": "object", "properties": {"topic": {"type": "string"}}},
)
def template_export(topic: str = "demo", session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to attach an artifact to"}
    try:
        client = conn.atria_client()
        aid = client.push_artifact(
            session_id, f"template_report_{topic}.md", service.report_markdown(topic).encode()
        )
    except AtriaClientError as exc:
        return {"success": False, "output": f"export failed: {exc}"}
    return {"output": f"attached report artifact #{aid} to the conversation."}


# --- 8. job tools: start, list, db overview ------------------------------------
@conn.tool(
    "template_start_job",
    description="Start a background job (Celery). Watch a live progress block update.",
    parameters={"type": "object", "properties": {"steps": {"type": "integer"}}},
)
def template_start_job(steps: int = 3, session_id=None):
    with db.db_session() as s:
        job = db.MtJob(kind="demo", status="queued", pct=0)
        s.add(job)
        s.flush()
        job_id = job.id
    tasks.run_job.delay(job_id, session_id, int(steps))
    return {
        "output": f"started job #{job_id} ({steps} steps) — watch the block update live.",
        "card": card(f"Job #{job_id} queued.", card_type="template_card"),
    }


@conn.tool("template_list_jobs", description="List recent background jobs.")
def template_list_jobs():
    with db.db_session() as s:
        rows = [j.as_dict() for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(10)]
    return {"output": {"jobs": rows}}


@conn.tool(
    "template_db_overview",
    description="Module DB counts + read-only Atria aggregates (shared database).",
)
def template_db_overview():
    with db.db_session() as s:
        jobs = s.query(db.MtJob).count()
        mediac = s.query(db.MtMedia).count()
    return {
        "output": {
            "mt_jobs": jobs,
            "mt_media": mediac,
            "atria_conversations": db.list_conversations(5),
            "atria_artifacts_count": db.count_artifacts(),
        }
    }


# --- lifecycle & extra endpoints -----------------------------------------------
@conn.on_startup
def _init_infra() -> None:
    try:
        db.init_db()
        media.ensure_bucket()
        logger.info("module_template infra ready (db + bucket)")
    except Exception as exc:  # noqa: BLE001 — readiness reports not-ready if this fails
        logger.warning("infra init failed (will report not-ready): %s", exc)


@conn.readiness_probe
def _ready():
    checks = {"db": False, "redis": False, "s3": False, "celery": False}
    try:
        with db.engine.connect() as c:
            c.exec_driver_sql("SELECT 1")
            checks["db"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        import redis  # celery[redis] pulls this in

        redis.Redis.from_url(tasks.celery_app.conf.broker_url).ping()
        checks["redis"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        media.s3_client().head_bucket(Bucket=media.MT_S3_BUCKET)
        checks["s3"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        checks["celery"] = bool(tasks.celery_app.control.ping(timeout=1))
    except Exception:  # noqa: BLE001
        pass
    return {"ready": all(checks.values()), "detail": checks}


@conn.health_probe
def _health():
    return {"showcase": "ok"}


@conn.route("/jobs", methods=["GET"])
def route_jobs():
    with db.db_session() as s:
        return {
            "jobs": [j.as_dict() for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(50)]
        }


@conn.route("/jobs/start", methods=["POST"])
def route_jobs_start(body):
    """Start a demo Celery job from the dashboard (no chat session).

    Mirrors the ``template_start_job`` tool so the Jobs panel button can enqueue
    work directly. There is no conversation to reverse-push into, so the live block
    is skipped; the panel reflects progress by polling ``GET /jobs``.
    """
    steps = max(1, min(int((body or {}).get("steps", 3)), 20))
    with db.db_session() as s:
        job = db.MtJob(kind="demo", status="queued", pct=0)
        s.add(job)
        s.flush()
        job_id = job.id
    tasks.run_job.delay(job_id, None, steps)
    return {"job_id": job_id, "steps": steps, "status": "queued"}


@conn.route("/media", methods=["GET"])
def route_media():
    with db.db_session() as s:
        rows = [m.as_dict() for m in s.query(db.MtMedia).order_by(db.MtMedia.id.desc()).limit(50)]
    for r in rows:
        r["url"] = media.presigned_url(r["s3_key"])
    return {"media": rows}


@conn.route("/media/upload", methods=["POST"])
def route_media_upload(body):
    # body carries {"filename", "content_b64", "content_type"} (dashboard posts JSON;
    # the SDK route handler receives the parsed JSON body).
    import base64
    from fastapi import HTTPException

    if not body.get("filename"):
        raise HTTPException(400, "filename required")
    data = base64.b64decode(body.get("content_b64", ""))
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 25MB)")
    return media.put_media(
        body["filename"], data, body.get("content_type", "application/octet-stream")
    )


@conn.route("/overview", methods=["GET"])
def route_overview():
    with db.db_session() as s:
        return {
            "mt_jobs": s.query(db.MtJob).count(),
            "mt_media": s.query(db.MtMedia).count(),
            "atria_conversations": db.list_conversations(10),
            "atria_artifacts_count": db.count_artifacts(),
            "atria_recent_artifacts": db.recent_artifacts(10),
        }


@conn.route("/metrics", methods=["GET"])
def route_metrics():
    with db.db_session() as s:
        by_status: dict = {}
        for (st,) in s.query(db.MtJob.status).all():
            by_status[st] = by_status.get(st, 0) + 1
        total_bytes = sum(m.size for m in s.query(db.MtMedia).all())
    return {"jobs_by_status": by_status, "media_total_bytes": total_bytes}


@conn.route("/ping", methods=["GET"])
def ping(principal):
    return {"pong": principal.username}


app = conn.asgi()
