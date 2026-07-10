---
name: module_template
description: A runnable SDK showcase. Use it to demonstrate what an Atria service module can do — typed tools, generic cards, federated React blocks, streaming with live progress, auth-gated tools, background reverse-push, artifact export, Celery jobs, S3 media storage, and a read-only DB overlay. Ask it to "show the module SDK capabilities".
---

# module_template

A reference module that demonstrates every `atria_module_sdk` capability. Each tool
maps to one feature — use it to learn the SDK or as a copy-me skeleton for a new module.

## When to use

Reach for this when someone wants to see or verify what a deeply-connected Atria
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
- `template_db_overview` — return a read-only summary of key Atria tables (agents, sessions, modules) plus `mt_*` row counts. Use to inspect the shared database state for debugging or reporting.

## Dashboard panels

The module's dashboard (`http://localhost:9300/dashboard/`) exposes four panels:

- **Jobs** — live list of Celery tasks (queued / running / done / failed) with results.
- **Media** — browse, upload, and download files stored in the MinIO `module-template` bucket.
- **Data** — read-only overlay of Atria's core tables; useful for debugging and cross-module visibility.
- **Metrics** — counters for job throughput, error rate, and object storage usage.
