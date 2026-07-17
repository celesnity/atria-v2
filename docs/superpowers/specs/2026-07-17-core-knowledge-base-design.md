# Core Knowledge Base — Design Spec

**Date:** 2026-07-17
**Status:** Approved (brainstorming), pending implementation plan
**Owner:** anlnm

## 1. Goal

Give the agent a first-class, in-core knowledge system per tenant. Users dump
documents (PDF / text / markdown); core auto-ingests them into a hybrid vector +
full-text index and a knowledge graph; the agent retrieves them at query time
and always carries the tenant's persona + company background in its prompt.

This lives **inside `minder/core/`** — not an external module. It reuses the
existing search framework (`minder/core/context_engineering/search/`), the
Postgres layer, the artifact upload path, the Keycloak principal, and the
in-process `BackgroundScheduler`.

Non-goals for v1: management UI, docx/xlsx ingestion, multi-instance ingest
queue, human-in-the-loop graph verification workflow.

## 2. Requirements (settled during brainstorming)

- **Multi-tenant, hard isolation** by `tenant_id` (from Keycloak
  `CurrentPrincipal.tenant_id`). A tenant never sees another tenant's data.
- **Categories** with distinct behavior (three, v1):
  - `persona` → **inject** a summary into the system prompt; details still retrievable. Summarized on ingest.
  - `company_background` → **inject** summary into prompt; details retrievable. Summarized on ingest.
  - `reference_docs` → **retrieve** via hybrid RAG + graph. Everything else (policy, PDF, FAQ, workflow/SOP) goes here.
- **Knowledge graph (Neo4j)** for `reference_docs`: entity + relation extraction, used to expand retrieval recall. Serves both "manage different knowledge" (grouping via `tenant_id`/`category` on nodes) and "entity relations" (graph traversal).
- **Persona replaces** the agent's default identity/role section entirely (fallback to default when a tenant has no persona). **Operational/safety sections stay** (security-policy, tool-use rules) — those are not "persona".
- **Two ingestion sources**, one pipeline: API upload (reuse artifact endpoint) and a **mounted seed folder** auto-ingested on startup and on-demand.
- **Ingestion runs in the background** (batch / large PDFs of hundreds of pages; embedding + entity extraction are slow and must not block HTTP).
- Surface v1: **agent tool + API/CLI**. No UI.
- Infra: **Qdrant + Neo4j run locally** in `docker-compose.dev.yml`.

## 3. Architecture

New package `minder/core/knowledge/`:

```
minder/core/knowledge/
├── __init__.py
├── models.py          # Category enum, ORM helpers glue, IngestJob dataclass
├── categories.py      # per-category behavior: inject|retrieve, graph on/off, summarize on/off
├── parsing.py         # PDF (pypdf) / text / md → plain text + metadata
├── chunking.py        # paragraph-packing chunker (port of chunk_markdown, ~40 lines)
├── ingestion.py       # IngestionService: parse→chunk→embed→Qdrant+FTS→graph→summary
├── seed.py            # scan KNOWLEDGE_SEED_DIR, diff by hash, enqueue jobs
├── graph.py           # Neo4j build + 2-hop expand; best-effort, toggleable
├── provider.py        # DocumentsProvider(SearchProvider): dense+FTS+graph
├── profile.py         # ProfileInjector: persona/background summary → PromptComposer
├── service.py         # KnowledgeService: list / upload / reingest / delete (API+CLI)
└── tool.py            # core `knowledge_query` tool
```

Three independent flows, communicating through `models.py` + the shared
`search/` framework. `ingestion.py` and `provider.py` do not import each other.
Graph is best-effort: Neo4j down → ingest still completes (warn logged), query
skips the expansion step.

### 3.1 Reuse (already in core — not rebuilt)

- `search/embedder.py::Embedder` — OpenAI-compatible embeddings (`SEARCH_EMBED_*` / `OPENAI_API_KEY`).
- `search/dense.py::DenseIndex` — Qdrant wrapper (`QDRANT_URL`).
- `search/pg.py` — Postgres FTS helpers.
- `search/fusion.py::rrf_fuse`, `search/normalize.py::normalize_for_search`.
- `search/provider.py::SearchProvider`, `search/types.py` (`SearchContext`, `SearchHit`, `SourceResults`).
- `web/routes/artifacts.py` upload + `artifacts` table (file bytes land here).
- `auth/keycloak/principal.py::CurrentPrincipal.tenant_id`.
- `core/scheduler.py::BackgroundScheduler` (drives the ingest queue + startup seed scan).
- `PromptComposer` (persona injection hook).

