# AI Workspace → Enterprise Knowledge Ingest — Design

**Date:** 2026-07-09
**Status:** Approved (design), pending implementation
**Author:** dien-tran (with Claude)

## 1. Context & problem

`ai_workspace` (My Tasco P1 secure document workspace) lets Manager+ users upload
documents. On upload it stores the file on disk, extracts text (PDF/DOCX/PPTX/OCR)
into a `.txt` sidecar, and writes a row to its own SQLite `documents` table. It does
**not** chunk, embed, or index anything — so uploaded documents cannot be searched or
answered over by AI.

`enterprise_knowledge` (EK) already has the full retrieval engine: Chonkie chunking,
hosted embeddings, a Qdrant hybrid index (dense + BM25 sparse), and an ACL-filtered
search. Its only ingest entry today is a CLI that reads a *directory* of `.md`/`.txt`
files with front-matter.

The two modules share the **same ACL model** (aligned in commit `c83ca55`, verified by
a cross-module parity test).

**Goal of this increment:** when a document is uploaded in `ai_workspace`, automatically
ingest it into EK (chunk + embed + upsert to Qdrant with ACL metadata) so it becomes
retrievable; keep the index in sync on delete.

## 2. Goals / Non-goals

**Goals**
- On `add-document`: synchronously chunk + embed + upsert the uploaded doc into EK's
  Qdrant collection, carrying the ACL metadata (`department`, `classification`,
  `knowledge_space`).
- On `delete-document` (soft-delete): remove the doc's chunks from Qdrant.
- BM25 stays correct for newly-uploaded docs (avgdl handled incrementally).
- Upload never fails because indexing failed (graceful degradation + retry).

**Non-goals (later increments)**
- Wiring search into the web chat/agent + enforcing ACL on that chat path.
- Async/queue-based indexing.
- Extended search-result payload (filename/size/deep-link back to the module).
- Mapping the web-authenticated user → RBAC identity.

## 3. Locked decisions

- **A. Invocation — in-process via a slim, audit-free EK entry.** EK exposes a new
  `scripts/ingest_api.py` importing only the ingest chain (`chunking`, `corpus`,
  `index_store`, `config`, `client`) — never `audit` or `knowledge.py`. Verified: those
  module names do not collide with any `ai_workspace/scripts` filename (`audit` is the
  only shared name, and the ingest chain does not import it), so bare imports resolve
  correctly in one process. `ai_workspace` calls it through a thin adapter
  (`scripts/ek_index.py`) that imports lazily.
- **B. avgdl — count-through from the index; no side table.** Store `token_count` in the
  chunk payload. On ingest, EK sums `token_count` over the existing collection and adds
  the new doc → `avgdl` → upsert. `reindex` recomputes exactly and rewrites all sparse
  vectors. Single source of truth = Qdrant.
- **C. One Qdrant collection.** Reuse EK's default `enterprise_chunks`, fed **only** by
  `ai_workspace`. The EK demo seeder (`knowledge.py ingest --samples`) is not run into
  it. `ai_workspace` doc_ids are unique (sequential), so no internal collision.
- **D. Timing/sync.** Synchronous on upload; synchronous removal on delete. Payload stays
  as-is plus `token_count` (an index-internal stat, not file metadata).

## 4. Architecture & data flow

```
ai_workspace.cmd_add_document
  1. repo.insert_document(...)              (existing) → SQLite row, index_status='pending'
  2. save file + extract text sidecar       (existing)
  3. if text: ek_index.index_document(doc_id, title, dept, classification, text, owner)
        │  (lazy import of EK ingest_api)
        ▼
     EK.ingest_api.ingest_document(...)
        • build corpus.Document(text, metadata) → chunk_document (Chonkie)
        • IndexStore.corpus_token_stats()  → (total_tokens, total_chunks)  [count-through]
        • avgdl = (total_tokens + doc_tokens) / (total_chunks + doc_chunks)
        • IndexStore.upsert_chunks(records, avgdl)   → dense + BM25 sparse + payload
          payload: doc_id, chunk_id, text, title, department, classification,
                   knowledge_space, owner, citation, token_count
        • return {chunks_indexed, doc_tokens, avgdl_used}
  4. repo.set_index_status(doc_id, 'indexed' | 'failed' | 'skipped')

ai_workspace.cmd_delete_document (soft-delete)
  1. repo.set_document_status(doc_id, 'deleted')   (existing)
  2. ek_index.remove_document(doc_id) → EK.ingest_api.remove_document
        → IndexStore.delete_by_doc_id(doc_id)  (Qdrant delete by payload filter)

ai_workspace.cmd_reindex  (new)
  • rebuild the index from all active documents with exact avgdl (reset + upsert-all)
```

Update/re-upload: `ai_workspace` has no in-place edit — a "new version" is a new upload
(new doc_id) plus soft-delete of the old, so delete-removal + add-ingest already cover it.

## 5. Components (new / changed)

