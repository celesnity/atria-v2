# AI Workspace → EK Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On upload in `ai_workspace`, synchronously chunk+embed+index the document into EK's Qdrant with ACL metadata; remove it on delete.

**Architecture:** EK exposes a slim, audit-free `ingest_api` (reusing `chunk_document` + `IndexStore`). `ai_workspace` calls it in-process through a lazy adapter. avgdl is derived by counting `token_count` over the collection (no side table). One collection `enterprise_chunks`, fed only by `ai_workspace`.

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0 (ai_workspace SQLite), qdrant-client, chonkie, openai, pytest.

## Global Constraints
- Line length 100 (Black + Ruff); Google-style docstrings; type hints on public APIs.
- Tests hermetic: in-memory Qdrant (`QdrantClient(":memory:")`) + fake `embed_fn`; no network.
- EK ingest chain must NEVER import `audit` or `knowledge` (in-process collision guard).
- Reference spec: `docs/superpowers/specs/2026-07-09-aiworkspace-ek-ingest-design.md`.
- Run tests with `PYTHONIOENCODING=utf-8 uv run pytest ...` (Vietnamese output on Windows).

---

## File structure
- `modules/enterprise_knowledge/scripts/index_store.py` — MODIFY (payload `token_count`, `delete_by_doc_id`, `corpus_token_stats`).
- `modules/enterprise_knowledge/scripts/ingest_api.py` — CREATE (audit-free `ingest_document`, `remove_document`, `reindex_documents`).
- `modules/ai_workspace/scripts/models.py` — MODIFY (`Document.index_status`).
- `modules/ai_workspace/scripts/repo.py` — MODIFY (`set_index_status`, expose `index_status`).
- `modules/ai_workspace/scripts/ek_index.py` — CREATE (lazy adapter).
- `modules/ai_workspace/scripts/workspace.py` — MODIFY (hooks + `cmd_reindex` + subparser).
- `modules/ai_workspace/requirements.txt` — MODIFY (add qdrant-client, chonkie, openai).
- Tests: `tests/test_enterprise_knowledge_index_store.py` (extend), `tests/test_enterprise_knowledge_ingest_api.py` (new), `tests/test_ai_workspace_ek_index.py` (new), `tests/test_ai_workspace_upload.py` (extend).

---

### Task 1: EK IndexStore — token_count payload, delete_by_doc_id, corpus_token_stats

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/index_store.py`
- Test: `tests/test_enterprise_knowledge_index_store.py`

**Interfaces:**
- Produces: `IndexStore.delete_by_doc_id(doc_id: str) -> int`, `IndexStore.corpus_token_stats() -> tuple[int, int]`; payload now includes `token_count: int`.

- [ ] **Step 1: Write failing tests** (append to `tests/test_enterprise_knowledge_index_store.py`; reuse its existing `_load`/`_store`/`_rec` helpers — a chunk record exposes `token_count`).

```python
def test_upsert_stores_token_count_in_payload():
    chunking = _load("chunking", "ek_is_tc_chunk")
    store = _make_store()  # in-memory IndexStore, dim=3, fake embed
    rec = _rec(chunking, "DOCT", "một hai ba bốn", "Internal", "ENG")  # 4 tokens
    store.upsert_chunks([rec], avgdl=4.0)
    pts, _ = store._q.scroll(store._collection, with_payload=True, limit=10)
    assert pts[0].payload["token_count"] == rec.token_count

def test_delete_by_doc_id_removes_only_that_doc():
    chunking = _load("chunking", "ek_is_del_chunk")
    store = _make_store()
    store.upsert_chunks([_rec(chunking, "DOCA", "a b", "Internal", "ENG"),
                         _rec(chunking, "DOCB", "c d", "Internal", "ENG")], avgdl=2.0)
    removed = store.delete_by_doc_id("DOCA")
    assert removed == 1
    left = {p.payload["doc_id"] for p in store._q.scroll(store._collection, limit=10)[0]}
    assert left == {"DOCB"}

