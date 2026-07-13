---
name: module_template
description: 'A runnable SDK showcase. Use it to demonstrate what an Minder service module can do — typed tools, generic cards, federated React blocks, streaming with live progress, auth-gated tools, background reverse-push, artifact export, Celery jobs, S3 media storage, a read-only DB overlay, AND the v3 agent surface: risk-gated actions, event envelopes, and a co-pilot that drives the real Products UI. Ask it to "show the module SDK capabilities" or "add a product".'
---

# module_template

A reference module that demonstrates every `minder_module_sdk` capability. Each tool
maps to one feature — use it to learn the SDK or as a copy-me skeleton for a new module.

## When to use

Reach for this when someone wants to see or verify what a deeply-connected Minder
module can do, or as the starting point for a new module.

## Tools

- `template_typed_query` — typed, validated params (pydantic `params_model`).
- `template_card` — a generic answer card.
- `template_block` — the module's own federated React block.
- `template_stream` — streaming tool: live progress + a mid-stream block.
- `template_secure` — an auth-gated tool (only runs for an authenticated user).
- `template_async_job` — a background job that pushes a live progress block into the chat.
- `template_export` — attaches a generated report as a conversation artifact.
- `template_start_job` — enqueue a Celery background task; returns a job ID. Use when the user asks to start a long-running job or process something asynchronously.
- `template_list_jobs` — list all background jobs and their current status/result. Use to check on queued or completed jobs.
- `template_db_overview` — return a read-only summary of key Minder tables (agents, sessions, modules) plus `mt_*` row counts. Use to inspect the shared database state for debugging or reporting.

## Agent surface demo — Products (v3)

The **Products** tab shows the agent-facing SDK: risk gate, event envelope, and a
UI co-pilot. Tools:

- `list_products` — a typed **read** (never gated). Use to see the catalog.
- `create_product` — **medium** risk; creates a product and emits a `product.created` event. Runs at the module's default autonomy.
- `restock_product` — **low** risk; adds stock.
- `delete_product` — **high** risk; **gated** below "high" autonomy, so it returns a *decision packet* for approval instead of deleting. To actually delete, the human approves (the Products panel's trash button posts a decision).
- `assist_add_product` — the **co-pilot**: opens the Add Product form in the UI, prefills the fields you pass, leaves blanks for the user (focuses `category`), and asks them to confirm. It does NOT create the product — the human confirms in the form, which runs `create_product`. Prefer this when the user says "add product …".

Try: *"list the products"*, *"add product ABC, a Widget, priced 12"* (→ co-pilot fills the form, you confirm), *"delete product 2"* (→ returns a decision packet needing approval).

## Dashboard panels

The module's dashboard (`http://localhost:9300/dashboard/`) exposes five panels:

- **Products** — CRUD catalog wired to the v3 agent surface; the Add Product form is agent-drivable (co-pilot fills it, you confirm).
- **Jobs** — live list of Celery tasks (queued / running / done / failed) with results.
- **Media** — browse, upload, and download files stored in the MinIO `module-template` bucket.
- **Data** — read-only overlay of Minder's core tables; useful for debugging and cross-module visibility.
- **Metrics** — counters for job throughput, error rate, and object storage usage.
