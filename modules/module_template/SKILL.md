---
name: module_template
description: A runnable SDK showcase. Use it to demonstrate what an Atria service module can do — typed tools, generic cards, federated React blocks, streaming with live progress, auth-gated tools, background reverse-push, and artifact export. Ask it to "show the module SDK capabilities".
---

# module_template

A reference module that demonstrates every `atria_module_sdk` capability. Each tool
maps to one feature — use it to learn the SDK or as a copy-me skeleton for a new module.

## When to use

Reach for this when someone wants to see or verify what a deeply-connected Atria
module can do, or as the starting point for a new module.

- `template_typed_query` — typed, validated params (pydantic `params_model`).
- `template_card` — a generic answer card.
- `template_block` — the module's own federated React block.
- `template_stream` — streaming tool: live progress + a mid-stream block.
- `template_secure` — an auth-gated tool (only runs for an authenticated user).
- `template_async_job` — a background job that pushes a live progress block into the chat.
- `template_export` — attaches a generated report as a conversation artifact.

The dashboard lists the tools and pings the connector.