def test_corpus_token_stats_sums_token_count():
    chunking = _load("chunking", "ek_is_stats_chunk")
    store = _make_store()
    r1 = _rec(chunking, "DOCA", "a b c", "Internal", "ENG")
    r2 = _rec(chunking, "DOCB", "d e", "Internal", "ENG")
    store.upsert_chunks([r1, r2], avgdl=2.5)
    total_tokens, total_chunks = store.corpus_token_stats()
    assert total_chunks == 2
    assert total_tokens == r1.token_count + r2.token_count
```

Add a `_make_store()` helper near the top of the test module if not present:

```python
def _make_store(dim=3):
    from qdrant_client import QdrantClient
    index_store = _load("index_store", f"ek_is_store_{dim}")
    s = index_store.IndexStore(QdrantClient(":memory:"), lambda ts: [[1.0, 0.0, 0.0] for _ in ts])
    s.ensure_collection(dim=dim)
    return s
```

- [ ] **Step 2: Run tests to verify they fail**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_enterprise_knowledge_index_store.py -k "token_count or delete_by_doc_id or corpus_token_stats" -v`
Expected: FAIL (`AttributeError: delete_by_doc_id` / KeyError `token_count`).

- [ ] **Step 3: Implement in `index_store.py`**

In `upsert_chunks`, add to the `payload={...}` dict (alongside `citation`):
```python
                    "token_count": rec.token_count,
```

Add two methods to `IndexStore` (after `list_indexed`):
```python
    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete every chunk whose payload ``doc_id`` matches. Returns the count removed."""
        if not self._q.collection_exists(self._collection):
            return 0
        flt = models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
        )
        removed = self._q.count(self._collection, count_filter=flt).count
        if removed:
            self._q.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(filter=flt),
                wait=True,
            )
        return removed

    def corpus_token_stats(self) -> tuple[int, int]:
        """Return ``(total_tokens, total_chunks)`` across the collection (0,0 if absent)."""
        if not self._q.collection_exists(self._collection):
            return 0, 0
        total_tokens = 0
        total_chunks = 0
        offset = None
        while True:
            recs, offset = self._q.scroll(
                self._collection, with_payload=True, limit=256, offset=offset
            )
            for r in recs:
                total_tokens += int(r.payload.get("token_count", 0))
                total_chunks += 1
            if offset is None:
                break
        return total_tokens, total_chunks
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_enterprise_knowledge_index_store.py -v`
Expected: PASS (all, including pre-existing).

- [ ] **Step 5: Commit**
```bash
git add modules/enterprise_knowledge/scripts/index_store.py tests/test_enterprise_knowledge_index_store.py
git commit -m "feat(enterprise_knowledge): index_store token_count payload + delete_by_doc_id + corpus_token_stats"
```

---

### Task 2: EK ingest_api — single-document ingest/remove (audit-free)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/ingest_api.py`
- Test: `tests/test_enterprise_knowledge_ingest_api.py`

**Interfaces:**
- Consumes: `IndexStore.upsert_chunks/query/corpus_token_stats/delete_by_doc_id`, `chunking.chunk_document`, `corpus.Document/knowledge_space_for`.
- Produces:
  - `ingest_document(doc_id, title, department, classification, text, owner="", knowledge_space=None, store=None) -> dict` with keys `chunks_indexed:int, doc_tokens:int, avgdl_used:float`.
  - `remove_document(doc_id, store=None) -> int`
  - `reindex_documents(docs: list[dict], store=None) -> dict` where each doc dict has `doc_id,title,department,classification,text,owner`.

- [ ] **Step 1: Write failing tests** (`tests/test_enterprise_knowledge_ingest_api.py`)

