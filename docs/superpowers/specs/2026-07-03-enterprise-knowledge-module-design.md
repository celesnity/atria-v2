# Enterprise Knowledge Module — Design

- **Date:** 2026-07-03
- **Status:** Approved (design) — core module pass
- **Author:** brainstormed with the user
- **Base:** cloned from `modules/maintenance_copilot`, minus the knowledge graph, plus an access-control layer
- **Problem source:** `Tasco Problem Statement.pdf` (P1 — AI Workspace: Enterprise Knowledge & Secure AI Search)
- **Dataset:** `ai_workspace_dataset_vietnamese_participants.xlsx`

## 1. Context and problem

Tasco's "My Tasco" AI Workspace needs a **secure, permission-aware enterprise-knowledge
RAG**. Employees ask natural-language questions and get answers grounded in company
documents — but the *defining* requirement is that a user must never retrieve, see, or
receive answers grounded in documents outside their access scope. This is what separates
the module from a generic RAG (and from `maintenance_copilot`, which has no per-user
access control).

The corpus and all questions/answers are in **Vietnamese**.

## 2. Goals and non-goals

### Goals (this pass — "core module first")

- A working Atria module `modules/enterprise_knowledge/` mirroring `maintenance_copilot`'s
  shape (skill + CLI + scripts + unit tests).
- One-time converter that materializes the `.xlsx` into a file corpus + access data.
- **Permission-aware retrieval**: the querying user's `(role, department)` constrains the
  vector search so forbidden documents never enter the candidate set.
- Vietnamese grounded answers with mandatory citations and an access guard.
- Append-only audit trail recording the user, the permission decision, and returned docs.
- Unit tests (injected fakes, no live services), including access-control cases seeded from
  the dataset's labeled `Deny`/`Allow` questions.

### Non-goals (deferred to a later pass)

- Full evaluation harness scoring all 50 `Public_Evaluation` Q&A.
- README, demo scripts, presentation deck.
- Neo4j knowledge graph (dropped from the `maintenance_copilot` base — not in scope).
- DOCX/PPTX/image/OCR ingest (dataset is text/markdown).
- Web UI, a CLAUDE.md routing rule, and docker-compose changes beyond reusing the
  existing Qdrant sidecar.

## 3. The dataset (materialized source)

`ai_workspace_dataset_vietnamese_participants.xlsx` sheets used:

- **Documents** — 40 docs, 8 departments × 5. Vietnamese markdown body (~300 words),
  header lines declaring owner department + classification.
- **Document_Metadata** — `owner`, `allowed_access`, `last_updated`, `tags`, `word_count`.
  `allowed_access` is 1:1 with `classification` (redundant; `classification` is canonical).
- **Users** — 32 users: `user_id, full_name, department, role, email, status`.
- **Departments** — `department_id` (COMP, HR, FIN, PROD, ENG, OPS, LEGAL, EXEC),
  `department_en`, `department_vi`, `knowledge_space`.
- **Roles** — Employee / Manager / Director / Executive with knowledge-space grants.
- **Permissions** — the classification × role matrix (materialized as reference only).
- **Public_Evaluation** — 50 labeled Q&A (`user_id`, `expected_permission` Allow/Deny,
  `expected_document_id`, `answer_type`, `difficulty`). **43 Allow / 7 Deny.** Used this
  pass only as a source of unit-test cases, not a full harness.

### Department-name canonicalization (required)

The **Documents** sheet uses `HR` while **Users** uses `Human Resources`; all other
department labels already agree. The converter normalizes *every* department reference —
in document front-matter and `users.csv` — to the canonical `department_id` from the
**Departments** sheet (`COMP, HR, FIN, PROD, ENG, OPS, LEGAL, EXEC`). Without this,
`user.department == doc.department` comparisons silently fail for HR.

`knowledge_space` is derived from `department_id`: `COMP → Company Knowledge`,
`EXEC → Executive Knowledge`, everything else → `Department Knowledge`.

## 4. Access-control model

Verified against all 50 `Public_Evaluation` labels (all 43 Allow + 7 Deny reproduced):

```
allow(user, doc):
  classification == Public       → True                       # everyone
  classification == Internal     → True                       # all employees
  classification == Restricted   → user.role == "Executive"
  classification == Confidential → user.role == "Executive"
                                    or user.department == doc.department
```

- `department` on both sides is the canonical `department_id` (§3).
- The matrix is encoded in `acl.py` as a small declarative structure that mirrors the
  `Permissions` sheet. `permissions.csv` is materialized as human-readable reference only;
  enforcement is code (so it is unit-testable and cannot drift from an unparsed file).
