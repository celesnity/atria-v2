# Enterprise Knowledge — Permission-Aware GraphRAG Design

**Date:** 2026-07-06
**Module:** `modules/enterprise_knowledge` (EK)
**Status:** Approved design — ready for implementation planning
**Author:** Brainstormed with Claude (superpowers:brainstorming)

---

## 1. Summary

Add a **knowledge graph** to the EK module to improve **retrieval quality** (GraphRAG),
while preserving EK's defining property: **permission-aware, cited, Vietnamese-only
answers**. The graph augments the existing vector pipeline — it does **not** change the
user-facing behavior or introduce new query types. Same questions, more complete answers,
identical access-control guarantees.

The user's stated goal (chosen explicitly during brainstorming): **"Better retrieval
(GraphRAG)"** at **best quality**, using a **hybrid metadata + LLM** graph stored in
**Neo4j**.

## 2. Goals / Non-Goals

**Goals**
- Use a graph to pull in *connected, permitted* context so synthesized answers are more
  complete and accurate for multi-fact questions.
- Reuse EK's existing pipeline (corpus, chunking, ACL, synthesis, audit) unchanged where
  possible; the graph slots in *behind* retrieval.
- Be **provably safe**: graph traversal must enforce the exact same RBAC as the vector
  path, at every hop.
- Be **cheap on the free tier**: deterministic metadata backbone always works with zero
  LLM cost; the LLM extraction pass is optional, toggleable, and cached.
- Be **measurably better**: prove the lift with the dataset's built-in evaluation set.

**Non-Goals (explicitly out of scope)**
- **New relationship-query capabilities** (org charts, "what references what"). The goal is
  retrieval augmentation, not a new answer type.
- **Community-summary GraphRAG** (Microsoft-style community detection + LLM summaries).
  Documented as the future upgrade path; too heavy/expensive for now (YAGNI).
- Changing the synthesis prompt, citation format, or Vietnamese-only guardrails.
- Any change to the general Atria platform outside the EK module + its compose wiring.

## 3. Decisions (from brainstorming)

- **Purpose:** GraphRAG for better retrieval (augment existing permission-aware vector RAG).
- **Graph source:** Hybrid — deterministic metadata backbone + optional/toggleable LLM
  extraction over chunks.
- **Graph store:** Neo4j (best quality). Reuse the Neo4j service already in the compose
  stack (currently used by `maintenance_copilot`). The compose image is `neo4j:5`
  **Community edition, which supports only a single database (`neo4j`)** — so EK/MC
  isolation is done via a **label prefix + `namespace="ek"` property** on all EK nodes and
  edges (every EK query filters on it), **not** a separate database. (If the deployment ever
  moves to Neo4j Enterprise, a dedicated `ek` database becomes the cleaner option.)
- **Retrieval integration:** Approach A (entity-seeded, ACL-filtered expansion fed into
  synthesis) **plus** Approach B (graph-connectivity rerank boost). Approach C
  (community-summary) deferred.

## 4. Reference: maintenance_copilot (MC)

MC already implements a Neo4j GraphRAG in this repo and is the concrete pattern to adapt:
- `scripts/extraction.py` — LLM extracts JSON entities/relations, validated against
  allow-lists, stamped with provenance + `confidence` + `status="unverified"`.
- `scripts/graph_store.py` — Neo4j `MERGE` upserts, per-label uniqueness constraints,
  injectable `run_fn` (mockable for tests), `neighbors(key, hops)` traversal.
- `config.py` role-based clients, `budget.py` token budgeting.

**What we adapt.** The extraction + graph_store shape transfers directly (EK already
mirrors MC's module skeleton).

**What we must NOT reproduce.** MC's graph is **access-blind** (no classification/department
on nodes or edges) and merely **advisory** (synthesis never consumes it). EK requires the
opposite on both counts: **ACL-carrying nodes** and **graph context actually fed into
synthesis**.

## 5. Dataset (source of truth)