```python
"""ai_workspace-facing ingest entry: one document at a time, ACL-aware, audit-free."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"

def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod

def _store():
    from qdrant_client import QdrantClient
    index_store = _load("index_store", "ek_api_store")
    s = index_store.IndexStore(QdrantClient(":memory:"), lambda ts: [[1.0, 0.0, 0.0] for _ in ts])
    s.ensure_collection(dim=3)
    return s

def test_ingest_document_indexes_chunks_with_acl_payload():
    api = _load("ingest_api", "ek_api_1")
    s = _store()
    r = api.ingest_document("DOC900", "Chính sách nghỉ phép", "ENG", "Internal",
                            "Nhân viên được nghỉ phép theo quy định của phòng.", owner="U004", store=s)
    assert r["chunks_indexed"] >= 1 and r["doc_tokens"] > 0
    pts, _ = s._q.scroll(s._collection, with_payload=True, limit=10)
    p = pts[0].payload
    assert p["doc_id"] == "DOC900" and p["department"] == "ENG"
    assert p["classification"] == "Internal" and p["knowledge_space"] == "Department Knowledge"
    assert p["owner"] == "U004" and p["token_count"] > 0

def test_running_avgdl_accounts_for_existing_and_new():
    api = _load("ingest_api", "ek_api_2")
    s = _store()
    api.ingest_document("DOCA", "A", "ENG", "Internal", "a b c d e f", store=s)   # 6 tokens
    r = api.ingest_document("DOCB", "B", "ENG", "Internal", "x y", store=s)        # 2 tokens
    tot_tokens, tot_chunks = s.corpus_token_stats()
    assert abs(r["avgdl_used"] - tot_tokens / tot_chunks) < 1e-6

def test_ingest_empty_text_indexes_nothing():
    api = _load("ingest_api", "ek_api_3")
    s = _store()
    r = api.ingest_document("DOCE", "E", "ENG", "Internal", "   ", store=s)
    assert r["chunks_indexed"] == 0

def test_remove_document_deletes_all_its_chunks():
    api = _load("ingest_api", "ek_api_4")
    s = _store()
    api.ingest_document("DOCX", "X", "ENG", "Internal", "a b c", store=s)
    assert api.remove_document("DOCX", store=s) >= 1
    assert s.corpus_token_stats() == (0, 0)

def test_ingested_doc_respects_acl_filter():
    api = _load("ingest_api", "ek_api_5"); acl = _load("acl", "ek_api_acl")
    identity = _load("identity", "ek_api_id")
    s = _store()
    api.ingest_document("DOCH", "HR internal", "HR", "Internal", "lương thưởng nội bộ", store=s)
    other = identity.User("U", "n", "Employee", "ENG", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(other))
    assert all(h["doc_id"] != "DOCH" for h in hits)  # cross-dept Internal excluded
```