- **Known simplification:** a `Company`-owned `Confidential` document would resolve to
  "own department == COMP" rather than "all employees". The dataset has no such document
  (Company docs are only Public/Internal), so this is not exercised; noted for correctness.

### Enforcement strategy — pre-retrieval filter + synthesis guard (defense in depth)

1. **Pre-retrieval:** `acl.build_filter(user)` compiles the predicate into a Qdrant payload
   filter, so the vector search only ever ranks documents the user may see. Forbidden docs
   never enter the candidate pool — no leakage via ranking, scores, or counts.
2. **Synthesis guard:** an independent second check asserts every cited chunk is in the
   user's accessible set before it appears in the answer; a stray forbidden citation is
   dropped and the answer flagged `needs_review`.

Rejected alternatives: post-retrieval filtering (forbidden docs pollute the pool, `k`
shrinks unpredictably, metadata-leak risk) and per-user/per-department collections
(overkill for 40 docs; duplicates public docs into every partition).

## 5. Architecture

```
modules/enterprise_knowledge/
├── SKILL.md                     # skill contract + runbook (Vietnamese Q&A)
├── manifest.json                # module manifest (subagent disabled)
├── requirements.txt             # openai, qdrant-client, chonkie, openpyxl
├── sample_documents/            # 40 materialized *.md (front-matter + VN body)  [tracked]
├── access/
│   ├── users.csv                # user_id, full_name, department(_id), role, email, status
│   ├── roles.csv                # reference: role grants
│   └── permissions.csv          # reference: classification × role matrix
├── data/                        # audit log (gitignored)
├── tools/
│   └── build_corpus.py          # ONE-TIME xlsx → sample_documents/ + access/*.csv
└── scripts/
    ├── knowledge.py             # CLI orchestrator (was copilot.py)
    ├── config.py                # roles: index_embed, synthesis (hosted-API defaults)
    ├── client.py                # RoleClient (OpenAI-compatible, per-endpoint reuse)
    ├── corpus.py                # front-matter parser → Document
    ├── chunking.py              # Chonkie RecursiveChunker → citation-anchored chunks
    ├── identity.py              # NEW: users.csv → User(role, department)
    ├── acl.py                   # NEW: permission predicate + Qdrant filter builder
    ├── index_store.py           # Qdrant; ACL-filtered, revision-free queries
    ├── synthesis.py             # Vietnamese grounded answers
    ├── guardrails.py            # cite-or-drop + access guard + advisory note
    ├── budget.py                # token budgeting
    └── audit.py                 # append-only JSONL trail (user + decision)
```

**Dropped from the base:** `extraction.py`, `graph_store.py` (Neo4j KG), the `kg_extract`
and (unused) `chunk_embed` roles, and all `graph *` CLI subcommands.

### Naming and configuration

- CLI: `python knowledge.py <cmd>`; env prefix `EK_`; Qdrant collection `enterprise_chunks`.
- Roles (`config.py`): `index_embed`, `synthesis`. Hosted-API defaults:
  - `index_embed` → OpenAI `text-embedding-3-small` (`EK_EMBED_DIM` default **1536**).
  - `synthesis` → a multilingual chat model (default `gpt-4o-mini`), overridable to any
    OpenRouter model via `EK_SYNTHESIS_*`.
  - `EK_<ROLE>_{PROVIDER,MODEL,BASE_URL,API_KEY}` override each field. API-key default
    falls back to `OPENAI_API_KEY` / `OPENROUTER_API_KEY` from the environment.
- Other env (inherited pattern): `EK_QDRANT_URL`, `EK_MODEL_CTX`, `EK_CHUNK_SIZE`,
  `EK_MIN_CONFIDENCE`, `EK_AUDIT_LOG`, `EK_USERS_CSV`.
- Only **Qdrant** runs locally (reuse the existing sidecar; new collection). No TEI/vLLM.

## 6. Components (responsibility · interface · dependencies)

- **`identity.py`** — *what:* resolve a `user_id` to a `User(user_id, full_name, role,
  department_id, status)`. *interface:* `load_users(path) -> dict[str, User]`,
  `resolve(users, user_id) -> User` (raises `UnknownUserError`). *depends on:* `access/users.csv`.
- **`acl.py`** — *what:* the pure permission decision + Qdrant filter. *interface:*
  `can_access(user, doc_meta) -> Decision(allowed: bool, reason: str)`;
  `build_filter(user) -> qdrant Filter`; `accessible_classifications(user) -> set[str]`.
  *depends on:* nothing (pure); the matrix is a module constant. Injected into `index_store`
  and `knowledge.py`; unit-tested in isolation.
