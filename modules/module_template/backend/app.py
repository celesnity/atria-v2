"""module_template — a runnable showcase of the minder-python-sdk surface.

Each tool demonstrates exactly one SDK capability. Pure/fake logic; never imports
``minder``. Ask the agent to "show what the module SDK can do" and it will call these.
"""

from __future__ import annotations

import logging
import threading

from pydantic import BaseModel, Field

from minder_python_sdk import (
    Connector,
    ToolError,
    card,
    fill,
    focus,
    navigate,
    request_confirm,
)
from minder_python_sdk.client import MinderClientError

import service
import db
import media
import tasks
import products

logger = logging.getLogger("module_template")

conn = Connector(
    "module_template",
    version="1",
    display_name="Module Template",
    public_base_env="MT_PUBLIC_BASE",
    dashboard_dist_env="MT_DASHBOARD_DIST",
    min_core_version="2",
    # Demo the safety gate out of the box: high/critical actions need approval
    # unless Minder core raises the caller's autonomy above "medium".
    default_autonomy="medium",
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
    when_to_use="When you need to search the demo corpus with typed, validated params "
    "(topic string + bounded limit).",
    examples=[{"topic": "pumps", "limit": 3}, {"topic": "valves", "limit": 1}],
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
    when_to_use="When you want to surface a short freeform message to the user as a "
    "rendered card rather than plain text.",
    examples=[{"note": "inventory looks healthy"}, {}],
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
    when_to_use="When results are best shown in the module's rich federated React "
    "block instead of as text or a card.",
    examples=[{"topic": "demo"}, {"topic": "gaskets"}],
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
    when_to_use="When a search takes noticeable time and you want to stream progress "
    "and a mid-stream block to the user before the final result.",
    examples=[{"topic": "demo"}, {"topic": "bearings"}],
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
    when_to_use="When an action must be attributed to a signed-in principal; it fails "
    "for anonymous callers.",
    examples=[{}],
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
    when_to_use="When you want to demo a long-running job that reverse-pushes a live, "
    "self-updating progress block into the current session.",
    examples=[{"steps": 3}, {"steps": 5}],
)
def template_async_job(steps: int = 3, session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to push into"}

    def _run(sid: str, n: int) -> None:
        try:
            client = conn.minder_client()
        except MinderClientError as exc:
            logger.warning("async job: minder client unavailable: %s", exc)
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
    when_to_use="When the user wants a generated report saved as a downloadable "
    "artifact attached to the conversation, not just shown inline.",
    examples=[{"topic": "demo"}, {"topic": "quarterly"}],
)
def template_export(topic: str = "demo", session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to attach an artifact to"}
    try:
        client = conn.minder_client()
        aid = client.push_artifact(
            session_id, f"template_report_{topic}.md", service.report_markdown(topic).encode()
        )
    except MinderClientError as exc:
        return {"success": False, "output": f"export failed: {exc}"}
    return {"output": f"attached report artifact #{aid} to the conversation."}


# --- 8. job tools: start, list, db overview ------------------------------------
@conn.tool(
    "template_start_job",
    description="Start a background job (Celery). Watch a live progress block update.",
    parameters={"type": "object", "properties": {"steps": {"type": "integer"}}},
    when_to_use="When the user asks to kick off real background work (a Celery job) and "
    "track it via a live progress block.",
    examples=[{"steps": 3}, {"steps": 10}],
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


@conn.tool(
    "template_list_jobs",
    description="List recent background jobs.",
    when_to_use="When the user asks what jobs are running, queued, or recently finished.",
    examples=[{}],
)
def template_list_jobs():
    with db.db_session() as s:
        rows = [j.as_dict() for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(10)]
    return {"output": {"jobs": rows}}


@conn.tool(
    "template_db_overview",
    description="Module DB counts + read-only Minder aggregates (shared database).",
    when_to_use="When the user wants a high-level snapshot of module data (job/media "
    "counts) plus read-only Minder aggregates.",
    examples=[{}],
)
def template_db_overview():
    with db.db_session() as s:
        jobs = s.query(db.MtJob).count()
        mediac = s.query(db.MtMedia).count()
    return {
        "output": {
            "mt_jobs": jobs,
            "mt_media": mediac,
            "minder_conversations": db.list_conversations(5),
            "minder_artifacts_count": db.count_artifacts(),
        }
    }


# --- 9. AGENT SURFACE DEMO: products catalog (risk gate + events + UI driving) --
# The Products tab is a small CRUD surface wired to the v3 agent-facing SDK:
#   • create_product  — medium risk, runs; emits a product.created event
#   • delete_product  — high risk, GATED below "high" autonomy → decision packet
#   • restock_product — low risk
#   • list_products   — a typed read (never gated)
#   • assist_add_product — co-pilot: drives the REAL Add Product form via UI intents
# Declare every dashboard screen so the auto ``<module>_navigate`` tool can move
# the user between them (ids match the frontend TABS in dashboard.tabs.ts).
conn.page("products", path="/products", label="Products",
          description="Product catalog — add, restock, delete.")
conn.page("jobs", path="/jobs", label="Jobs",
          description="Background jobs and their status.")
conn.page("media", path="/media", label="Media",
          description="Uploaded media assets.")
conn.page("data", path="/data", label="Data",
          description="Raw data tables and records.")
conn.page("metrics", path="/metrics", label="Metrics",
          description="Dashboard metrics and charts.")
conn.page("graph", path="/graph", label="Graph",
          description="Operational Graph — products linked to their categories.")
conn.form(
    "add_product",
    route="products",
    fields=[
        {"name": "sku", "type": "string", "label": "SKU", "required": True},
        {"name": "name", "type": "string", "label": "Name", "required": True},
        {"name": "price", "type": "number", "label": "Price", "required": True},
        {"name": "category", "type": "enum", "label": "Category",
         "options": ["A", "B", "C"], "required": False},
    ],
    submit_tool="create_product",
    risk="medium",
    reversible=True,
    undo="delete_product(product_id) removes the product this form created",
    instructions="Fill sku, name, price. Category is optional. Ask the user to "
    "confirm before submitting.",
)


# --- Declarative agent context (mirror of the frontend Agent.* layer) ---
@conn.context.state("inventory", "Live catalog summary: total products and low stock")
def inventory_state(principal=None):
    items = products.list_products()
    return {"total": len(items), "skus": [p["sku"] for p in items][:20]}


@conn.context.state("jobs", "Live background-job summary")
def jobs_state(principal=None):
    """Summarize recent background jobs for the agent's live context.

    Reads the most recent ``MtJob`` rows via the same accessor ``template_list_jobs``
    uses. Defensive by design: any DB failure yields an empty, well-formed summary.

    Returns:
        A dict ``{"recent": [...], "count": N}`` where ``recent`` holds up to five
        recent job dicts and ``count`` is how many were read.
    """
    try:
        with db.db_session() as s:
            rows = [
                j.as_dict()
                for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(5)
            ]
        return {"recent": rows, "count": len(rows)}
    except Exception:  # noqa: BLE001 — showcase fallback; SDK is already fail-closed
        return {"recent": [], "count": 0}


conn.context.knowledge(
    "Confirm SKU and price with the user before creating a product; SKUs are unique."
)
conn.context.knowledge(
    "Deleting a product is irreversible and high-risk; it is gated below 'high' "
    "autonomy and requires explicit human approval before it runs."
)
conn.context.note("products", "Product catalog area — add, restock, and delete products.")
conn.context.note("jobs", "Background jobs and their status.")
conn.context.note("media", "Uploaded media assets.")
conn.context.note("data", "Raw data tables and records.")
conn.context.note("metrics", "Dashboard metrics and charts.")
conn.context.note("graph", "Operational Graph — products linked to their categories.")


# --- BE-SDK-10: Operational Graph — linked context around a node ---------------
@conn.graph
def product_graph(node=None, depth: int = 1):
    """Answer a linked-context query over the catalog. Ask for a product or
    category node (e.g. ``product:1`` / ``category:A``) to get its neighbourhood,
    or omit ``node`` for the whole graph."""
    return products.graph(node, depth)


conn.event(
    "product.created",
    description="Emitted when a product is added to the catalog.",
    schema={"type": "object", "properties": {"product": {"type": "object"}}},
)


@conn.read("list_products", description="List every product in the catalog (typed read).")
def list_products():
    return {"output": {"products": products.list_products()}}


@conn.tool(
    "create_product",
    risk="medium",
    reversible=True,
    undo="delete_product(product_id) — removes the product just created",
    description="Create a product. This is the Add Product form's submit action.",
    parameters={
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "name": {"type": "string"},
            "price": {"type": "number"},
            "category": {"type": "string"},
        },
        "required": ["sku", "name", "price"],
    },
    card_type="template_card",
    when_to_use="When the user asks to add a new product and has provided SKU and price.",
    examples=[{"sku": "A-1", "name": "Pump", "price": 9.9, "category": "A"}],
)
def create_product(sku: str, name: str, price: float, category: str = "", session_id=None, **kw):
    if not sku or not name:
        raise ToolError("missing_fields", "sku and name are required", retryable=False)
    p = products.create(sku, name, price, category)
    conn.emit_event("product.created", {"product": p}, session_id=session_id)
    return {
        "output": f"created product #{p['id']} ({sku})",
        "card": card(
            f"Created {name} ({sku}) at ${p['price']:.2f}.",
            card_type="template_card",
            confidence=0.95,
        ),
    }


@conn.tool(
    "restock_product",
    risk="low",
    description="Add stock to a product.",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "integer"}, "qty": {"type": "integer"}},
        "required": ["product_id"],
    },
    when_to_use="When the user wants to add units to an existing product's stock.",
    examples=[{"product_id": 1, "qty": 10}, {"product_id": 2}],
)
def restock_product(product_id: int, qty: int = 10, **kw):
    p = products.restock(int(product_id), int(qty))
    if p is None:
        raise ToolError("not_found", f"no product #{product_id}", retryable=False)
    return {"output": f"restocked #{product_id} → {p['stock']} in stock"}