- [ ] **Step 2: Run tests to verify they fail**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_enterprise_knowledge_ingest_api.py -v`
Expected: FAIL (`ModuleNotFoundError: ingest_api`).

- [ ] **Step 3: Create `ingest_api.py`** (imports the ingest chain only — no `audit`, no `knowledge`)

```python
"""Single-document ingest entry for external callers (e.g. ai_workspace).

Deliberately slim and audit-free so it can be imported in-process without the
full CLI: it pulls in only ``chunk_document`` + ``IndexStore`` and never imports
``audit`` (a module name shared with ai_workspace) or ``knowledge``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Document, knowledge_space_for  # type: ignore[import-not-found]
from chunking import chunk_document  # type: ignore[import-not-found]
from index_store import IndexStore  # type: ignore[import-not-found]

EMBED_DIM = 1536


def _build_store() -> IndexStore:
    """Build the production IndexStore (Qdrant + index_embed embedder)."""
    from qdrant_client import QdrantClient
    from config import load_config  # type: ignore[import-not-found]
    from client import RoleClient  # type: ignore[import-not-found]

    q = QdrantClient(url=os.environ.get("EK_QDRANT_URL", "http://localhost:6333"))
    rc = RoleClient(load_config())
    store = IndexStore(q, lambda texts: rc.embed("index_embed", texts))
    store.ensure_collection(dim=int(os.environ.get("EK_EMBED_DIM", str(EMBED_DIM))))
    return store


def _to_document(doc_id, title, department, classification, text, owner, knowledge_space) -> Document:
    return Document(
        doc_id=doc_id, title=title, department=department, classification=classification,
        owner=owner or department, knowledge_space=knowledge_space or knowledge_space_for(department),
        last_updated="", language="vi", path=f"aiw://{doc_id}", text=text, tags=(),
    )


def ingest_document(
    doc_id: str, title: str, department: str, classification: str, text: str,
    owner: str = "", knowledge_space: str | None = None, store: IndexStore | None = None,
) -> dict:
    """Chunk, embed, and upsert one document; returns ingest stats.

    avgdl is a running corpus average derived from the collection's stored
    ``token_count`` plus this document's chunks (count-through, no side table).
    Empty/whitespace text indexes nothing.
    """
    if not text or not text.strip():
        return {"chunks_indexed": 0, "doc_tokens": 0, "avgdl_used": 0.0}
    doc = _to_document(doc_id, title, department, classification, text, owner, knowledge_space)
    records = chunk_document(doc)
    store = store or _build_store()
    total_tokens, total_chunks = store.corpus_token_stats()
    doc_tokens = sum(r.token_count for r in records)
    denom = total_chunks + len(records)
    avgdl = (total_tokens + doc_tokens) / denom if denom else 1.0
    n = store.upsert_chunks(records, avgdl=avgdl)
    return {"chunks_indexed": n, "doc_tokens": doc_tokens, "avgdl_used": avgdl}


def remove_document(doc_id: str, store: IndexStore | None = None) -> int:
    """Delete every chunk for ``doc_id`` from the index. Returns count removed."""
    store = store or _build_store()
    return store.delete_by_doc_id(doc_id)


def reindex_documents(docs: list[dict], store: IndexStore | None = None) -> dict:
    """Rebuild the index from ``docs`` with an exact corpus-wide avgdl.

    Each dict: ``doc_id, title, department, classification, text`` (+ optional
    ``owner``). Existing chunks for those doc_ids are removed first.
    """
    import bm25  # type: ignore[import-not-found]

    store = store or _build_store()
    all_records = []
    for d in docs:
        if not d.get("text", "").strip():
            continue
        doc = _to_document(d["doc_id"], d["title"], d["department"], d["classification"],
                           d["text"], d.get("owner", ""), None)
        store.delete_by_doc_id(d["doc_id"])
        all_records.extend(chunk_document(doc))
    if not all_records:
        return {"documents": len(docs), "chunks_indexed": 0}
    avgdl = bm25.average_length([r.text for r in all_records])
    n = store.upsert_chunks(all_records, avgdl=avgdl)
    return {"documents": len(docs), "chunks_indexed": n, "avgdl_used": avgdl}
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_enterprise_knowledge_ingest_api.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Guard test — ingest chain must not import audit**
Add to the test file:
```python
def test_ingest_api_does_not_import_audit():
    for sentinel in ("ek_api_1", "ek_api_2"):
        assert "audit" not in sys.modules.get(sentinel).__dict__
```
Run the file again; expected PASS.

- [ ] **Step 6: Commit**
```bash
git add modules/enterprise_knowledge/scripts/ingest_api.py tests/test_enterprise_knowledge_ingest_api.py
git commit -m "feat(enterprise_knowledge): slim audit-free ingest_api (ingest/remove/reindex one document)"
```

---

### Task 3: ai_workspace — index_status column + repo accessor

**Files:**
- Modify: `modules/ai_workspace/scripts/models.py`, `modules/ai_workspace/scripts/repo.py`
- Test: `tests/test_ai_workspace_db_schema.py`

**Interfaces:**
- Produces: `Document.index_status: str` (default `"pending"`); `repo.set_index_status(doc_id, status, path=None) -> bool`; `index_status` present in `repo`'s document dicts.

- [ ] **Step 1: Write failing test** (`tests/test_ai_workspace_db_schema.py`, follow its existing seed/session pattern)

```python
def test_document_has_index_status_default_pending(aiw_env):
    repo = _load("repo", "aiw_idxstatus_repo")
    repo.insert_document(doc_id="DOC900", title="t", dept_code="ENG",
                         classification_code="Internal", file_path="ENG/DOC900_t.txt",
                         original_filename="t.txt", mime_type="text/plain",
                         size_bytes=3, uploaded_by="U004")
    doc = repo.get_document("DOC900")
    assert doc["index_status"] == "pending"
    assert repo.set_index_status("DOC900", "indexed") is True
    assert repo.get_document("DOC900")["index_status"] == "indexed"
```
(If the test module has no `aiw_env` fixture, reuse the seeding/env setup used by the other `test_ai_workspace_*` tests — point `AIW_DB_PATH`/`AIW_UPLOADS_DIR` at a tmp dir and call the seeder or `initdb`.)

- [ ] **Step 2: Run to verify it fails**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_db_schema.py -k index_status -v`
Expected: FAIL (KeyError `index_status` / no attribute).

- [ ] **Step 3: Implement**
In `models.py`, add to `Document` (after `status`):
```python
    index_status: Mapped[str] = mapped_column(String(16), default="pending")
```
In `repo.py`, include `index_status` in the doc-dict builder (`_doc_dict`), and add:
```python
def set_index_status(doc_id: str, status: str, path: str | None = None) -> bool:
    """Update a document's index_status; returns False if the doc is unknown."""
    with db.session_scope(path) as session:
        doc = session.get(models.Document, doc_id)
        if doc is None:
            return False
        doc.index_status = status
        return True
