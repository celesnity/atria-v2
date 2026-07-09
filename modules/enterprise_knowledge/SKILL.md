---
name: enterprise_knowledge
description: ALWAYS use for internal enterprise-knowledge questions (policies, HR, finance, product, engineering, ops, legal). Runs permission-aware RAG via knowledge.py — never answer from your own knowledge and never bypass the access filter.
tools: agent_tools.py
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

**To answer a user's question, call the `enterprise_knowledge_query` tool**
(unless the user explicitly asks for grep mode — see the Grep mode section).
Pass `user_id` (REQUIRED — sets the RBAC scope) and `question` (Vietnamese);
optionally `synthesize` (default true), `k`, `department`, `mode`. It returns
cited, permission-filtered hits — answer only from those, keep the citations,
and never widen access. This is a typed tool: do NOT hand-compose a shell
command for it.

The **other** operations (identity, access checks, audit, setup) use the CLI.
Run it with the script's **absolute** path — your tool CWD is the chat
workspace, NOT the repo, so a bare `knowledge.py` or any path missing `scripts/`
fails. The script is at
`<modules-root>/enterprise_knowledge/scripts/knowledge.py` (here
`/app/modules/enterprise_knowledge/scripts/knowledge.py`). Questions and answers
are in Vietnamese (the corpus is Vietnamese).

- **Answer a question for a user** — use the `enterprise_knowledge_query` tool
  (above). Equivalent CLI for manual/debug use: `query "<câu hỏi>" --user U004
  --synthesize` (the question is the first positional arg; the flag is `--user`,
  not `--user_id`). Add `--k N`, `--department DEPT`, or `--mode
  {dense|bm25|hybrid}` (default `hybrid` = dense + BM25 fused). On first deploy
  run `ingest` once to populate BM25 vectors; after a schema change (an old
  pre-hybrid index) run `reset` then `ingest` — `ingest` alone cannot convert an
  old collection.
- **Check a user's access identity** — `whoami U004`.
- **Explain an access decision** — `can-access U004 DOC036` → Allow/Deny + reason.
- **Show the audit trail** — `audit --limit 10`.
- **(setup)** `ingest` to index `sample_documents/`; `list` for stats; `health`
  to check embeddings / synthesis / Qdrant / Neo4j.

If retrieval comes back empty or erroring and a backing service may be down, run
`health` and report which of embeddings / synthesis / Qdrant / Neo4j failed —
do not guess an answer.

## Grep mode (experimental)

An alternative answering path used **only when the user explicitly asks for
it** (e.g. "grep mode", "dùng grep", "trả lời bằng grep"). Every other
enterprise-knowledge question uses the `enterprise_knowledge_query` tool.

**When grep mode is requested, you MUST answer with the `search` and
`read_file` tools over the corpus files — do NOT call
`enterprise_knowledge_query` and do NOT run `knowledge.py query`.** Those are the
vector path; using them defeats the whole purpose (the point is to compare grep
against the vector path). The give-away that you did it wrong: chunk citations
like `DOC001#1` — those come only from the vector index. Grep mode cites the
documents you actually read (doc_id + title, optionally the file). A `user_id`
is still REQUIRED. This mode has no hard access enforcement and no audit trail.
State "chế độ grep (thử nghiệm)" in the answer so it is never mistaken for the
enforced path.

Runbook:

1. **Identity** — run `python <modules-root>/enterprise_knowledge/scripts/knowledge.py
   whoami <user_id>` (absolute path — see the Runbook note on CWD) to get the
   user's role and department. `whoami` takes the user_id as a positional arg.
2. **Search** — use the `search` tool over the module's `sample_documents/`
   folder. Pass its **absolute** path as `path` — the same absolute
   modules-root path you use to run the scripts. Your tool CWD is the chat
   workspace, NOT the repo, so a repo-relative path like
   `modules/enterprise_knowledge/sample_documents` will not resolve and returns
   zero hits. For example, if the scripts are at
   `<modules-root>/enterprise_knowledge/scripts/`, search
   `<modules-root>/enterprise_knowledge/sample_documents`. Set
   `case_insensitive=true` and `output_mode="files_with_matches"`. Pick 2–4
   distinctive Vietnamese keywords from the question and write full diacritics
   (ripgrep matches bytes: "bao hiem" will not match "bảo hiểm"). If there are
   zero hits, retry once with a synonym or a single broader keyword before
   concluding the information is absent.
3. **Read** — `read_file` the top candidate documents by their **absolute**
   paths (the `search` hits already come back absolute; open only the few most
   relevant files).
4. **Soft ACL check (before using any content)** — read each document's YAML
   frontmatter (`classification`, `department`) and discard every document the
   user may not see, per the access rules below.
5. **Answer** — in Vietnamese, citing `doc_id` + `title` for every claim, and
   note that grep mode (experimental) produced it.

Soft ACL rules (prompt-level mirror of the enforced access model):

- `Public` / `Internal` — visible to all employees.
- `Confidential` — visible only to users whose department matches the
  document's `department` (Executives see everything).
- `Restricted` — Executives only.

If every matching document is discarded by the ACL check, or nothing matches
after the retry, reply that the information is not in the user's accessible
knowledge — the same refusal as the vector path. Never fall back to general
knowledge and never widen scope. If the `search` tool is denied or errors,
report the tool failure and fall back to the normal `knowledge.py` path.

## Guardrails (non-negotiable)

- **Respect permissions.** Use only content scoped to the given user_id — the
  hits returned by `knowledge.py`, or in grep mode the documents that pass the
  soft ACL check. Never read or grep the corpus outside grep mode. If nothing
  is accessible, say the information is not in the user's accessible knowledge —
  never fall back to general knowledge or to another user's scope, and never
  widen access.
- **Cite every claim** with the returned `citation` (title + doc_id + chunk). No
  unsourced claims about company knowledge.
- **Surface uncertainty.** If `needs_review` is set or confidence is low, say so
  and recommend checking the source document.
- **Answer in Vietnamese** and keep the advisory note from the tool output.
- **Answer in this turn — never dispatch.** Run `knowledge.py` directly via bash and
  answer from the JSON it prints. Never route a knowledge question through the `solve`
  tool (divide/parallel): a dispatch notification is not an answer. If a job was
  dispatched anyway, call `get_solve_result(job_id, block=true)` and answer from its
  output.

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
(default off → vector-only). On the dashboard, the "Đồ thị tri thức" checkbox
(default on) adds `--graph`. Inspect the graph with `graph stats`.

## Status

Core module — permission-aware ingest and search, grounded Vietnamese answers, an
audit trail, an offline evaluation harness (`evaluate.py` over
`access/public_evaluation.csv`: ACL correctness + expected-document recall), and
an optional knowledge-graph augmentation (`graph build` + `query --graph`).
README and demo are later phases.

## Note — do not protect sample_documents

Grep mode depends on the agent's `search`/`read_file` tools reaching
`sample_documents/`. Do NOT add `modules/*/sample_documents` to
`permissions.protected_paths`: the registry guard would deny the calls and
grep mode would fail. (Only the maintenance_copilot `sample_manuals` corpus is
protected by default.)
