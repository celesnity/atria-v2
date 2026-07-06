---
name: enterprise_knowledge
description: ALWAYS use for internal enterprise-knowledge questions (policies, HR, finance, product, engineering, ops, legal). Runs permission-aware RAG via knowledge.py — never answer from your own knowledge and never bypass the access filter.
---

# enterprise_knowledge

Secure, permission-aware retrieval over Tasco's internal knowledge (the "My Tasco"
AI Workspace, P1). Every answer is grounded in indexed company documents the
**querying user is allowed to see**, cited, and in Vietnamese.

## When to use

Reach for this module for any internal enterprise-knowledge question — company
policy, HR, finance, product, engineering, operations, or legal. Always retrieve
through `knowledge.py` first. Never answer such questions from your own knowledge,
and never read or grep the corpus files directly: that bypasses the access filter,
the citations, and the audit trail. Every retrieval needs a `user_id` — it sets
the RBAC scope.

## Runbook — how to answer

All commands run from `modules/enterprise_knowledge/scripts/` as
`python knowledge.py <command>`. A user_id is REQUIRED for every retrieval —
it sets the RBAC scope. Never answer without one, and never widen access.
Questions and answers are in Vietnamese (the corpus is Vietnamese).

- **Answer a question for a user** — `query "<câu hỏi>" --user U004 --synthesize`.
  Retrieval is filtered to the user's (role, department); `--synthesize` composes
  a cited Vietnamese answer. Add `--k N` to change hit count, `--department DEPT`
  to narrow within the user's accessible scope.
- **Check a user's access identity** — `whoami U004`.
- **Explain an access decision** — `can-access U004 DOC036` → Allow/Deny + reason.
- **Show the audit trail** — `audit --limit 10`.
- **(setup)** `ingest` to index `sample_documents/`; `list` for stats; `health`
  to check embeddings / synthesis / Qdrant / Neo4j.

If retrieval comes back empty or erroring and a backing service may be down, run
`health` and report which of embeddings / synthesis / Qdrant / Neo4j failed —
do not guess an answer.

## Guardrails (non-negotiable)

- **Respect permissions.** Use only the returned hits, scoped to the given
  user_id. If retrieval is empty, say the information is not in the user's
  accessible knowledge — never fall back to general knowledge or to another user's
  scope, and never widen access.
- **Cite every claim** with the returned `citation` (title + doc_id + chunk). No
  unsourced claims about company knowledge.
- **Surface uncertainty.** If `needs_review` is set or confidence is low, say so
  and recommend checking the source document.
- **Answer in Vietnamese** and keep the advisory note from the tool output.

## Access model

Public/Internal → all employees. Confidential → the owning department only
(Executives see all). Restricted → Executives only. Enforcement is a
pre-retrieval Qdrant filter plus a citation-time re-check.

## GraphRAG (optional)

For richer answers, retrieval can be augmented with a knowledge graph. Build it
once, then pass `--graph` on a query:

- `python knowledge.py graph build` — build the metadata + tag backbone (no LLM).
  Add `--extract` to also run the LLM entity/relation pass (cached; needs
  `EK_KG_EXTRACT_*` and is slower on free tiers).
- `python knowledge.py query "<Q>" --user U004 --graph --synthesize` — expand
  retrieval with the graph. Access control is identical to the vector path: every
  graph-surfaced passage is re-checked with the same permission rules, so
  `--graph` never widens what a user can see. If the graph is unavailable, the
  query silently falls back to vector-only.

`--graph` only takes effect when the master switch `EK_GRAPH_ENABLED=1` is set
(default off → vector-only). Inspect the graph with `graph stats`.

## Status

Core module — permission-aware ingest and search, grounded Vietnamese answers, an
audit trail, an offline evaluation harness (`evaluate.py` over
`access/public_evaluation.csv`: ACL correctness + expected-document recall), and
an optional knowledge-graph augmentation (`graph build` + `query --graph`).
README and demo are later phases.