```
(If `get_document`/`_doc_dict` reads explicit columns, add `"index_status": doc.index_status`.)

- [ ] **Step 4: Run to verify it passes**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_db_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add modules/ai_workspace/scripts/models.py modules/ai_workspace/scripts/repo.py tests/test_ai_workspace_db_schema.py
git commit -m "feat(ai_workspace): documents.index_status column + repo.set_index_status"
```

---

### Task 4: ai_workspace — ek_index adapter (lazy, fail-soft)

**Files:**
- Create: `modules/ai_workspace/scripts/ek_index.py`
- Test: `tests/test_ai_workspace_ek_index.py`

**Interfaces:**
- Produces: `ek_index.index_document(doc_id, title, dept_code, classification, text, owner) -> bool`; `ek_index.remove_document(doc_id) -> bool`. Both catch all exceptions and return False on failure (never raise).

- [ ] **Step 1: Write failing tests** (`tests/test_ai_workspace_ek_index.py`)

```python
"""ai_workspace → EK adapter: lazy import, fail-soft, correct metadata mapping."""
from __future__ import annotations
import importlib.util, sys, types
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"

def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod

def test_index_document_calls_ingest_api_with_mapped_args(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_1")
    calls = {}
    fake = types.ModuleType("ingest_api")
    fake.ingest_document = lambda **kw: calls.update(kw) or {"chunks_indexed": 1}
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    ok = ek_index.index_document("DOC900", "Tiêu đề", "ENG", "Internal", "nội dung", "U004")
    assert ok is True
    assert calls["doc_id"] == "DOC900" and calls["department"] == "ENG"
    assert calls["classification"] == "Internal" and calls["owner"] == "U004"

def test_index_document_returns_false_on_error(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_2")
    fake = types.ModuleType("ingest_api")
    def boom(**kw): raise RuntimeError("qdrant down")
    fake.ingest_document = boom
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.index_document("DOC900", "t", "ENG", "Internal", "x", "U004") is False

def test_remove_document_fail_soft(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_3")
    fake = types.ModuleType("ingest_api")
    fake.remove_document = lambda **kw: (_ for _ in ()).throw(RuntimeError("x"))
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.remove_document("DOC900") is False
```