- **`corpus.py`** — front-matter now requires `doc_id, title, department, classification,
  owner, knowledge_space, last_updated, language`. `Document` carries them through.
- **`index_store.py`** — payload gains `classification`, `department`, `knowledge_space`,
  `owner`, `title`. `query(text, k, acl_filter=None)` accepts the ACL filter. The base's
  revision/ATA-chapter logic is removed — the enterprise corpus has neither.
- **`synthesis.py` / `guardrails.py`** — Vietnamese system prompt ("answer in Vietnamese,
  cite every claim, use only the passages"). `guardrails` keeps cite-or-drop + advisory note
  and adds the access guard: drop any citation whose `chunk_id` is not in the accessible set.
- **`audit.py`** — event schema extended: `{ts, type, user_id, role, department,
  permission_decision, query, returned_doc_ids, needs_review}`.
- **`knowledge.py`** — subcommands:
  - `health` — probe embeddings + synthesis endpoints + Qdrant.
  - `ingest [--samples DIR]` — parse + chunk + index `sample_documents/`.
  - `query "<vn text>" --user U004 [--k 5] [--department DEPT] [--synthesize]` —
    permission-aware retrieval (+ optional Vietnamese synthesized answer). `--department`
    narrows *within* the user's accessible scope; it never widens it.
  - `whoami U004` — resolved role/department/accessible classifications.
  - `can-access U004 DOC036` — `Allow`/`Deny` + reason (the clearest ACL expression).
  - `list`, `reset`, `audit [--limit N]` — inherited.
- **`tools/build_corpus.py`** — one-time. `--xlsx PATH [--out DIR]`. Reads Documents +
  Document_Metadata + Users + Departments + Roles + Permissions; canonicalizes departments;
  writes 40 `sample_documents/*.md` (front-matter + VN body) and `access/*.csv`. Idempotent.

## 7. Data flow

**Ingest:** `sample_documents/*.md → corpus.parse → chunking → index_store.upsert`
(payload carries classification/department/knowledge_space for filtering).

**Query:**
```
knowledge.py query "<vn>" --user U004 [--synthesize]
  → identity.resolve(U004)              → User(Employee, ENG)
  → acl.build_filter(user)              → Qdrant Filter
  → index_store.query(text, k, filter)  → only-accessible hits
  → [--synthesize] synthesis (Vietnamese)
       → guardrails: cite-or-drop + assert every cited chunk ∈ accessible
  → audit.append_event(user, decision, returned_doc_ids)
  → print hits (+ answer)
```

**can-access:** `identity.resolve → acl.can_access(user, doc_meta) → {Allow|Deny, reason}`.

## 8. Error handling

- Unknown `user_id` → clear message, non-zero exit (no query runs).
- Qdrant / embeddings / synthesis endpoint down → surfaced by `health`; `query` reports the
  failing service rather than guessing.
- **Zero accessible hits** → "Không tìm thấy tài liệu phù hợp trong phạm vi truy cập của
  bạn." (no leak — indistinguishable from "does not exist").
- A cited-but-forbidden chunk (should be impossible given the pre-filter) → dropped by the
  guard + answer flagged `needs_review`.
- Malformed front-matter / missing required key → converter and `corpus.parse` raise with
  the offending file + key.

## 9. Testing strategy (unit, injected fakes — no live services)

- **`acl`** — the 4 classification rules across roles/departments; parametrized with the
  **7 `Deny`** cases and a sample of `Allow` cases from `Public_Evaluation`
  (resolve user → decide against expected doc's metadata → assert matches `expected_permission`).
- **`identity`** — resolution, canonical department, unknown-user error.
- **`index_store`** — filter construction and that a fake Qdrant only returns filtered points;
  ACL filter excludes forbidden payloads.
- **`corpus`** — front-matter parse including classification/department/knowledge_space.
- **`synthesis` / `guardrails`** — cite-or-drop, the access guard dropping a forbidden
  citation, advisory note, `needs_review` on low confidence.
- **`knowledge.py`** — CLI wiring for `query`/`whoami`/`can-access` with fakes.
- **`build_corpus`** — converts a tiny in-memory/fixture workbook to expected files;
  department canonicalization (HR ↔ Human Resources) is asserted.

## 10. Open decisions (resolved)

- Data representation → **materialize to files** (converter output tracked; `.xlsx` external).
- Backend → **hosted API** (OpenAI/OpenRouter); only Qdrant local.
- Scope → **core module first**; eval harness / README / demo deferred.
- Permission matrix → **code-encoded** in `acl.py`; `permissions.csv` generated as reference.
- Knowledge graph → **dropped**.