## 4. Data model

### Postgres (new ORM classes in `minder/db/models.py`; `init_schema()` create_all)

`knowledge_documents`
- `id`, `tenant_id` (index), `category` (enum), `title`,
  `artifact_id` (FK→artifacts, nullable for seed-folder files),
  `source_path` (nullable, for seed files), `source_filename`,
  `content_hash` (sha256, for idempotency),
  `status` (`pending`|`ingesting`|`ready`|`failed`), `error` (nullable),
  `summary` (nullable Text — for persona/company_background),
  `created_at`, `updated_at`.

`knowledge_chunks`
- `id`, `document_id` (FK), `tenant_id` (index), `category`,
  `chunk_index`, `text`, `tsv` (tsvector, GIN index),
  `qdrant_point_id`, `citation`, `created_at`.

### Qdrant — one collection `knowledge_chunks`
Cosine, 1536-dim. Payload: `tenant_id`, `category`, `document_id`, `chunk_id`,
`text`, `title`, `citation`. Every query filters hard on `tenant_id` (+ `category`).
Single collection + filter (not per-tenant collections) — sufficient at this
scale; physical isolation can come later.

### Neo4j — only for categories with graph enabled (`reference_docs`)
Namespaced labels `:KDocument`, `:KChunk`, `:KEntity`; every node carries
`tenant_id`. Relations: `PART_OF` (chunk→doc), `MENTIONS` (chunk→entity),
`RELATED_TO` (entity→entity, with `confidence`, `status="unverified"`).
Entity types: `Concept`, `Process`, `Policy`, `Person`, `Org`, `Term`.
Extraction is LLM-based, cached by `sha256(chunk)` so reingest does not re-call
the LLM.

### Categories (`categories.py`)
Each category declares: behavior (`inject`|`retrieve`), `build_graph` (bool),
`summarize` (bool). v1:
- `persona` → inject, graph=false, summarize=true
- `company_background` → inject, graph=false, summarize=true
- `reference_docs` → retrieve, graph=true, summarize=false

Adding a category = one declaration line.

## 5. Ingestion (two sources, one pipeline)

### Source A — API upload
Reuse `POST /artifacts/upload`; on completion create a `knowledge_documents`
row (`status=pending`) + enqueue an ingest job. `category` supplied by the
caller.

### Source B — seed folder (`seed.py`)
Docker volume mounted at `KNOWLEDGE_SEED_DIR` (`/knowledge`), structure encodes
identity:

```
/knowledge/<tenant_id>/<category>/<files...>
```

- Level-1 dir = `tenant_id` (matches `CurrentPrincipal.tenant_id`); level-2 dir = `category`. Malformed paths logged and skipped.
- On startup (a `BackgroundScheduler` task) and on `POST /knowledge/rescan`: recurse the dir, compute `sha256` per file, diff against `knowledge_documents.content_hash`.
  - New / changed hash → create-or-update doc + enqueue (re)ingest.
  - Same hash → skip (restart-idempotent).
- **Upsert-only**: files removed from the folder are **not** auto-deleted (safe against a broken/empty mount). Manual cleanup via `minder knowledge delete <doc_id>`.

### Pipeline (`IngestionService`, background)
For each job: set `ingesting` → parse (`parsing.py`) → chunk (`chunking.py`) →
embed chunks (`Embedder`) → upsert Qdrant (payload with `tenant_id`+`category`)
→ write `knowledge_chunks` rows with `tsv` (FTS) → if `build_graph`: extract
entities/relations per chunk (LLM, cached) and write Neo4j → if `summarize`:
LLM-summarize the whole doc into `summary` → set `ready`. On failure: `failed`
+ `error`, other jobs continue.

## 6. Query (agent)

`knowledge_query` tool params: `question` (required), `category?`
(default `reference_docs`), `k?` (default 6). **`tenant_id` is NOT a
parameter** — taken from the principal so the model cannot cross tenants.

`DocumentsProvider.search`:
1. Embed question → Qdrant query, hard filter `tenant_id` + `category` → top-N dense.
2. Postgres FTS (`pg` + `normalize_for_search`), same filter → top-N lexical.
3. `rrf_fuse` the two rankings.
4. If `KNOWLEDGE_GRAPH_ENABLED` and category has graph → **2-hop** expansion
   (`KNOWLEDGE_GRAPH_HOPS=2`): from seed chunks traverse
   `MENTIONS → RELATED_TO* → chunk`, with a `max_neighbors` cap (~20) per step
   and dedup by `chunk_id`. Graph-sourced chunks get a small boost; vector hits
   still lead. Neo4j down → skip, no error.