- [ ] **Step 2: Run to verify they fail**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_ek_index.py -v`
Expected: FAIL (`ModuleNotFoundError: ek_index`).

- [ ] **Step 3: Create `ek_index.py`**
```python
"""Adapter to EK's ingest_api. Lazy import + fail-soft: indexing must never break
an upload. On any failure the caller marks the document index_status='failed'.
"""
from __future__ import annotations

import sys
from pathlib import Path

_EK_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "enterprise_knowledge" / "scripts"


def _api():
    """Import EK's slim ingest_api (audit-free) with EK's scripts dir on sys.path."""
    if str(_EK_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_EK_SCRIPTS))
    import ingest_api  # type: ignore[import-not-found]
    return ingest_api


def index_document(doc_id: str, title: str, dept_code: str, classification: str,
                   text: str, owner: str) -> bool:
    """Ingest one document into EK. Returns True on success, False on any failure."""
    try:
        self_api = _api()
        self_api.ingest_document(doc_id=doc_id, title=title, department=dept_code,
                                 classification=classification, text=text, owner=owner)
        return True
    except Exception:  # noqa: BLE001 - never break the upload
        return False


def remove_document(doc_id: str) -> bool:
    """Remove a document's chunks from EK. Returns True on success, else False."""
    try:
        _api().remove_document(doc_id=doc_id)
        return True
    except Exception:  # noqa: BLE001
        return False
```

- [ ] **Step 4: Run to verify they pass**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_ek_index.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add modules/ai_workspace/scripts/ek_index.py tests/test_ai_workspace_ek_index.py
git commit -m "feat(ai_workspace): ek_index adapter (lazy, fail-soft) to EK ingest_api"
```

---

### Task 5: ai_workspace — hook add/delete + index_status

**Files:**
- Modify: `modules/ai_workspace/scripts/workspace.py` (`cmd_add_document`, `cmd_delete_document`)
- Test: `tests/test_ai_workspace_upload.py` (extend)

**Interfaces:**
- Consumes: `ek_index.index_document/remove_document`, `repo.set_index_status`.
- Behaviour: after a successful upload with extractable text → call indexer, set `index_status` to `indexed`/`failed`; no text → `skipped`. After soft-delete → call remove.

- [ ] **Step 1: Write failing tests** (extend `tests/test_ai_workspace_upload.py`; monkeypatch the `ek_index` the command uses)