Workspace dataset:
`Tasco Resources/AI Workspace_ Enterprise Knowledge & Secure AI Search/ai_workspace_dataset_vietnamese_participants.xlsx`

Relevant sheets (validated against EK's `acl.py` — exact match):
- `Documents` / `Document_Metadata`: `document_id, title, department, classification,
  content_vi, owner, allowed_access, last_updated, tags, language, word_count`.
- `Departments`: `department_id, department_en, department_vi, knowledge_space`
  (COMP→Company Knowledge, EXEC→Executive Knowledge, else Department Knowledge).
- `Roles`: Employee / Manager / Director / Executive with company / department / executive
  knowledge access levels.
- `Permissions`: classification × role matrix — **identical** to `acl.py`
  (Public/Internal → all; Confidential → own department + Executive; Restricted →
  Executive only).
- `Public_Evaluation`: **52 labeled cases** — `question_id, category, user_id, user_role,
  user_department, question_vi, expected_permission (Allow/Deny), expected_document_id,
  answer_type, difficulty`.

**Two dataset-driven additions to the design:**
1. **`tags` as free deterministic entity seeds.** The repo corpus front-matter does **not**
   currently carry `tags` (`corpus.py` parses `owner`/`knowledge_space`/`last_updated` only;
   0 sample docs have `tags:`). Enriching ingestion with `tags` yields `Tag` connector
   nodes + `TAGGED` edges with **no LLM call**, strengthening the metadata backbone.
2. **`Public_Evaluation` as the eval/regression harness** — the measurable definition of
   done (see §10).

## 6. Graph schema

All EK nodes/edges additionally carry `namespace="ek"` (see §3) for isolation from MC.

**Gated nodes (carry ACL — `department` + `classification`):**
- `Document {doc_id, title, department, classification, owner, knowledge_space, last_updated}`
- `Chunk {chunk_id, doc_id, citation, department, classification}` — links 1:1 to a Qdrant
  point.

**Connector nodes (NOT gated — never trusted for access):**
- `Entity {key, name, type, confidence, status, provenance}` — from LLM extraction;
  `type` ∈ allow-list (e.g. Policy, Concept, Person, Org, Amount, Date).
- `Tag {name}` — from `Document_Metadata.tags` (deterministic).
- `Department {department_id, ...}`, `KnowledgeSpace {name}` — non-sensitive dimensions.

**Edges:**
- `(Chunk)-[:PART_OF]->(Document)`
- `(Document)-[:IN_DEPARTMENT]->(Department)`
- `(Document)-[:TAGGED]->(Tag)` and/or `(Chunk)-[:TAGGED]->(Tag)`
- `(Chunk)-[:MENTIONS]->(Entity)` (LLM extraction)
- `(Entity)-[:RELATED_TO {type, confidence}]->(Entity)` (LLM extraction; cross-doc links)

**Why entities are unlabeled connectors.** An entity (e.g. "chính sách nghỉ phép") can
appear in a Public doc *and* a Confidential doc, so it has no single classification. We
never gate on it. Traversal uses entities/tags only to *discover* candidate chunks; the
content that enters context/citations is always a `Chunk`, ACL-checked with the existing
`acl.can_access`. An entity reachable only through Restricted chunks yields nothing for a
non-executive.

**Constraints:** one uniqueness constraint per node label on its key
(`Document.doc_id`, `Chunk.chunk_id`, `Entity.key`, `Tag.name`) for idempotent upserts.

## 7. Ingestion (build time)

Two passes over the corpus EK already parses:

**Pass 1 — Metadata backbone (deterministic, no LLM, always runs).**
From YAML front-matter + `Document_Metadata` (tags) + `access/*.csv`: create `Document`,
`Chunk`, `Tag`, `Department` nodes stamped with `department`/`classification` (inherited),
plus `PART_OF`, `IN_DEPARTMENT`, `TAGGED` edges. This is the ACL substrate and provides
real GraphRAG lift (tag co-occurrence) at zero LLM cost.

**Pass 2 — Semantic extraction (LLM, optional/toggleable).**
For each chunk, an extraction prompt (adapted from MC `extraction.py`) returns JSON
entities + `RELATED_TO` relations, validated against an allow-list, stamped with
`confidence`, provenance, and `status="unverified"`. Creates `Entity` nodes +
`MENTIONS`/`RELATED_TO` edges.

**EK-specific ingestion requirements (beyond MC):**
- **Extraction caching** — key each chunk's extraction by a content hash (reuse EK's stable
  `uuid5`/chunk-id). Rebuilds skip unchanged chunks. (MC re-extracts everything; unusable on
  free tier.)