@conn.tool(
    "delete_product",
    risk="high",
    reversible=False,
    idempotent=True,
    description="Delete a product. HIGH risk — gated below 'high' autonomy, so it "
    "returns a decision packet for approval instead of deleting.",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "integer"}},
        "required": ["product_id"],
    },
    when_to_use="Only when the user explicitly asks to permanently remove a product — "
    "HIGH risk and irreversible, so it is gated below 'high' autonomy and returns a "
    "decision packet for human approval instead of deleting outright.",
    examples=[{"product_id": 1}],
)
def delete_product(product_id: int, **kw):
    p = products.delete(int(product_id))
    if p is None:
        raise ToolError("not_found", f"no product #{product_id}", retryable=False)
    return {"output": f"deleted product #{product_id} ({p['sku']})"}


@conn.tool(
    "assist_add_product",
    risk="low",
    description="Co-pilot: open the Add Product form in the UI, prefill what you "
    "know, leave blanks for the user, and ask them to confirm. Does NOT create the "
    "product itself — the human confirms in the form.",
    parameters={
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "name": {"type": "string"},
            "price": {"type": "number"},
            "category": {"type": "string"},
        },
        "required": ["sku", "name"],
    },
    when_to_use="When the user wants help filling in the Add Product form — prefill what "
    "you know and let the human confirm; use create_product only for direct creation.",
    examples=[
        {"sku": "A-1", "name": "Pump"},
        {"sku": "B-2", "name": "Valve", "price": 12.5, "category": "B"},
    ],
)
def assist_add_product(sku, name, price=None, category=None, session_id=None, **kw):
    values: dict = {"sku": sku, "name": name}
    if price is not None:
        values["price"] = price
    if category:
        values["category"] = category
    # Push to the demo session "default" (the mounted dashboard subscribes there)
    # and to the chat session if one was provided.
    for sid in {"default", session_id} - {None}:
        conn.push_ui_intent(sid, navigate("products"))
        conn.push_ui_intent(sid, fill("add_product", values, partial=True))
        if not category:
            conn.push_ui_intent(sid, focus("category", form="add_product"))
        conn.push_ui_intent(
            sid, request_confirm("add_product", summary=f"Create product {name} ({sku})?")
        )
    return {
        "output": f"Opened the Add Product form and prefilled {sku!r}; asked the user "
        "to review the blanks and confirm."
    }