### enterprise_knowledge
- **NEW `scripts/ingest_api.py`** (audit-free):
  - `ingest_document(doc_id, title, department, classification, text, owner="", knowledge_space=None, store=None) -> dict`
    - Builds a `corpus.Document` (knowledge_space via `corpus.knowledge_space_for` when
      not given), calls `chunk_document`, computes running `avgdl`, `upsert_chunks`.
    - Returns `{"chunks_indexed": int, "doc_tokens": int, "avgdl_used": float}`.
    - Empty/whitespace text → returns `{"chunks_indexed": 0, ...}` (caller marks skipped).
  - `remove_document(doc_id, store=None) -> int` → `IndexStore.delete_by_doc_id`.
  - `_build_store()` reused from the same config path EK's CLI uses (Qdrant URL +
    `index_embed` embedder). `store` injectable for tests.
- **CHANGE `scripts/index_store.py`**:
  - `upsert_chunks` payload gains `"token_count": rec.token_count`.
  - NEW `delete_by_doc_id(doc_id) -> int` (delete points where `payload.doc_id == doc_id`).
  - NEW `corpus_token_stats() -> tuple[int, int]` (scroll, sum `token_count`, count points).

### ai_workspace
- **NEW `scripts/ek_index.py`** — adapter isolating the EK import:
  - lazily inserts EK scripts dir on `sys.path`, imports `ingest_api`.
  - `index_document(doc_id, title, dept_code, classification, text, owner) -> bool`
    (returns False on any failure; never raises to the caller).
  - `remove_document(doc_id) -> bool` (best-effort).
- **CHANGE `scripts/models.py`** — `Document.index_status` column
  (`String(16)`, default `"pending"`; values: pending/indexed/failed/skipped).
- **CHANGE `scripts/repo.py`** — `set_index_status(doc_id, status)`; include
  `index_status` in `_doc_dict` for management listings.
- **CHANGE `scripts/workspace.py`**:
  - `cmd_add_document`: after insert + extraction, call `ek_index.index_document`
    (skip when no extracted text → `skipped`); set `index_status`; audit the outcome.
  - `cmd_delete_document`: after soft-delete, call `ek_index.remove_document`.
  - NEW `cmd_reindex(user_id)` + `reindex` subparser (Executive only): rebuild the index
    from active docs, recomputing exact avgdl.
- **CHANGE `requirements.txt`** — add `qdrant-client`, `chonkie`, `openai` (needed for
  in-process ingest; adapter still degrades gracefully if unavailable).

## 6. Metadata mapping (ai_workspace → EK payload)

| ai_workspace document | EK chunk payload |
|---|---|
| `department` (dept_code) | `department` + `knowledge_space = knowledge_space_of(dept)` |
| `classification` | `classification` |
| `title` | `title` |
| `id` (DOC0xx) | `doc_id` |
| `uploaded_by` | `owner` |
| extracted text (sidecar) | chunk `text` (+ derived `token_count`) |

ACL fields (`department`, `classification`, `knowledge_space`) are exactly what
`acl.build_filter` / `acl.can_access` use, so ACL-filtered search works unchanged.

## 7. Error handling & edge cases

- EK/Qdrant/embedding unavailable or raising → `index_document` returns False → upload
  still succeeds, `index_status='failed'`, audit records the failure; `reindex` retries.
- No extractable text (e.g., scanned image without OCR) → `index_status='skipped'`,
  nothing indexed.
- avgdl divide-by-zero (empty collection) → fall back to the new doc's own average length
  (or 1.0), matching `bm25.average_length` semantics.
- Delete of a never-indexed doc → `delete_by_doc_id` deletes 0 points (no error).

## 8. Configuration

The `ai_workspace` process needs EK's ingest env: `EK_INDEX_EMBED_*`, `EK_QDRANT_URL`
(and `EK_EMBED_DIM`). Present in docker-compose; documented for local `.env`. When absent,
indexing degrades to `failed`/`pending` without breaking upload.

## 9. Testing (TDD — tests first)

**EK (`tests/test_enterprise_knowledge_ingest_api.py`)** — hermetic, in-memory Qdrant +
fake embed_fn:
- ingest_document indexes queryable chunks with ACL payload (department/classification/
  knowledge_space) and `token_count`.
- running avgdl reflects existing + new chunks (assert `avgdl_used`).
- an ingested cross-department Internal doc is excluded by `build_filter` for another dept.
- remove_document deletes exactly the doc's chunks.
- empty text → 0 chunks.
- `index_store`: `delete_by_doc_id`, `corpus_token_stats`, payload contains `token_count`.

**ai_workspace (`tests/test_ai_workspace_ek_index.py`, extend upload/delete tests)** —
inject a fake `ek_index`:
- add-document calls indexer with correctly mapped metadata.
- index failure → upload succeeds, `index_status='failed'`.
- no text → `index_status='skipped'`.
- delete-document calls `remove_document`.
- `index_status` defaults to `pending`; reindex updates statuses.

**Parity:** reuse `test_enterprise_knowledge_acl_parity.py`; the ingest path introduces no
new ACL logic.

## 10. Out of scope (explicitly deferred)

Chat/agent search wiring + ACL on the chat path; async worker; extended payload &
deep-linking; web-user → RBAC identity mapping; hard-delete of files/sidecars.