- **Extraction toggle** — Pass 2 runs only when `graph build --extract` is passed (or
  `EK_GRAPH_EXTRACT=1`). Default builds the metadata backbone only; enable LLM extraction
  when a paid/faster endpoint is available. (Distinct from the query-time master switch
  `EK_GRAPH_ENABLED`, see §8/§9.)
- **ACL inheritance at write time** — every `Chunk`/`Document` node gets
  `department`+`classification` from its source, so the graph is ACL-aware from the first
  write.

## 8. Retrieval (query time) — Approach A + B

1. Resolve user → role/department (`identity.py`).
2. **Vector path (unchanged):** Qdrant search + existing ACL pre-filter → permitted seed
   chunks.
3. **Graph path:** seed chunks → `MENTIONS`/`TAGGED` → traverse `RELATED_TO`/`TAGGED`
   1–2 hops (`EK_GRAPH_HOPS`, capped by `EK_GRAPH_MAX_NEIGHBORS`) → resolve neighbor
   entities/tags back to candidate chunk-ids.
4. **ACL on graph candidates — two layers, identical predicate to the vector path:**
   - *Cypher-level filter:* pass the user's `(permitted departments, permitted
     classifications, is_executive)` into the traversal (a graph mirror of
     `acl.build_filter`) so only permitted chunks are returned.
   - *Python re-check:* run existing `guard_accessible` on every graph-sourced chunk.
5. **Merge + dedup:** union vector + graph chunks by `chunk_id`; rerank (vector score
   primary, graph-connectivity boost = Approach B); cap to budget.
6. **Citation-time ACL re-check** (existing `guard_accessible`) → **Synthesis**
   (`synthesis.py`, unchanged interface — receives a richer, still-permitted hit list).

**Security invariant (the cornerstone):** *No chunk enters synthesis or citations unless it
passes `acl.can_access` for the querying user — the same predicate on both paths.* The graph
can only surface candidate chunk-ids faster; **it never grants access.**

## 9. Module surface (files, CLI, config, compose)

**New scripts** (`modules/enterprise_knowledge/scripts/`):
- `graph_store.py` — Neo4j wrapper: injectable `run_fn`, `ensure_constraints`,
  `upsert_nodes/edges`, `neighbors(chunk_ids, hops, acl_filter)`, `stats`, `reset`.
- `extraction.py` — LLM entity/relation extraction (allow-list + provenance + confidence +
  status).
- `graph_build.py` — ingestion orchestrator (backbone + optional extraction, with caching).
- `graph_retrieval.py` — query-time expansion + ACL-filtered candidate resolution + merge.

**Changed files:**
- `corpus.py` — parse `tags` (+ optional `allowed_access`); backfill via `--from-xlsx` /
  a small `metadata_sync.py` that reads `Document_Metadata`.
- `knowledge.py` — new subcommands `graph build [--extract]`, `graph show <key> [--hops]`,
  `graph stats`, `graph reset`; a `--graph` flag on `query`; extend `health` to probe Neo4j.
- `config.py` — add `EK_KG_EXTRACT_*` role (mirrors `EK_SYNTHESIS_*`) + `EK_GRAPH_ENABLED`,
  `EK_GRAPH_HOPS`, `EK_GRAPH_MAX_NEIGHBORS`, `EK_NEO4J_URI/USER/PASSWORD`.
- `requirements.txt` — add `neo4j>=5.24`.
- `docker-compose.yml` — add `EK_NEO4J_*` passthrough to `atria` + `atria-worker` (mirror the
  `MC_NEO4J_*` block), pointing at the existing `neo4j` service (`bolt://neo4j:7687`); EK
  isolates via the `namespace="ek"` label/property (§3), not a separate database.