@conn.tool(
    "duplicate_product",
    risk="low",
    description="Duplicate a product (new SKU suffixed -COPY).",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "integer"}},
        "required": ["product_id"],
    },
    when_to_use="When the user wants a copy of an existing product as a starting point "
    "for a variant (the copy gets a '-COPY' SKU suffix).",
    examples=[{"product_id": 1}],
)
def duplicate_product(product_id: int, session_id=None, **kw):
    src = products.get(int(product_id))
    if src is None:
        raise ToolError("not_found", f"no product #{product_id}", retryable=False)
    p = products.create(f"{src['sku']}-COPY", src["name"], src["price"], src["category"], src["stock"])
    conn.emit_event("product.created", {"product": p}, session_id=session_id)
    return {"output": f"duplicated #{product_id} → #{p['id']} ({p['sku']})"}


@conn.tool(
    "update_price",
    risk="medium",
    reversible=True,
    undo="update_price(product_id, <previous price>) — set the price back",
    description="Change a product's price.",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "integer"}, "price": {"type": "number"}},
        "required": ["product_id", "price"],
    },
    when_to_use="When the user wants to change an existing product's price; reversible "
    "by setting the price back.",
    examples=[{"product_id": 1, "price": 19.99}],
)
def update_price(product_id: int, price: float, **kw):
    p = products.set_price(int(product_id), price)
    if p is None:
        raise ToolError("not_found", f"no product #{product_id}", retryable=False)
    return {"output": f"set #{product_id} price → ${p['price']:.2f}"}


@conn.route("/products", methods=["GET"])
def route_products():
    return {"products": products.list_products()}


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
            "minder_conversations": db.list_conversations(10),
            "minder_artifacts_count": db.count_artifacts(),
            "minder_recent_artifacts": db.recent_artifacts(10),
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