5. Return `SearchHit[]` with `citation` (`title [doc_id] · doc_id#idx`).

## 7. Profile injection (persona / company_background)

- On ingest of `persona` / `company_background`: after storing chunks,
  LLM-summarize the whole doc (cap ~800 tokens) into
  `knowledge_documents.summary`. Full detail stays in chunks (retrievable).
- `ProfileInjector` (hook into `PromptComposer`): for the current `tenant_id`,
  load `summary` of all `persona` + `company_background` docs (Postgres, cached
  by `updated_at`).
  - **Replace** the default identity/role section entirely with the tenant's
    persona + a company-background section. Operational/safety sections
    (security-policy, tool-use) are untouched.
  - Tenant has no persona → keep the default identity section (fallback).
- Hard cap on total injected summary per tenant (~2000 tokens): overflow
  trimmed + logged; the trimmed detail is still retrievable.

## 8. Error handling (fail-safe, no data loss)

- Ingest job failure → `status=failed` + `error`; siblings continue; retry via `minder knowledge reingest <doc_id>`.
- Qdrant down at ingest → job `failed` (no half-write). At query → empty results + note "vector store unavailable"; the agent does not fabricate.
- Neo4j down → ingest completes (graph best-effort, warn); query skips graph.
- Summary/extraction LLM failure → chunk still stored; `summary=null` (persona still retrievable); graph skips that chunk; cache not written (retry next time).
- Idempotent by `content_hash` — reruns never duplicate.

## 9. Configuration (env; already wired in docker-compose.dev.yml)

`QDRANT_URL`, `KNOWLEDGE_NEO4J_URI`, `KNOWLEDGE_NEO4J_USER`,
`KNOWLEDGE_NEO4J_PASSWORD`, `KNOWLEDGE_GRAPH_ENABLED`, `KNOWLEDGE_GRAPH_HOPS=2`,
`KNOWLEDGE_SEED_DIR=/knowledge`, `KNOWLEDGE_DEV_TENANT=dev`, plus existing
`SEARCH_EMBED_*` / `OPENAI_API_KEY`. No centralized config object — env read at
the service, matching `DenseIndex`/`Embedder`.

`KNOWLEDGE_DEV_TENANT` provides a fallback tenant when a request has no
principal (only when `MINDER_ENV=dev`), so local dev needs no Keycloak.

## 10. Infra (done)

- `pyproject.toml`: `qdrant-client>=1.11`, `neo4j>=5.24`; `uv.lock` regenerated.
- `docker-compose.dev.yml`: new local `qdrant` service (+ `qdrant_data` volume);
  `minder` service gets the knowledge env vars + `./knowledge:/knowledge` mount.
  Neo4j service already present. Dockerfile unchanged (deps come from pyproject).

## 11. Testing

- **Unit** (`uv run pytest`, no external services; inject fake embedder/dense/graph):
  chunking; seed-scan (tenant/category from path, hash idempotency);
  category behavior map; `rrf_fuse` merge; `tenant_id` filter; ProfileInjector
  (with / without persona, fallback); citation format.
- **Integration** (compose profile `knowledge`): real ingest → Qdrant + Neo4j →
  query returns correct-tenant hits; **cross-tenant leakage test** (tenant A
  cannot see tenant B's docs).
- **E2e** (real `OPENAI_API_KEY`, per CLAUDE.md):
  `docker compose -f docker-compose.dev.yml up` → drop sample files in
  `./knowledge/dev/{persona,company_background,reference_docs}/` → `rescan` →
  ask the agent and confirm (a) answers cite `reference_docs`, (b) the agent
  reflects the tenant persona/background from its prompt.

## 12. Developer workflow

1. Drop files in `./knowledge/<tenant>/<category>/`.
2. `minder knowledge rescan` (CLI) or `POST /knowledge/rescan` — no restart.
3. `minder knowledge list` — see docs + status.
4. `minder knowledge query "<q>" --tenant dev` — test retrieval without the agent.

## 13. Open items for the implementation plan

- Exact `PromptComposer` section priority for persona replacement.
- Whether the ingest queue is a DB-polled `pending` scan or an in-memory queue fed by upload+seed (DB-polled is simpler and survives restart — likely choice).
- Token caps (summary 800, injected total 2000, `max_neighbors` 20) are starting values to tune.
