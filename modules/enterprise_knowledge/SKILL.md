---
name: enterprise_knowledge
description: ALWAYS use for internal enterprise-knowledge questions (policies, HR, finance, product, engineering, ops, legal). Runs permission-aware RAG via knowledge.py — never answer from your own knowledge and never bypass the access filter.
---

# enterprise_knowledge

Secure, permission-aware retrieval over Tasco's internal knowledge (the "My Tasco"
AI Workspace, P1). Every answer is grounded in indexed company documents the
**querying user is allowed to see**, cited, and in Vietnamese.

## Runbook — how to answer

All commands run from `modules/enterprise_knowledge/scripts/` as
`python knowledge.py <command>`. A user_id is REQUIRED for every retrieval —
it sets the RBAC scope. Never answer without one, and never widen access.

- **Answer a question for a user** — `query "<câu hỏi>" --user U004 --synthesize`.
  Retrieval is filtered to the user's (role, department); `--synthesize` composes
  a cited Vietnamese answer. Add `--k N` to change hit count, `--department DEPT`
  to narrow within the user's accessible scope.
- **Check a user's access identity** — `whoami U004`.
- **Explain an access decision** — `can-access U004 DOC036` → Allow/Deny + reason.
- **Show the audit trail** — `audit --limit 10`.
- **(setup)** `ingest` to index `sample_documents/`; `list` for stats; `health`
  to check embeddings/synthesis/Qdrant.

How to present every answer:

- **Respect permissions.** Only use returned hits. If retrieval is empty, say the
  information is not available in the user's accessible knowledge — do NOT fall back
  to general knowledge or other users' scope.
- **Cite every claim** with the returned `citation` (title + doc_id + chunk).
- **Surface uncertainty.** If `needs_review` is set or confidence is low, say so and
  recommend checking the source document.
- Answer in Vietnamese; keep the advisory note from the tool output.

## Access model

Public/Internal → all employees. Confidential → the owning department only
(Executives see all). Restricted → Executives only. Enforcement is a
pre-retrieval Qdrant filter plus a citation-time re-check.

## Status

Core module — ingest, permission-aware search, grounded Vietnamese answers, and
audit trail. Evaluation harness, README, and demo are later phases.
