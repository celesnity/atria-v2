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


@conn.tool("template_typed_query",
           description="Demo: pydantic params_model — typed, schema-validated input.",
           params_model=TemplateQuery, card_type="template_card")
def template_typed_query(topic: str, limit: int = 3):
    res = service.search(topic, limit)
    return {"output": res, "card": card(f"Found {res['count']} results for {topic!r}.",
                                        card_type="template_card", confidence=0.9)}


# --- 2. card(): the generic card renderer --------------------------------------
@conn.tool("template_card", description="Demo: return a generic card().",
           parameters={"type": "object", "properties": {"note": {"type": "string"}}})
def template_card(note: str = "hello from module_template"):
    return {"output": note,
            "card": card(note, card_type="template_card", confidence=0.7,
                         validation_warnings=["this is a demo card"])}


# --- 3. conn.block(): a federated React block ----------------------------------
@conn.tool("template_block", description="Demo: render the module's own federated React block.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_block(topic: str = "demo"):
    res = service.search(topic, 3)
    return {"output": f"Rendered a federated ShowcaseBlock for {topic!r}.",
            "blocks": [_block({"kind": "block", "topic": topic, "results": res["results"]})]}


# --- 4. streaming + mid-stream block event -------------------------------------
@conn.tool("template_stream", streaming=True,
           description="Demo: a streaming tool — progress events, a mid-stream block, a final.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_stream(topic: str = "demo"):
    yield {"event": "progress", "message": "searching…", "pct": 30}
    res = service.search(topic, 3)
    yield {"event": "block", "block": _block({"kind": "stream", "topic": topic,
                                              "results": res["results"]})}
    yield {"event": "progress", "message": "finishing…", "pct": 80}
    yield {"event": "final", "success": True, "output": f"streamed {res['count']} results"}


# --- 5. requires_auth: gate on an authenticated principal ----------------------
@conn.tool("template_secure", requires_auth=True,
           description="Demo: requires_auth — only runs for an authenticated user.")
def template_secure(principal=None):
    who = getattr(principal, "username", "unknown")
    return {"output": f"authenticated call by {who}",
            "card": card(f"Secure action performed for {who}.", card_type="template_card")}


# --- 6. reverse-push: an async job pushing a live progress block ---------------
@conn.tool("template_async_job",
           description="Demo: start a background job that reverse-pushes a live progress block.",
           parameters={"type": "object", "properties": {"steps": {"type": "integer"}}})
def template_async_job(steps: int = 3, session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to push into"}

    def _run(sid: str, n: int) -> None:
        try:
            client = conn.atria_client()
        except AtriaClientError as exc:
            logger.warning("async job: atria client unavailable: %s", exc)
            return
        bid = client.push_block(sid, "./ShowcaseBlock", {"kind": "job", "pct": 0})
        for i in range(1, n + 1):
            import time
            time.sleep(1)
            client.update_block(sid, bid, {"kind": "job", "pct": int(i / n * 100),
                                           "done": i == n})

    threading.Thread(target=_run, args=(session_id, max(1, int(steps))),
                     name="module_template-job", daemon=True).start()
    return {"output": f"started a {steps}-step background job; watch the block update live."}


# --- 7. push_artifact: attach a report to the conversation ---------------------
@conn.tool("template_export",
           description="Demo: push_artifact — attach a generated report to the conversation.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_export(topic: str = "demo", session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to attach an artifact to"}
    try:
        client = conn.atria_client()
        aid = client.push_artifact(session_id, f"template_report_{topic}.md",
                                   service.report_markdown(topic).encode())
    except AtriaClientError as exc:
        return {"success": False, "output": f"export failed: {exc}"}
    return {"output": f"attached report artifact #{aid} to the conversation."}


# --- lifecycle & extra endpoint ------------------------------------------------
@conn.readiness_probe
def _ready():
    return {"ready": service.is_warm(), "detail": "warming up" if not service.is_warm() else "ready"}


@conn.health_probe
def _health():
    return {"showcase": "ok"}


@conn.on_startup
def _warm_up():
    logger.info("module_template starting — warming up…")
    service.warm_up()
    logger.info("module_template warm and ready.")


@conn.route("/ping", methods=["GET"])
def ping(principal):
    return {"pong": principal.username}


app = conn.asgi()