```python
def test_upload_text_triggers_indexing_indexed(aiw_env, monkeypatch):
    ws = _load("workspace", "aiw_up_idx1")
    seen = {}
    monkeypatch.setattr(ws.ek_index, "index_document",
                        lambda **kw: seen.update(kw) or True)
    rc = ws.cmd_add_document("U002", str(_write_tmp("policy.txt", "nội dung nghỉ phép")),
                             "Internal", "Chính sách", department=None)
    assert rc == 0
    doc = ws.repo.get_document(seen["doc_id"])
    assert doc["index_status"] == "indexed"
    assert seen["dept_code"] == "ENG" and seen["classification"] == "Internal"

def test_upload_index_failure_sets_failed_but_upload_ok(aiw_env, monkeypatch):
    ws = _load("workspace", "aiw_up_idx2")
    monkeypatch.setattr(ws.ek_index, "index_document", lambda **kw: False)
    rc = ws.cmd_add_document("U002", str(_write_tmp("p.txt", "abc")), "Internal", "P")
    assert rc == 0
    last = ws.repo.list_documents(None)[0]  # newest
    assert last["index_status"] == "failed"

def test_delete_calls_remove(aiw_env, monkeypatch):
    ws = _load("workspace", "aiw_up_idx3")
    monkeypatch.setattr(ws.ek_index, "index_document", lambda **kw: True)
    ws.cmd_add_document("U002", str(_write_tmp("p.txt", "abc")), "Internal", "P")
    doc_id = ws.repo.list_documents(None)[0]["doc_id"]
    removed = {}
    monkeypatch.setattr(ws.ek_index, "remove_document", lambda **kw: removed.update(kw) or True)
    assert ws.cmd_delete_document("U002", doc_id) == 0
    assert removed["doc_id"] == doc_id
```
(Provide `_write_tmp(name, text)` writing into a tmp dir, and reuse the module's `aiw_env` fixture that points `AIW_DB_PATH`/`AIW_UPLOADS_DIR` at tmp + seeds. U002 is a Manager.)

- [ ] **Step 2: Run to verify they fail**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_upload.py -k "index or remove" -v`
Expected: FAIL (`AttributeError: module workspace has no attribute ek_index`).

- [ ] **Step 3: Implement in `workspace.py`**
Add `import ek_index  # noqa: E402` with the other local imports.
In `cmd_add_document`, replace the tail (from text extraction through `repo.insert_document` and the final `_print`) so that after `repo.insert_document(...)` it computes the text to index and indexes:
```python
    # Resolve text to index: extracted sidecar text (non-text) or the file itself.
    index_text = ""
    if not storage.is_text(mime, src_name):
        index_text = text  # from the extraction block above (may be "")
    else:
        try:
            index_text = storage.read_text(rel)
        except OSError:
            index_text = ""

    if index_text.strip():
        ok = ek_index.index_document(doc_id=doc_id, title=doc_title, dept_code=target_dept,
                                     classification=classification, text=index_text,
                                     owner=user.user_id)
        index_status = "indexed" if ok else "failed"
    else:
        index_status = "skipped"
    repo.set_index_status(doc_id, index_status)
```
Add `"index_status": index_status` to the `_print({...})` upload payload and to the audit event.
In `cmd_delete_document`, after `repo.set_document_status(doc_id, "deleted")`:
```python
    ek_index.remove_document(doc_id=doc_id)
```

- [ ] **Step 4: Run to verify they pass**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_upload.py -v`
Expected: PASS (including pre-existing upload tests).

- [ ] **Step 5: Commit**
```bash
git add modules/ai_workspace/scripts/workspace.py tests/test_ai_workspace_upload.py
git commit -m "feat(ai_workspace): index on upload + remove on delete, tracking index_status"
```

---

### Task 6: ai_workspace — reindex command

**Files:**
- Modify: `modules/ai_workspace/scripts/workspace.py` (`cmd_reindex` + subparser + dispatch), `modules/ai_workspace/scripts/ek_index.py` (`reindex`)
- Test: `tests/test_ai_workspace_ek_index.py` (extend)

**Interfaces:**
- Produces: `ek_index.reindex(docs: list[dict]) -> bool`; `cmd_reindex(user_id) -> int` (Executive only).

- [ ] **Step 1: Write failing test**
```python
def test_reindex_executive_only(aiw_env, monkeypatch):
    ws = _load("workspace", "aiw_reidx1")
    monkeypatch.setattr(ws.ek_index, "reindex", lambda docs: True)
    assert ws.cmd_reindex("U002") == 1   # Manager denied
    assert ws.cmd_reindex("U007") == 0   # Executive ok

def test_ek_index_reindex_forwards(monkeypatch):
    ek_index = _load("ek_index", "aiw_reidx2")
    import types
    fake = types.ModuleType("ingest_api")
    got = {}
    fake.reindex_documents = lambda docs, **kw: got.update({"n": len(docs)}) or {"chunks_indexed": 1}
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.reindex([{"doc_id": "DOCA", "title": "t", "department": "ENG",
                              "classification": "Internal", "text": "a b"}]) is True
    assert got["n"] == 1
```

- [ ] **Step 2: Run to verify fail**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_ek_index.py -k reindex -v`
Expected: FAIL.

- [ ] **Step 3: Implement**
In `ek_index.py`:
```python
def reindex(docs: list[dict]) -> bool:
    """Rebuild the index from a list of active-document dicts. False on failure."""
    try:
        _api().reindex_documents(docs)
        return True
    except Exception:  # noqa: BLE001
        return False
```
In `workspace.py` add `cmd_reindex` and wire the subparser + dispatch:
```python
def cmd_reindex(user_id: str) -> int:
    """Rebuild the EK index from all active documents (Executive only)."""
    user = _require_user(user_id)
    if user.role != "Executive":
        _print({"reindexed": False, "reason": "cần Executive"})
        return 1
    docs = []
    for d in repo.list_documents(None):
        rel = d.get("file_path", "")
        sidecar = storage.sidecar_path(rel)
        text = ""
        try:
            if storage.exists(sidecar):
                text = storage.read_text(sidecar)
            elif rel and storage.is_text(d.get("mime_type", ""), d.get("original_filename", "")):
                text = storage.read_text(rel)
        except OSError:
            text = ""
        docs.append({"doc_id": d["doc_id"], "title": d["title"], "department": d["department"],
                     "classification": d["classification"], "text": text, "owner": d.get("uploaded_by", "")})
    ok = ek_index.reindex(docs)
    for d in docs:
        repo.set_index_status(d["doc_id"], "indexed" if (ok and d["text"].strip()) else
                              ("skipped" if not d["text"].strip() else "failed"))
    _print({"reindexed": ok, "documents": len(docs)})
    return 0 if ok else 1
```
Add subparser `sub.add_parser("reindex", ...)` with `--user`, and dispatch `elif args.command == "reindex": return cmd_reindex(args.user)`.

- [ ] **Step 4: Run to verify pass**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_ek_index.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add modules/ai_workspace/scripts/workspace.py modules/ai_workspace/scripts/ek_index.py tests/test_ai_workspace_ek_index.py
git commit -m "feat(ai_workspace): reindex command (Executive) to rebuild EK index"
```

---

### Task 7: Dependencies + full suite + format

**Files:**
- Modify: `modules/ai_workspace/requirements.txt`

- [ ] **Step 1: Add deps** — append to `modules/ai_workspace/requirements.txt`:
```
qdrant-client>=1.11
chonkie>=1.0
openai>=1.40
```

- [ ] **Step 2: Format + lint**
Run: `uv run black modules/ai_workspace/scripts modules/enterprise_knowledge/scripts/ingest_api.py modules/enterprise_knowledge/scripts/index_store.py tests/test_ai_workspace_ek_index.py tests/test_enterprise_knowledge_ingest_api.py`
Run: `uv run ruff check modules/ai_workspace/scripts modules/enterprise_knowledge/scripts/ingest_api.py`
Expected: all checks pass.

- [ ] **Step 3: Full suite**
Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_ai_workspace_*.py tests/test_enterprise_knowledge_*.py -q`
Expected: PASS (all).

- [ ] **Step 4: Commit**
```bash
git add modules/ai_workspace/requirements.txt
git commit -m "chore(ai_workspace): add qdrant-client/chonkie/openai for in-process EK ingest"
```

---

## Manual end-to-end verification (after all tasks; requires Qdrant + embed API per CLAUDE.md)
1. `export OPENAI_API_KEY=...` and EK env (`EK_QDRANT_URL`, `EK_INDEX_EMBED_*`, `EK_EMBED_DIM`); start Qdrant.
2. Seed ai_workspace, then upload a doc: `python modules/ai_workspace/scripts/workspace.py add-document --user U002 --file <some.pdf> Internal "Test"`. Confirm JSON shows `index_status: indexed`.
3. Query EK for content of that doc as an in-department user → returned; as an out-of-department Employee → not returned (ACL).
4. Delete the doc → confirm EK query no longer returns it.
```
```