- `SKILL.md` — document `--graph` and when it helps.
- `dashboard.html` — optional "expand with graph" toggle (defer-able).

**Config / env defaults (two distinct switches):**
- `EK_GRAPH_ENABLED=0` — **query-time master switch.** When 0, `query` is vector-only even if
  `--graph` is passed; when 1, `--graph` (or default-on) performs graph expansion.
- `EK_GRAPH_EXTRACT=0` — **build-time switch** for Pass 2 LLM extraction (equivalently the
  `graph build --extract` flag). Backbone always builds regardless.
- `EK_GRAPH_HOPS=1`, `EK_GRAPH_MAX_NEIGHBORS=20`
- `EK_NEO4J_URI=bolt://neo4j:7687`, `EK_NEO4J_USER=neo4j`, `EK_NEO4J_PASSWORD=atria-neo4j`
- `EK_KG_EXTRACT_{PROVIDER,MODEL,BASE_URL,API_KEY}` (fallback key resolution as in
  `config.py`)

## 10. Degradation, testing, and definition of done

**Graceful degradation (never fail a query):**
- Neo4j unreachable / `EK_GRAPH_ENABLED=0` / graph never built → skip graph path, serve
  **vector-only** (behaviorally identical to today). Zero-regression guarantee.
- Extraction endpoint 429/timeout → skip that chunk's extraction, continue; backbone already
  present; caching prevents re-hammering.
- `namespace="ek"` filter on every EK graph read so EK never sees MC nodes (shared
  single-database Neo4j Community).

**Testing** (pytest; mirrors EK's 14 existing tests + MC's injectable-`run_fn` pattern):
- **Unit:** `graph_store` with in-memory fake `run_fn`; `extraction.parse_extraction` on
  fixture JSON; `corpus` tags parsing; the ACL-filter Cypher param builder.
- **ACL leakage tests (critical):** graph where a permitted chunk's entity links to a
  Restricted/other-department chunk; assert a non-executive `--graph` query never returns or
  cites the forbidden chunk. Parametrized over permission-matrix corners.
- **E2E offline eval harness:** run all 52 `Public_Evaluation` cases, graph on vs off; assert
  (a) **0 Allow/Deny regressions**, (b) **recall@k(expected_document_id) graph ≥ vector**.
  Offline (mocked embed/synthesis, in-memory Neo4j stub seeded from the backbone).

**Definition of done:**
1. Zero ACL regressions across all 52 `Public_Evaluation` cases.
2. `expected_document_id` recall@k improves or holds vs. the vector-only baseline.
3. Pure-vector behavior is unchanged when the graph is disabled.
4. Health check reports Neo4j status; ingestion is idempotent + cached.

## 11. Risks

- **ACL leakage via traversal** — the primary risk; mitigated by the two-layer ACL filter +
  citation re-check + dedicated leakage tests. Treated as a must-hold invariant.
- **Free-tier extraction cost/latency** — mitigated by metadata-only default, caching, and
  the toggle.
- **Neo4j shared with MC** — mitigated by the `namespace="ek"` label/property filter on
  every EK read (single-database Community edition; no cross-module reads).
- **Dataset sync scope** — `tags` and the eval set live only in the xlsx today; the small
  corpus-sync step is real (but low) added scope.
- **Entity quality (LLM extraction)** — `status="unverified"` + `confidence` retained;
  low-confidence edges can be down-weighted in rerank.

## 12. Future upgrade path (not now)

Community-summary GraphRAG (Approach C) for broad/thematic questions: precompute graph
communities + LLM summaries, retrieve at community level. Revisit only if global-summary
questions become a real need and a cost-appropriate LLM endpoint is available.
