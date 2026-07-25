# Core Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-core, per-tenant knowledge base so users can dump PDF/text/markdown documents that core auto-ingests into hybrid vector + full-text search plus a Neo4j knowledge graph, exposes to the agent via a `knowledge_query` tool, and injects tenant persona/background into the agent prompt.

**Architecture:** New package `minder/core/knowledge/` reusing the existing search framework (`minder/core/context_engineering/search/`: `Embedder`, `DenseIndex`, `pg`, `rrf_fuse`), the Postgres ORM layer, the artifact upload path, the Keycloak principal, and the in-process `BackgroundScheduler`. Ingestion runs in the background off a DB-polled `pending` queue fed by both API upload and a mounted seed folder. Graph writes are best-effort and toggleable.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (asyncpg), Qdrant (`qdrant-client`), Neo4j (`neo4j` driver), Postgres FTS, OpenAI-compatible embeddings + chat, pytest (`uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-07-17-core-knowledge-base-design.md`

## Global Constraints

- Line length 100 (Black + Ruff); type hints on public APIs (mypy strict); Google-style docstrings. (from CLAUDE.md)
- Tests run with `uv run pytest`; unit tests must not require Qdrant/Neo4j (inject fakes). Integration/e2e use real services + `OPENAI_API_KEY`. (from CLAUDE.md + spec §11)
- `tenant_id` is always taken from `CurrentPrincipal.tenant_id`, never a model-supplied parameter. Dev fallback: `KNOWLEDGE_DEV_TENANT` only when `MINDER_ENV=dev`. (spec §2, §9)
- Categories (v1, exact names): `persona`, `company_background`, `reference_docs`. (spec §4)
- Qdrant: single collection `knowledge_chunks`, cosine; every query hard-filters `tenant_id` (+ `category`). (spec §4)
- Neo4j nodes namespaced `:KDocument`/`:KChunk`/`:KEntity`, every node carries `tenant_id`; relation `RELATED_TO` has `confidence` + `status="unverified"`. (spec §4)
- Env vars (already wired in `docker-compose.dev.yml`): `QDRANT_URL`, `KNOWLEDGE_NEO4J_URI`, `KNOWLEDGE_NEO4J_USER`, `KNOWLEDGE_NEO4J_PASSWORD`, `KNOWLEDGE_GRAPH_ENABLED`, `KNOWLEDGE_GRAPH_HOPS` (default 2), `KNOWLEDGE_SEED_DIR`, `KNOWLEDGE_DEV_TENANT`, plus existing `SEARCH_EMBED_*`/`OPENAI_API_KEY`, `DATABASE_URL`. (spec §9)
- Idempotency: a document is keyed by `content_hash` (sha256 of file bytes); re-ingest never duplicates. (spec §5)
- Fail-safe: ingest failures set `status="failed"` + `error` and never abort sibling jobs; Neo4j/summary failures never block chunk storage. (spec §8)

## File Structure

- `minder/core/knowledge/__init__.py` — package marker + public exports.
- `minder/core/knowledge/categories.py` — `Category` enum + per-category behavior table.
- `minder/core/knowledge/chunking.py` — `chunk_text()` paragraph-packing chunker.
- `minder/core/knowledge/parsing.py` — `parse_file()` → plain text for pdf/text/md.
- `minder/core/knowledge/models.py` — dataclasses: `IngestJob`, `Chunk`, `Hit` (transport types; ORM lives in `db/models.py`).
- `minder/core/knowledge/embedding.py` — `KnowledgeEmbedder` thin wrapper over `Embedder` + `DenseIndex` with the fixed collection.
- `minder/core/knowledge/graph.py` — `KnowledgeGraph` (Neo4j build + 2-hop expand) + pure `merge_graph_hits()`.
- `minder/core/knowledge/summarize.py` — `summarize_document()` (LLM) for persona/background.
- `minder/core/knowledge/ingestion.py` — `IngestionService.ingest_document()` orchestration.
- `minder/core/knowledge/seed.py` — `scan_seed_dir()` folder → enqueue diff.
- `minder/core/knowledge/provider.py` — `DocumentsProvider(SearchProvider)`.
- `minder/core/knowledge/profile.py` — `ProfileInjector.build_profile_block()`.
- `minder/core/knowledge/service.py` — `KnowledgeService` (list/create/reingest/delete + queue drain).
- `minder/core/knowledge/tool.py` — `build_knowledge_tool_spec()` → `ToolSpec`.
- `minder/core/knowledge/repository.py` — `KnowledgeRepository` (Postgres CRUD).
- `minder/db/models.py` — add `KnowledgeDocument`, `KnowledgeChunk` ORM (modify).
- `minder/db/connection.py` — add GIN expression index in `init_schema()` (modify).
- `minder/core/context_engineering/tools/registry.py` — register knowledge `ToolSpec` (modify).
- `minder/core/agents/assistant_agent.py` — inject profile block (modify).
- `minder/web/routes/knowledge.py` — `/knowledge/rescan`, `/knowledge/documents` (create).
- `minder/web/server.py` (or app factory) — schedule seed scan + queue drain (modify).
- `minder/cli.py` — `minder knowledge …` subcommands (modify).
- `tests/knowledge/…` — unit tests; `tests/knowledge/test_integration_*.py` — integration.

---

### Task 1: Category behavior table

**Files:**
- Create: `minder/core/knowledge/__init__.py`
- Create: `minder/core/knowledge/categories.py`
- Test: `tests/knowledge/test_categories.py`

**Interfaces:**
- Produces: `class Category(str, Enum)` with members `PERSONA="persona"`, `COMPANY_BACKGROUND="company_background"`, `REFERENCE_DOCS="reference_docs"`; `@dataclass(frozen=True) CategoryBehavior(inject: bool, build_graph: bool, summarize: bool)`; `BEHAVIOR: dict[Category, CategoryBehavior]`; `behavior_for(name: str) -> CategoryBehavior`; `is_valid_category(name: str) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_categories.py
import pytest
from minder.core.knowledge.categories import (
    Category,
    behavior_for,
    is_valid_category,
)


def test_reference_docs_retrieves_and_graphs():
    b = behavior_for("reference_docs")
    assert b.inject is False
    assert b.build_graph is True
    assert b.summarize is False


def test_persona_injects_and_summarizes_no_graph():
    b = behavior_for("persona")
    assert b.inject is True
    assert b.summarize is True
    assert b.build_graph is False


def test_company_background_matches_persona_behavior():
    assert behavior_for("company_background").inject is True
    assert behavior_for("company_background").build_graph is False


def test_unknown_category_rejected():
    assert is_valid_category("reference_docs") is True
    assert is_valid_category("nope") is False
    with pytest.raises(ValueError):
        behavior_for("nope")


def test_category_enum_values_are_stable_strings():
    assert Category.PERSONA.value == "persona"
    assert Category.REFERENCE_DOCS.value == "reference_docs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_categories.py -v`
Expected: FAIL with `ModuleNotFoundError: minder.core.knowledge.categories`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/__init__.py
"""Core per-tenant knowledge base: ingestion, retrieval, graph, profile."""
```

```python
# minder/core/knowledge/categories.py
"""Knowledge categories and their per-category ingestion/retrieval behavior."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Category(str, Enum):
    """The knowledge categories a document can belong to."""

    PERSONA = "persona"
    COMPANY_BACKGROUND = "company_background"
    REFERENCE_DOCS = "reference_docs"


@dataclass(frozen=True)
class CategoryBehavior:
    """How a category is treated.

    Attributes:
        inject: Summary is injected into the agent system prompt.
        build_graph: Chunks feed the Neo4j knowledge graph.
        summarize: The whole document is LLM-summarized on ingest.
    """

    inject: bool
    build_graph: bool
    summarize: bool


BEHAVIOR: dict[Category, CategoryBehavior] = {
    Category.PERSONA: CategoryBehavior(inject=True, build_graph=False, summarize=True),
    Category.COMPANY_BACKGROUND: CategoryBehavior(inject=True, build_graph=False, summarize=True),
    Category.REFERENCE_DOCS: CategoryBehavior(inject=False, build_graph=True, summarize=False),
}


def is_valid_category(name: str) -> bool:
    """Return True if `name` is a known category value."""
    return name in Category._value2member_map_


def behavior_for(name: str) -> CategoryBehavior:
    """Return the behavior for a category value, raising ValueError if unknown."""
    if not is_valid_category(name):
        raise ValueError(f"Unknown knowledge category: {name!r}")
    return BEHAVIOR[Category(name)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_categories.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/__init__.py minder/core/knowledge/categories.py tests/knowledge/test_categories.py
git commit -m "feat(knowledge): category behavior table"
```

---

### Task 2: Paragraph-packing chunker

**Files:**
- Create: `minder/core/knowledge/chunking.py`
- Test: `tests/knowledge/test_chunking.py`

**Interfaces:**
- Produces: `chunk_text(text: str, max_chars: int = 900) -> list[str]` — splits on blank lines, greedily packs paragraphs up to `max_chars`; a single over-long paragraph is kept whole; empty/whitespace input → `[]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_chunking.py
from minder.core.knowledge.chunking import chunk_text


def test_empty_input_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_paragraphs_pack_up_to_limit():
    text = "aaa\n\nbbb\n\nccc"
    chunks = chunk_text(text, max_chars=8)
    # "aaa\n\nbbb" = 8 chars fits; "ccc" starts a new chunk
    assert chunks == ["aaa\n\nbbb", "ccc"]


def test_oversized_paragraph_kept_whole():
    big = "x" * 50
    chunks = chunk_text(big, max_chars=10)
    assert chunks == [big]


def test_all_text_preserved_in_order():
    text = "one\n\ntwo\n\nthree"
    joined = "\n\n".join(chunk_text(text, max_chars=3))
    assert "one" in joined and "two" in joined and "three" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/chunking.py
"""Paragraph-packing chunker for ingested documents."""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 900) -> list[str]:
    """Split on blank lines and greedily pack paragraphs up to max_chars.

    A single paragraph longer than max_chars is kept whole. Returns an empty
    list when the text has no non-blank paragraphs.

    Args:
        text: Source text; paragraphs are delimited by blank lines.
        max_chars: Soft cap on chunk length in characters.

    Returns:
        Chunk strings in original order.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_chunking.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/chunking.py tests/knowledge/test_chunking.py
git commit -m "feat(knowledge): paragraph-packing chunker"
```

---

### Task 3: File parsing (pdf / text / md → plain text)

**Files:**
- Create: `minder/core/knowledge/parsing.py`
- Test: `tests/knowledge/test_parsing.py`

**Interfaces:**
- Consumes: `pypdf` (already a dependency).
- Produces: `parse_file(path: str) -> str` — dispatches by extension. `.txt`/`.md` read as UTF-8; `.pdf` extracted with pypdf (pages joined by blank lines). Unknown extension raises `ValueError`. `SUPPORTED_EXTENSIONS: frozenset[str]` = `{".pdf", ".txt", ".md"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_parsing.py
import pytest
from minder.core.knowledge.parsing import SUPPORTED_EXTENSIONS, parse_file


def test_reads_markdown(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nBody text", encoding="utf-8")
    assert "Body text" in parse_file(str(p))


def test_reads_plain_text(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")
    assert parse_file(str(p)) == "hello world"


def test_unknown_extension_rejected(tmp_path):
    p = tmp_path / "a.docx"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(str(p))


def test_supported_extensions_set():
    assert ".pdf" in SUPPORTED_EXTENSIONS and ".md" in SUPPORTED_EXTENSIONS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_parsing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/parsing.py
"""Extract plain text from ingested files (pdf / text / markdown)."""

from __future__ import annotations

import os

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".txt", ".md"})


def parse_file(path: str) -> str:
    """Return the plain-text content of a supported file.

    Args:
        path: Absolute path to a `.pdf`, `.txt`, or `.md` file.

    Returns:
        Extracted UTF-8 text.

    Raises:
        ValueError: The extension is not supported.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext!r}")
    if ext == ".pdf":
        return _parse_pdf(path)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_pdf(path: str) -> str:
    """Extract text from every page of a PDF, joined by blank lines."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_parsing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/parsing.py tests/knowledge/test_parsing.py
git commit -m "feat(knowledge): file parsing for pdf/text/md"
```

---

### Task 4: ORM tables + GIN full-text index

**Files:**
- Modify: `minder/db/models.py` (append two model classes at end of file)
- Modify: `minder/db/connection.py:83-104` (`init_schema`) — add a GIN expression index
- Test: `tests/knowledge/test_models.py`

**Interfaces:**
- Produces ORM classes `KnowledgeDocument` (`__tablename__ = "knowledge_documents"`) and `KnowledgeChunk` (`__tablename__ = "knowledge_chunks"`) on the existing `Base`. No stored `tsv` column — full-text is an expression index over `text` created in `init_schema()`.

Columns — `knowledge_documents`: `id int pk`, `tenant_id str(128) index`, `category str(40)`, `title str(512)`, `artifact_id int nullable`, `source_path text nullable`, `source_filename str(512) nullable`, `content_hash str(64) index`, `status str(16) default "pending"`, `error text nullable`, `summary text nullable`, `created_at`, `updated_at`.

Columns — `knowledge_chunks`: `id int pk`, `document_id int FK→knowledge_documents.id index`, `tenant_id str(128) index`, `category str(40)`, `chunk_index int`, `text text`, `qdrant_point_id str(64) nullable`, `citation text`, `created_at`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_models.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from minder.db.models import Base, KnowledgeChunk, KnowledgeDocument


@pytest.mark.asyncio
async def test_document_and_chunk_roundtrip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        doc = KnowledgeDocument(
            tenant_id="t1",
            category="reference_docs",
            title="Policy",
            content_hash="abc",
            status="pending",
        )
        s.add(doc)
        await s.flush()
        s.add(
            KnowledgeChunk(
                document_id=doc.id,
                tenant_id="t1",
                category="reference_docs",
                chunk_index=0,
                text="hello",
                citation="Policy [1] · 1#0",
            )
        )
        await s.commit()
        assert doc.id is not None
        assert doc.status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'KnowledgeDocument'`

- [ ] **Step 3: Write minimal implementation**

Append to `minder/db/models.py` (uses imports already at the top of that file):

```python
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    qdrant_point_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
```

In `minder/db/connection.py`, inside `init_schema()`, after the legacy-drop loop and before the `messages.role` widen block, add a Postgres-only GIN expression index (guarded so sqlite/other backends are unaffected):

```python
    # Full-text index for knowledge chunks (Postgres only). Expression index over
    # to_tsvector('simple', text) so the provider can run websearch_to_tsquery.
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS knowledge_chunks_fts "
                    "ON knowledge_chunks USING gin (to_tsvector('simple', text))"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create knowledge_chunks FTS index: %s", exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_models.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/db/models.py minder/db/connection.py tests/knowledge/test_models.py
git commit -m "feat(knowledge): knowledge_documents/knowledge_chunks tables + FTS index"
```

---

### Task 5: Repository (Postgres CRUD + FTS query)

**Files:**
- Create: `minder/core/knowledge/repository.py`
- Test: `tests/knowledge/test_repository.py`

**Interfaces:**
- Consumes: `get_sessionmaker()` from `minder.db.connection`; ORM from Task 4; `pg.fetch_all` from `minder.core.context_engineering.search.pg`; `normalize_for_search` from `minder.core.context_engineering.search.normalize`.
- Produces: `class KnowledgeRepository` with:
  - `async create_document(tenant_id, category, title, content_hash, *, artifact_id=None, source_path=None, source_filename=None) -> int`
  - `async find_document_by_hash(tenant_id, content_hash) -> dict | None`
  - `async set_status(document_id, status, *, error=None) -> None`
  - `async set_summary(document_id, summary) -> None`
  - `async replace_chunks(document_id, tenant_id, category, chunks: list[tuple[int, str, str, str]]) -> None` where each tuple is `(chunk_index, text, qdrant_point_id, citation)`
  - `async list_documents(tenant_id) -> list[dict]`
  - `async delete_document(document_id) -> list[str]` (returns deleted chunks' `qdrant_point_id`s)
  - `async pending_document_ids(limit=5) -> list[int]`
  - `fts_search(tenant_id, category, query, limit) -> list[str]` (sync; returns chunk external ids `"{document_id}#{chunk_index}"` ranked by ts_rank) — uses `pg.fetch_all`.

Note: async CRUD tested against sqlite; `fts_search` is Postgres-only and covered in the integration task (Task 15).

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_repository.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from minder.core.knowledge.repository import KnowledgeRepository
from minder.db.models import Base


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_find_and_status(sm):
    repo = KnowledgeRepository(sm)
    doc_id = await repo.create_document("t1", "reference_docs", "Doc", "hash1")
    found = await repo.find_document_by_hash("t1", "hash1")
    assert found["id"] == doc_id and found["status"] == "pending"
    await repo.set_status(doc_id, "ready")
    assert (await repo.find_document_by_hash("t1", "hash1"))["status"] == "ready"


@pytest.mark.asyncio
async def test_replace_chunks_and_delete_returns_point_ids(sm):
    repo = KnowledgeRepository(sm)
    doc_id = await repo.create_document("t1", "reference_docs", "Doc", "hash1")
    await repo.replace_chunks(
        doc_id, "t1", "reference_docs",
        [(0, "text a", "pt-0", "Doc [1] · 1#0"), (1, "text b", "pt-1", "Doc [1] · 1#1")],
    )
    point_ids = await repo.delete_document(doc_id)
    assert sorted(point_ids) == ["pt-0", "pt-1"]
    assert await repo.find_document_by_hash("t1", "hash1") is None


@pytest.mark.asyncio
async def test_pending_ids_and_tenant_isolation(sm):
    repo = KnowledgeRepository(sm)
    a = await repo.create_document("t1", "faq" if False else "reference_docs", "A", "h1")
    await repo.create_document("t2", "reference_docs", "B", "h2")
    pending = await repo.pending_document_ids(limit=10)
    assert a in pending
    assert [d["title"] for d in await repo.list_documents("t1")] == ["A"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/repository.py
"""Postgres persistence for knowledge documents and chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from minder.core.context_engineering.search import pg
from minder.core.context_engineering.search.normalize import normalize_for_search
from minder.db.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    """CRUD for knowledge documents/chunks plus Postgres FTS recall."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def create_document(
        self,
        tenant_id: str,
        category: str,
        title: str,
        content_hash: str,
        *,
        artifact_id: int | None = None,
        source_path: str | None = None,
        source_filename: str | None = None,
    ) -> int:
        async with self._sm() as s:
            doc = KnowledgeDocument(
                tenant_id=tenant_id,
                category=category,
                title=title,
                content_hash=content_hash,
                artifact_id=artifact_id,
                source_path=source_path,
                source_filename=source_filename,
                status="pending",
            )
            s.add(doc)
            await s.commit()
            return doc.id

    async def find_document_by_hash(self, tenant_id: str, content_hash: str) -> dict[str, Any] | None:
        async with self._sm() as s:
            row = (
                await s.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == tenant_id,
                        KnowledgeDocument.content_hash == content_hash,
                    )
                )
            ).scalar_one_or_none()
            return _doc_to_dict(row) if row else None

    async def set_status(self, document_id: int, status: str, *, error: str | None = None) -> None:
        async with self._sm() as s:
            await s.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(status=status, error=error)
            )
            await s.commit()

    async def set_summary(self, document_id: int, summary: str) -> None:
        async with self._sm() as s:
            await s.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(summary=summary)
            )
            await s.commit()

    async def replace_chunks(
        self,
        document_id: int,
        tenant_id: str,
        category: str,
        chunks: list[tuple[int, str, str, str]],
    ) -> None:
        async with self._sm() as s:
            await s.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )
            for chunk_index, text, point_id, citation in chunks:
                s.add(
                    KnowledgeChunk(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        category=category,
                        chunk_index=chunk_index,
                        text=text,
                        qdrant_point_id=point_id,
                        citation=citation,
                    )
                )
            await s.commit()

    async def list_documents(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.tenant_id == tenant_id)
                    .order_by(KnowledgeDocument.id)
                )
            ).scalars()
            return [_doc_to_dict(r) for r in rows]

    async def summaries_for_inject(self, tenant_id: str, categories: list[str]) -> list[dict[str, Any]]:
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == tenant_id,
                        KnowledgeDocument.category.in_(categories),
                        KnowledgeDocument.status == "ready",
                    )
                )
            ).scalars()
            return [_doc_to_dict(r) for r in rows if r.summary]

    async def delete_document(self, document_id: int) -> list[str]:
        async with self._sm() as s:
            point_ids = [
                pid
                for pid in (
                    await s.execute(
                        select(KnowledgeChunk.qdrant_point_id).where(
                            KnowledgeChunk.document_id == document_id
                        )
                    )
                ).scalars()
                if pid
            ]
            await s.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
            await s.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
            )
            await s.commit()
            return point_ids

    async def pending_document_ids(self, limit: int = 5) -> list[int]:
        async with self._sm() as s:
            return list(
                (
                    await s.execute(
                        select(KnowledgeDocument.id)
                        .where(KnowledgeDocument.status == "pending")
                        .order_by(KnowledgeDocument.id)
                        .limit(limit)
                    )
                ).scalars()
            )

    def fts_search(self, tenant_id: str, category: str, query: str, limit: int) -> list[str]:
        """Return chunk external ids ('{document_id}#{chunk_index}') by FTS rank."""
        normalized = normalize_for_search(query)
        rows = pg.fetch_all(
            "SELECT document_id, chunk_index "
            "FROM knowledge_chunks "
            "WHERE tenant_id = $1 AND category = $2 "
            "AND to_tsvector('simple', text) @@ websearch_to_tsquery('simple', $3) "
            "ORDER BY ts_rank(to_tsvector('simple', text), "
            "websearch_to_tsquery('simple', $3)) DESC "
            "LIMIT $4",
            [tenant_id, category, normalized, limit],
        )
        return [f"{r['document_id']}#{r['chunk_index']}" for r in rows]


def _doc_to_dict(doc: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "category": doc.category,
        "title": doc.title,
        "content_hash": doc.content_hash,
        "status": doc.status,
        "error": doc.error,
        "summary": doc.summary,
        "artifact_id": doc.artifact_id,
        "source_path": doc.source_path,
        "source_filename": doc.source_filename,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_repository.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/repository.py tests/knowledge/test_repository.py
git commit -m "feat(knowledge): repository CRUD + FTS query"
```

---

### Task 6: Embedding/vector wrapper

**Files:**
- Create: `minder/core/knowledge/embedding.py`
- Test: `tests/knowledge/test_embedding.py`

**Interfaces:**
- Consumes: `Embedder` and `DenseIndex` from `minder.core.context_engineering.search`.
- Produces: `class KnowledgeEmbedder` with constructor `(embedder=None, index=None)` (defaults construct real `Embedder()`/`DenseIndex("knowledge_chunks")`); `COLLECTION = "knowledge_chunks"`; methods:
  - `embed_query(text: str) -> list[float]`
  - `index_chunks(external_ids, texts, payloads) -> None` (ensures collection dim from the first vector, then upserts)
  - `delete(external_ids: list[str]) -> None`
  - `search(query_vector, tenant_id, category, limit) -> list[tuple[str, float, dict]]` (builds the Qdrant filter on `tenant_id`+`category`).
- Filter helper `tenant_category_filter(tenant_id, category)` returns a `qdrant_client.models.Filter`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_embedding.py
from minder.core.knowledge.embedding import KnowledgeEmbedder


class FakeEmbedder:
    def embed(self, texts):
        return [[float(len(t)), 1.0, 0.0] for t in texts]


class FakeIndex:
    def __init__(self):
        self.ensured = None
        self.upserts = []
        self.deleted = []

    def ensure(self, dim):
        self.ensured = dim

    def upsert(self, ids, vectors, payloads):
        self.upserts.append((ids, vectors, payloads))

    def delete(self, ids):
        self.deleted.extend(ids)


def test_index_chunks_ensures_dim_and_upserts():
    idx = FakeIndex()
    ke = KnowledgeEmbedder(embedder=FakeEmbedder(), index=idx)
    ke.index_chunks(["1#0"], ["hello"], [{"tenant_id": "t1"}])
    assert idx.ensured == 3
    assert idx.upserts[0][0] == ["1#0"]


def test_embed_query_returns_vector():
    ke = KnowledgeEmbedder(embedder=FakeEmbedder(), index=FakeIndex())
    assert ke.embed_query("abcd")[0] == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_embedding.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/embedding.py
"""Embedding + Qdrant wrapper bound to the knowledge_chunks collection."""

from __future__ import annotations

from typing import Any

from qdrant_client import models

from minder.core.context_engineering.search.dense import DenseIndex
from minder.core.context_engineering.search.embedder import Embedder

COLLECTION = "knowledge_chunks"


def tenant_category_filter(tenant_id: str, category: str) -> models.Filter:
    """Qdrant hard filter scoping a query to one tenant + category."""
    return models.Filter(
        must=[
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
            models.FieldCondition(key="category", match=models.MatchValue(value=category)),
        ]
    )


class KnowledgeEmbedder:
    """Generate embeddings and read/write the knowledge_chunks collection."""

    COLLECTION = COLLECTION

    def __init__(self, embedder: Any = None, index: Any = None) -> None:
        self._embedder = embedder or Embedder()
        self._index = index or DenseIndex(COLLECTION)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed([text])[0]

    def index_chunks(
        self, external_ids: list[str], texts: list[str], payloads: list[dict[str, Any]]
    ) -> None:
        if not texts:
            return
        vectors = self._embedder.embed(texts)
        self._index.ensure(len(vectors[0]))
        self._index.upsert(external_ids, vectors, payloads)

    def delete(self, external_ids: list[str]) -> None:
        self._index.delete(external_ids)

    def search(
        self, query_vector: list[float], tenant_id: str, category: str, limit: int
    ) -> list[tuple[str, float, dict[str, Any]]]:
        return self._index.query(
            query_vector, tenant_category_filter(tenant_id, category), limit
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_embedding.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/embedding.py tests/knowledge/test_embedding.py
git commit -m "feat(knowledge): embedding + qdrant wrapper"
```

---

### Task 7: Knowledge graph (best-effort Neo4j + pure merge)

**Files:**
- Create: `minder/core/knowledge/graph.py`
- Test: `tests/knowledge/test_graph.py`

**Interfaces:**
- Consumes: `neo4j` driver (lazy import); env `KNOWLEDGE_NEO4J_URI/USER/PASSWORD`, `KNOWLEDGE_GRAPH_ENABLED`, `KNOWLEDGE_GRAPH_HOPS`.
- Produces:
  - Pure function `merge_graph_hits(vector_ids: list[str], graph_ids: list[str], cap: int, boost: float = 0.1) -> list[str]` — vector ids lead (deduped, order preserved), then graph-only ids, truncated to `cap`.
  - `graph_enabled() -> bool` (reads `KNOWLEDGE_GRAPH_ENABLED`).
  - `class KnowledgeGraph` with `(driver=None)`; `build_chunk(tenant_id, document_id, chunk_index, text, entities: list[tuple[str,str]], relations: list[tuple[str,str,float]]) -> None` and `expand(tenant_id, seed_ids: list[str], hops: int, max_neighbors: int) -> list[str]`. Both no-op/`[]` when the driver is unavailable (best-effort). Neo4j I/O is exercised in Task 15; unit tests cover `merge_graph_hits` + `graph_enabled`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_graph.py
import os

from minder.core.knowledge.graph import graph_enabled, merge_graph_hits


def test_merge_prefers_vector_then_graph_and_dedupes():
    merged = merge_graph_hits(["a", "b"], ["b", "c", "d"], cap=3)
    assert merged == ["a", "b", "c"]


def test_merge_truncates_to_cap():
    assert merge_graph_hits(["a"], ["b", "c"], cap=2) == ["a", "b"]


def test_graph_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_GRAPH_ENABLED", "1")
    assert graph_enabled() is True
    monkeypatch.setenv("KNOWLEDGE_GRAPH_ENABLED", "0")
    assert graph_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/graph.py
"""Best-effort Neo4j knowledge graph: build on ingest, expand on query."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def graph_enabled() -> bool:
    """True if graph writes/expansion are turned on via env."""
    return os.environ.get("KNOWLEDGE_GRAPH_ENABLED", "0") == "1"


def graph_hops() -> int:
    """Configured traversal depth (default 2)."""
    try:
        return int(os.environ.get("KNOWLEDGE_GRAPH_HOPS", "2"))
    except ValueError:
        return 2


def merge_graph_hits(
    vector_ids: list[str], graph_ids: list[str], cap: int, boost: float = 0.1
) -> list[str]:
    """Vector ids lead (deduped, order preserved); graph-only ids follow; cap total.

    `boost` is reserved for score-aware callers; ordering already encodes the
    "vector leads" preference, so graph ids never displace vector ids.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for external_id in [*vector_ids, *graph_ids]:
        if external_id in seen:
            continue
        seen.add(external_id)
        merged.append(external_id)
        if len(merged) >= cap:
            break
    return merged


class KnowledgeGraph:
    """Thin Neo4j wrapper; every method degrades to a no-op if Neo4j is down."""

    def __init__(self, driver: Any = None) -> None:
        self._driver = driver if driver is not None else _connect()

    def build_chunk(
        self,
        tenant_id: str,
        document_id: int,
        chunk_index: int,
        text: str,
        entities: list[tuple[str, str]],
        relations: list[tuple[str, str, float]],
    ) -> None:
        if self._driver is None:
            return
        chunk_id = f"{document_id}#{chunk_index}"
        try:
            with self._driver.session() as session:
                session.execute_write(
                    _write_chunk, tenant_id, document_id, chunk_id, entities, relations
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph build_chunk failed for %s: %s", chunk_id, exc)

    def expand(
        self, tenant_id: str, seed_ids: list[str], hops: int, max_neighbors: int
    ) -> list[str]:
        if self._driver is None or not seed_ids:
            return []
        try:
            with self._driver.session() as session:
                return session.execute_read(
                    _expand, tenant_id, seed_ids, hops, max_neighbors
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph expand failed: %s", exc)
            return []


def _connect() -> Any:
    uri = os.environ.get("KNOWLEDGE_NEO4J_URI")
    if not uri or not graph_enabled():
        return None
    try:
        from neo4j import GraphDatabase

        return GraphDatabase.driver(
            uri,
            auth=(
                os.environ.get("KNOWLEDGE_NEO4J_USER", "neo4j"),
                os.environ.get("KNOWLEDGE_NEO4J_PASSWORD", ""),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Neo4j unavailable, graph disabled: %s", exc)
        return None


def _write_chunk(tx, tenant_id, document_id, chunk_id, entities, relations):
    tx.run(
        "MERGE (c:KChunk {chunk_id:$chunk_id}) SET c.tenant_id=$tenant_id, c.document_id=$doc",
        chunk_id=chunk_id, tenant_id=tenant_id, doc=document_id,
    )
    for key, etype in entities:
        tx.run(
            "MERGE (e:KEntity {key:$key}) SET e.tenant_id=$tenant_id, e.type=$etype "
            "WITH e MATCH (c:KChunk {chunk_id:$chunk_id}) MERGE (c)-[:MENTIONS]->(e)",
            key=key, etype=etype, tenant_id=tenant_id, chunk_id=chunk_id,
        )
    for src, dst, confidence in relations:
        tx.run(
            "MATCH (a:KEntity {key:$src}), (b:KEntity {key:$dst}) "
            "MERGE (a)-[r:RELATED_TO]->(b) "
            "SET r.confidence=$confidence, r.status='unverified'",
            src=src, dst=dst, confidence=confidence,
        )


def _expand(tx, tenant_id, seed_ids, hops, max_neighbors):
    result = tx.run(
        "MATCH (c:KChunk)-[:MENTIONS]->(:KEntity)-[:RELATED_TO*1..$hops]-"
        "(:KEntity)<-[:MENTIONS]-(n:KChunk) "
        "WHERE c.chunk_id IN $seed_ids AND n.tenant_id=$tenant_id "
        "AND NOT n.chunk_id IN $seed_ids "
        "RETURN DISTINCT n.chunk_id AS chunk_id LIMIT $max_neighbors",
        seed_ids=seed_ids, tenant_id=tenant_id, hops=hops, max_neighbors=max_neighbors,
    )
    return [record["chunk_id"] for record in result]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_graph.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/graph.py tests/knowledge/test_graph.py
git commit -m "feat(knowledge): best-effort neo4j graph + hit merge"
```

---

### Task 8: LLM helpers — entity extraction + summary

**Files:**
- Create: `minder/core/knowledge/summarize.py`
- Create: `minder/core/knowledge/extraction.py`
- Test: `tests/knowledge/test_llm_helpers.py`

**Interfaces:**
- Produces:
  - `summarize_document(text: str, chat_fn) -> str` — calls `chat_fn(messages: list[dict]) -> str`, returns trimmed summary; on empty/failed returns `""`.
  - `extract_entities(text: str, chat_fn) -> tuple[list[tuple[str,str]], list[tuple[str,str,float]]]` — parses the model's JSON `{"entities":[{"key","type"}],"relations":[{"src","dst","confidence"}]}`; malformed JSON → `([], [])`. Allowed types filtered to `{"Concept","Process","Policy","Person","Org","Term"}`.
- `chat_fn` is injected so unit tests use a fake (no network).

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_llm_helpers.py
from minder.core.knowledge.extraction import extract_entities
from minder.core.knowledge.summarize import summarize_document


def test_summary_trims_and_returns_text():
    assert summarize_document("body", lambda msgs: "  a summary  ") == "a summary"


def test_summary_failure_returns_empty():
    def boom(msgs):
        raise RuntimeError("llm down")

    assert summarize_document("body", boom) == ""


def test_extract_parses_entities_and_filters_types():
    payload = (
        '{"entities":[{"key":"leave-policy","type":"Policy"},'
        '{"key":"junk","type":"Bogus"}],'
        '"relations":[{"src":"leave-policy","dst":"hr","confidence":0.8}]}'
    )
    entities, relations = extract_entities("t", lambda msgs: payload)
    assert ("leave-policy", "Policy") in entities
    assert ("junk", "Bogus") not in entities
    assert relations == [("leave-policy", "hr", 0.8)]


def test_extract_malformed_json_is_empty():
    assert extract_entities("t", lambda msgs: "not json") == ([], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_llm_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/summarize.py
"""LLM summary for inject-category documents (persona / company_background)."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Summarize the document into a concise briefing (max ~800 tokens) that an "
    "AI assistant can carry as background. Keep concrete facts; drop fluff."
)


def summarize_document(text: str, chat_fn: Callable[[list[dict]], str]) -> str:
    """Return a short summary, or '' if the model call fails/returns nothing."""
    try:
        out = chat_fn(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": text}]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarize failed: %s", exc)
        return ""
    return (out or "").strip()
```

```python
# minder/core/knowledge/extraction.py
"""LLM entity/relation extraction for the knowledge graph."""

from __future__ import annotations

import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = {"Concept", "Process", "Policy", "Person", "Org", "Term"}
_SYSTEM = (
    'Extract entities and relations as JSON: {"entities":[{"key","type"}],'
    '"relations":[{"src","dst","confidence"}]}. type in '
    "[Concept,Process,Policy,Person,Org,Term]. key is a lowercase slug. "
    "Only output JSON."
)


def extract_entities(
    text: str, chat_fn: Callable[[list[dict]], str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str, float]]]:
    """Return (entities, relations); ([], []) on any parse/model failure."""
    try:
        raw = chat_fn(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": text}]
        )
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extraction failed/invalid: %s", exc)
        return [], []
    entities = [
        (e["key"], e["type"])
        for e in data.get("entities", [])
        if e.get("type") in _ALLOWED_TYPES and e.get("key")
    ]
    valid_keys = {k for k, _ in entities}
    relations = [
        (r["src"], r["dst"], float(r.get("confidence", 0.5)))
        for r in data.get("relations", [])
        if r.get("src") in valid_keys and r.get("dst")
    ]
    return entities, relations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_llm_helpers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/summarize.py minder/core/knowledge/extraction.py tests/knowledge/test_llm_helpers.py
git commit -m "feat(knowledge): llm summary + entity extraction helpers"
```

---

### Task 9: IngestionService (orchestration)

**Files:**
- Create: `minder/core/knowledge/ingestion.py`
- Test: `tests/knowledge/test_ingestion.py`

**Interfaces:**
- Consumes: `KnowledgeRepository` (Task 5), `KnowledgeEmbedder` (Task 6), `KnowledgeGraph` (Task 7), `parse_file` (Task 3), `chunk_text` (Task 2), `behavior_for` (Task 1), `summarize_document`/`extract_entities` (Task 8).
- Produces: `class IngestionService(repo, embedder, graph, chat_fn)` with `async ingest_document(document_id: int) -> None`. Reads the doc row, sets `ingesting`, resolves file text (from `source_path` or the artifact bytes), chunks, indexes vectors, writes chunk rows, builds graph (if `behavior.build_graph`), summarizes (if `behavior.summarize`), sets `ready`. Any exception → `set_status(failed, error=...)` and returns (never raises).
- Citation format: `"{title} [{document_id}] · {document_id}#{chunk_index}"`; external id: `"{document_id}#{chunk_index}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_ingestion.py
import pytest

from minder.core.knowledge.ingestion import IngestionService


class FakeRepo:
    def __init__(self, doc):
        self.doc = doc
        self.status = []
        self.chunks = None
        self.summary = None

    async def get_document(self, document_id):
        return self.doc

    async def set_status(self, document_id, status, *, error=None):
        self.status.append((status, error))

    async def replace_chunks(self, document_id, tenant_id, category, chunks):
        self.chunks = chunks

    async def set_summary(self, document_id, summary):
        self.summary = summary


class FakeEmbedder:
    def __init__(self):
        self.indexed = None

    def index_chunks(self, ids, texts, payloads):
        self.indexed = (ids, texts, payloads)


class FakeGraph:
    def __init__(self):
        self.built = []

    def build_chunk(self, *args, **kwargs):
        self.built.append(args)


@pytest.mark.asyncio
async def test_reference_docs_indexes_and_builds_graph(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("para one\n\npara two", encoding="utf-8")
    doc = {
        "id": 1, "tenant_id": "t1", "category": "reference_docs",
        "title": "Doc", "source_path": str(f), "artifact_id": None,
    }
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: '{"entities":[],"relations":[]}')
    await svc.ingest_document(1)
    assert repo.status[0] == ("ingesting", None)
    assert repo.status[-1] == ("ready", None)
    assert emb.indexed[0] == ["1#0", "1#1"]
    assert repo.summary is None  # reference_docs is not summarized
    assert len(graph.built) == 2


@pytest.mark.asyncio
async def test_persona_summarized_not_graphed(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("I am the assistant.", encoding="utf-8")
    doc = {"id": 2, "tenant_id": "t1", "category": "persona",
           "title": "P", "source_path": str(f), "artifact_id": None}
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: "short summary")
    await svc.ingest_document(2)
    assert repo.summary == "short summary"
    assert graph.built == []


@pytest.mark.asyncio
async def test_failure_marks_failed(tmp_path):
    doc = {"id": 3, "tenant_id": "t1", "category": "reference_docs",
           "title": "X", "source_path": "/nonexistent.md", "artifact_id": None}
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: "")
    await svc.ingest_document(3)
    assert repo.status[-1][0] == "failed"
    assert repo.status[-1][1]  # error message present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_ingestion.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Add `get_document` to `KnowledgeRepository` (needed here and later):

```python
    async def get_document(self, document_id: int) -> dict[str, Any] | None:
        async with self._sm() as s:
            row = (
                await s.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
                )
            ).scalar_one_or_none()
            return _doc_to_dict(row) if row else None
```

```python
# minder/core/knowledge/ingestion.py
"""Background ingestion: parse -> chunk -> embed -> index -> graph -> summarize."""

from __future__ import annotations

import logging
from typing import Any, Callable

from minder.core.knowledge.categories import behavior_for
from minder.core.knowledge.chunking import chunk_text
from minder.core.knowledge.extraction import extract_entities
from minder.core.knowledge.parsing import parse_file
from minder.core.knowledge.summarize import summarize_document

logger = logging.getLogger(__name__)


class IngestionService:
    """Runs a single document through the full ingest pipeline, fail-safe."""

    def __init__(self, repo: Any, embedder: Any, graph: Any, chat_fn: Callable[[list[dict]], str]):
        self._repo = repo
        self._embedder = embedder
        self._graph = graph
        self._chat_fn = chat_fn

    async def ingest_document(self, document_id: int) -> None:
        doc = await self._repo.get_document(document_id)
        if doc is None:
            return
        await self._repo.set_status(document_id, "ingesting")
        try:
            await self._run(doc)
            await self._repo.set_status(document_id, "ready")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest failed for doc %s: %s", document_id, exc)
            await self._repo.set_status(document_id, "failed", error=str(exc))

    async def _run(self, doc: dict[str, Any]) -> None:
        behavior = behavior_for(doc["category"])
        text = self._resolve_text(doc)
        chunks = chunk_text(text)
        did, tenant, category, title = doc["id"], doc["tenant_id"], doc["category"], doc["title"]

        external_ids = [f"{did}#{i}" for i in range(len(chunks))]
        citations = [f"{title} [{did}] · {did}#{i}" for i in range(len(chunks))]
        payloads = [
            {
                "id": external_ids[i],
                "tenant_id": tenant,
                "category": category,
                "document_id": did,
                "chunk_id": external_ids[i],
                "text": chunks[i],
                "title": title,
                "citation": citations[i],
            }
            for i in range(len(chunks))
        ]
        self._embedder.index_chunks(external_ids, chunks, payloads)
        await self._repo.replace_chunks(
            did, tenant, category,
            [(i, chunks[i], external_ids[i], citations[i]) for i in range(len(chunks))],
        )

        if behavior.build_graph:
            for i, chunk in enumerate(chunks):
                entities, relations = extract_entities(chunk, self._chat_fn)
                self._graph.build_chunk(tenant, did, i, chunk, entities, relations)

        if behavior.summarize:
            summary = summarize_document(text, self._chat_fn)
            if summary:
                await self._repo.set_summary(did, summary)

    def _resolve_text(self, doc: dict[str, Any]) -> str:
        if doc.get("source_path"):
            return parse_file(doc["source_path"])
        raise ValueError("document has no source_path (artifact resolution is Task 12)")
```

Note: artifact-bytes resolution (when `artifact_id` is set) is wired in Task 12 where the `ArtifactService` path is available; seed-folder ingest (the default) always sets `source_path`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_ingestion.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/ingestion.py minder/core/knowledge/repository.py tests/knowledge/test_ingestion.py
git commit -m "feat(knowledge): ingestion orchestration"
```

---

### Task 10: Seed-folder scanner

**Files:**
- Create: `minder/core/knowledge/seed.py`
- Test: `tests/knowledge/test_seed.py`

**Interfaces:**
- Consumes: `KnowledgeRepository` (`find_document_by_hash`, `create_document`), `is_valid_category` (Task 1), `SUPPORTED_EXTENSIONS` (Task 3).
- Produces: `async scan_seed_dir(root: str, repo) -> list[int]` — recurse `root/<tenant_id>/<category>/<file>`; for each supported file compute sha256; if no doc with that `(tenant_id, hash)` exists, `create_document(... source_path=abs, source_filename=name)` and collect the new id. Malformed paths / bad categories / unsupported extensions are skipped. Returns the list of newly-enqueued document ids. `sha256_file(path) -> str` helper.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_seed.py
import pytest

from minder.core.knowledge.seed import scan_seed_dir, sha256_file


class FakeRepo:
    def __init__(self):
        self.docs = {}
        self.created = []

    async def find_document_by_hash(self, tenant_id, content_hash):
        return self.docs.get((tenant_id, content_hash))

    async def create_document(self, tenant_id, category, title, content_hash, **kw):
        new_id = len(self.created) + 1
        self.docs[(tenant_id, content_hash)] = {"id": new_id}
        self.created.append((tenant_id, category, title, content_hash, kw))
        return new_id


def _seed(tmp_path, tenant, category, name, body):
    d = tmp_path / tenant / category
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


@pytest.mark.asyncio
async def test_scan_enqueues_valid_files_only(tmp_path):
    _seed(tmp_path, "t1", "reference_docs", "a.md", "hello")
    _seed(tmp_path, "t1", "bad_category", "b.md", "x")   # skipped: bad category
    _seed(tmp_path, "t1", "reference_docs", "c.docx", "x")  # skipped: unsupported
    repo = FakeRepo()
    new_ids = await scan_seed_dir(str(tmp_path), repo)
    assert len(new_ids) == 1
    assert repo.created[0][0:3] == ("t1", "reference_docs", "a.md")


@pytest.mark.asyncio
async def test_scan_is_idempotent_on_unchanged_hash(tmp_path):
    _seed(tmp_path, "t1", "persona", "p.md", "same")
    repo = FakeRepo()
    first = await scan_seed_dir(str(tmp_path), repo)
    second = await scan_seed_dir(str(tmp_path), repo)
    assert len(first) == 1 and second == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_seed.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/seed.py
"""Scan the mounted seed folder and enqueue new/changed documents."""

from __future__ import annotations

import hashlib
import logging
import os

from minder.core.knowledge.categories import is_valid_category
from minder.core.knowledge.parsing import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


def sha256_file(path: str) -> str:
    """Return the hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


async def scan_seed_dir(root: str, repo) -> list[int]:
    """Enqueue new/changed files under root/<tenant_id>/<category>/<file>.

    Upsert-only: files removed from the folder are never auto-deleted. Returns
    ids of documents newly created (i.e. enqueued for ingest).
    """
    if not os.path.isdir(root):
        return []
    new_ids: list[int] = []
    for tenant_id in sorted(os.listdir(root)):
        tenant_dir = os.path.join(root, tenant_id)
        if not os.path.isdir(tenant_dir):
            continue
        for category in sorted(os.listdir(tenant_dir)):
            cat_dir = os.path.join(tenant_dir, category)
            if not os.path.isdir(cat_dir) or not is_valid_category(category):
                logger.info("seed: skip non-category dir %s/%s", tenant_id, category)
                continue
            for name in sorted(os.listdir(cat_dir)):
                path = os.path.join(cat_dir, name)
                ext = os.path.splitext(name)[1].lower()
                if not os.path.isfile(path) or ext not in SUPPORTED_EXTENSIONS:
                    continue
                content_hash = sha256_file(path)
                if await repo.find_document_by_hash(tenant_id, content_hash):
                    continue
                doc_id = await repo.create_document(
                    tenant_id, category, name, content_hash,
                    source_path=path, source_filename=name,
                )
                new_ids.append(doc_id)
    return new_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_seed.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/seed.py tests/knowledge/test_seed.py
git commit -m "feat(knowledge): seed-folder scanner (upsert-only, idempotent)"
```

---

### Task 11: DocumentsProvider (hybrid retrieval)

**Files:**
- Create: `minder/core/knowledge/provider.py`
- Test: `tests/knowledge/test_provider.py`

**Interfaces:**
- Consumes: `SearchProvider`, `SearchContext`, `SearchHit`, `SourceResults` from `minder.core.context_engineering.search`; `rrf_fuse`, `top_margin`; `KnowledgeEmbedder` (Task 6), `KnowledgeRepository.fts_search` (Task 5), `KnowledgeGraph` + `merge_graph_hits` + `graph_hops` + `graph_enabled` (Task 7).
- Produces: `class DocumentsProvider(SearchProvider)` with `name="documents"`, `description`, `filter_schema` = `{"category": {...enum...}}`; `__init__(embedder, repo, graph, resolve_tenant: Callable[[SearchContext], str | None])`. `search(query, filters, limit, context)` runs dense + FTS, `rrf_fuse`, optional 2-hop graph merge, then materializes `SearchHit`s from Qdrant payloads (already fetched in the dense step) — graph-only ids that lack a payload are hydrated from the repo. Returns `SourceResults(source="documents", hits=[...], top_margin=...)`. If tenant cannot be resolved → empty results with a `note`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_provider.py
from minder.core.context_engineering.search.types import SearchContext
from minder.core.knowledge.provider import DocumentsProvider


class FakeEmbedder:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]

    def search(self, vec, tenant_id, category, limit):
        # (external_id, score, payload)
        return [
            ("1#0", 0.9, {"id": "1#0", "text": "alpha", "title": "A", "citation": "A [1] · 1#0"}),
            ("1#1", 0.5, {"id": "1#1", "text": "beta", "title": "A", "citation": "A [1] · 1#1"}),
        ]


class FakeRepo:
    def fts_search(self, tenant_id, category, query, limit):
        return ["1#1"]


class FakeGraph:
    def expand(self, tenant_id, seed_ids, hops, max_neighbors):
        return []


def _provider(tenant="t1"):
    return DocumentsProvider(
        FakeEmbedder(), FakeRepo(), FakeGraph(),
        resolve_tenant=lambda ctx: tenant,
    )


def test_search_returns_fused_hits_scoped_to_tenant():
    res = _provider().search("alpha", {"category": "reference_docs"}, 6, SearchContext("U1"))
    ids = [h.id for h in res.hits]
    assert "1#0" in ids and "1#1" in ids
    assert res.source == "documents"


def test_missing_tenant_returns_empty_with_note():
    res = _provider(tenant=None).search("x", {}, 6, SearchContext(None))
    assert res.hits == []
    assert res.note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_provider.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/provider.py
"""Hybrid (dense + FTS + graph) search provider over knowledge chunks."""

from __future__ import annotations

from typing import Any, Callable

from minder.core.context_engineering.search.fusion import rrf_fuse, top_margin
from minder.core.context_engineering.search.provider import SearchProvider
from minder.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults
from minder.core.knowledge.categories import Category
from minder.core.knowledge.graph import graph_enabled, graph_hops, merge_graph_hits

_MAX_NEIGHBORS = 20


class DocumentsProvider(SearchProvider):
    """Permission-scoped hybrid retrieval; tenant is injected, never model-set."""

    name = "documents"
    description = (
        "Per-tenant knowledge base: reference documents (policies, PDFs, FAQs, "
        "workflows). Results are scoped to the acting tenant and cited."
    )
    filter_schema: dict[str, Any] = {
        "category": {
            "type": "string",
            "enum": [c.value for c in Category],
            "description": "Which knowledge category to search (default reference_docs).",
        }
    }

    def __init__(
        self,
        embedder: Any,
        repo: Any,
        graph: Any,
        resolve_tenant: Callable[[SearchContext], str | None],
    ) -> None:
        self._embedder = embedder
        self._repo = repo
        self._graph = graph
        self._resolve_tenant = resolve_tenant

    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        tenant_id = self._resolve_tenant(context)
        if not tenant_id:
            return SourceResults(
                source=self.name, hits=[], note="no tenant in context; access denied"
            )
        category = filters.get("category") or Category.REFERENCE_DOCS.value

        query_vec = self._embedder.embed_query(query)
        dense = self._embedder.search(query_vec, tenant_id, category, max(limit * 2, 10))
        payloads = {external_id: payload for external_id, _score, payload in dense}
        dense_ids = [external_id for external_id, _s, _p in dense]
        fts_ids = self._repo.fts_search(tenant_id, category, query, max(limit * 2, 10))

        fused = rrf_fuse([dense_ids, fts_ids])
        ranked = sorted(fused, key=lambda i: fused[i], reverse=True)

        if graph_enabled():
            graph_ids = self._graph.expand(
                tenant_id, ranked[:limit], graph_hops(), _MAX_NEIGHBORS
            )
            ranked = merge_graph_hits(ranked, graph_ids, cap=limit + _MAX_NEIGHBORS)

        hits: list[SearchHit] = []
        for external_id in ranked[:limit]:
            payload = payloads.get(external_id) or self._hydrate(external_id, tenant_id)
            if payload is None:
                continue
            hits.append(
                SearchHit(
                    id=external_id,
                    source=self.name,
                    title=payload.get("title", ""),
                    snippet=payload.get("text", "")[:700],
                    score=fused.get(external_id, 0.0),
                    metadata={"citation": payload.get("citation", "")},
                )
            )
        return SourceResults(
            source=self.name, hits=hits, top_margin=top_margin([h.score for h in hits])
        )

    def _hydrate(self, external_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Fetch a graph-only chunk's payload from Postgres when not in the dense set."""
        document_id, _, chunk_index = external_id.partition("#")
        rows = self._repo.chunk_payload(tenant_id, int(document_id), int(chunk_index))
        return rows
```

Add to `KnowledgeRepository` the sync `chunk_payload` used by `_hydrate`:

```python
    def chunk_payload(self, tenant_id: str, document_id: int, chunk_index: int) -> dict[str, Any] | None:
        rows = pg.fetch_all(
            "SELECT text, citation, "
            "(SELECT title FROM knowledge_documents d WHERE d.id = c.document_id) AS title "
            "FROM knowledge_chunks c "
            "WHERE c.tenant_id = $1 AND c.document_id = $2 AND c.chunk_index = $3",
            [tenant_id, document_id, chunk_index],
        )
        return rows[0] if rows else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_provider.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/provider.py minder/core/knowledge/repository.py tests/knowledge/test_provider.py
git commit -m "feat(knowledge): hybrid documents search provider"
```

---

### Task 12: KnowledgeService + artifact-bytes ingest resolution + queue drain

**Files:**
- Create: `minder/core/knowledge/service.py`
- Modify: `minder/core/knowledge/ingestion.py` (`_resolve_text`: support `artifact_id`)
- Test: `tests/knowledge/test_service.py`

**Interfaces:**
- Produces: `class KnowledgeService(repo, ingestion)`:
  - `async register_upload(tenant_id, category, title, content_hash, artifact_id) -> int` (create doc + return id; validates category)
  - `async drain_queue(batch=5) -> int` — pull `pending_document_ids`, ingest each, return count processed
  - `async list_documents(tenant_id) -> list[dict]`
  - `async delete(document_id) -> None` (repo delete → embedder delete for returned point ids)
  - `async reingest(document_id) -> None` (set status pending; the drain picks it up)
- `IngestionService._resolve_text` gains: when `source_path` is empty but `artifact_id` set, read the artifact file bytes to a temp path and parse. (Artifact file resolution reuses `ArtifactService.get_artifact_path`; if unavailable, raise — surfaced as `failed`.)

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_service.py
import pytest

from minder.core.knowledge.service import KnowledgeService


class FakeRepo:
    def __init__(self):
        self.created = []
        self.pending = [1, 2]
        self.status = {}

    async def create_document(self, tenant_id, category, title, content_hash, **kw):
        self.created.append((tenant_id, category))
        return len(self.created)

    async def pending_document_ids(self, limit=5):
        out, self.pending = self.pending[:limit], self.pending[limit:]
        return out

    async def set_status(self, document_id, status, *, error=None):
        self.status[document_id] = status


class FakeIngestion:
    def __init__(self):
        self.done = []

    async def ingest_document(self, document_id):
        self.done.append(document_id)


@pytest.mark.asyncio
async def test_register_upload_validates_category():
    svc = KnowledgeService(FakeRepo(), FakeIngestion())
    with pytest.raises(ValueError):
        await svc.register_upload("t1", "bogus", "T", "h", artifact_id=7)
    doc_id = await svc.register_upload("t1", "reference_docs", "T", "h", artifact_id=7)
    assert doc_id == 1


@pytest.mark.asyncio
async def test_drain_processes_pending_batch():
    repo, ing = FakeRepo(), FakeIngestion()
    svc = KnowledgeService(repo, ing)
    count = await svc.drain_queue(batch=5)
    assert count == 2 and ing.done == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/service.py
"""Management API for the knowledge base: register, drain, list, delete."""

from __future__ import annotations

from typing import Any

from minder.core.knowledge.categories import is_valid_category


class KnowledgeService:
    """Coordinates document lifecycle over the repository + ingestion service."""

    def __init__(self, repo: Any, ingestion: Any, embedder: Any = None) -> None:
        self._repo = repo
        self._ingestion = ingestion
        self._embedder = embedder

    async def register_upload(
        self, tenant_id: str, category: str, title: str, content_hash: str, artifact_id: int
    ) -> int:
        if not is_valid_category(category):
            raise ValueError(f"Unknown category: {category!r}")
        return await self._repo.create_document(
            tenant_id, category, title, content_hash, artifact_id=artifact_id
        )

    async def drain_queue(self, batch: int = 5) -> int:
        ids = await self._repo.pending_document_ids(limit=batch)
        for document_id in ids:
            await self._ingestion.ingest_document(document_id)
        return len(ids)

    async def list_documents(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self._repo.list_documents(tenant_id)

    async def reingest(self, document_id: int) -> None:
        await self._repo.set_status(document_id, "pending")

    async def delete(self, document_id: int) -> None:
        point_ids = await self._repo.delete_document(document_id)
        if self._embedder and point_ids:
            self._embedder.delete(point_ids)
```

Modify `IngestionService._resolve_text` in `ingestion.py`:

```python
    def _resolve_text(self, doc: dict[str, Any]) -> str:
        if doc.get("source_path"):
            return parse_file(doc["source_path"])
        if doc.get("artifact_id"):
            from minder.core.knowledge.artifact_bytes import artifact_path

            return parse_file(artifact_path(doc["artifact_id"]))
        raise ValueError("document has neither source_path nor artifact_id")
```

Create `minder/core/knowledge/artifact_bytes.py` with a single resolver that
reuses the existing artifact storage layout (the exact accessor is the one
`ArtifactService` uses to turn an artifact row into an on-disk path):

```python
# minder/core/knowledge/artifact_bytes.py
"""Resolve an artifact id to an on-disk file path for ingestion."""

from __future__ import annotations


def artifact_path(artifact_id: int) -> str:
    """Return the absolute path of an uploaded artifact's file.

    Reuses ArtifactService's resolution so knowledge ingest reads the exact
    bytes the upload stored.
    """
    from minder.core.services.artifact_service import ArtifactService

    return ArtifactService.resolve_path_sync(artifact_id)
```

> Implementer note: if `ArtifactService` exposes path resolution under a
> different name, adapt `resolve_path_sync` to that method (grep
> `minder/core/services/artifact_service.py` for the path/`payload_ref`
> accessor). Keep the `artifact_path(artifact_id) -> str` signature stable.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_service.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/service.py minder/core/knowledge/artifact_bytes.py minder/core/knowledge/ingestion.py tests/knowledge/test_service.py
git commit -m "feat(knowledge): management service + artifact-bytes ingest resolution"
```

---

### Task 13: ProfileInjector (persona/background → prompt block)

**Files:**
- Create: `minder/core/knowledge/profile.py`
- Test: `tests/knowledge/test_profile.py`

**Interfaces:**
- Consumes: `KnowledgeRepository.summaries_for_inject` (Task 5).
- Produces: `class ProfileInjector(repo, max_chars=8000)` with `async build_profile_block(tenant_id: str | None) -> str`. Returns a markdown block:
  ```
  ## Bối cảnh tổ chức
  <company_background summaries...>

  ## Vai trò của bạn
  <persona summaries...>
  ```
  Empty string when tenant is falsy or has no ready summaries. Total length capped at `max_chars` (truncate + append "…"). Persona summaries drive whether the caller replaces the default identity section (`has_persona(tenant_id)` helper returns bool).

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_profile.py
import pytest

from minder.core.knowledge.profile import ProfileInjector


class FakeRepo:
    def __init__(self, docs):
        self._docs = docs

    async def summaries_for_inject(self, tenant_id, categories):
        return [d for d in self._docs if d["tenant_id"] == tenant_id and d["category"] in categories]


@pytest.mark.asyncio
async def test_block_has_background_and_persona_sections():
    repo = FakeRepo([
        {"tenant_id": "t1", "category": "company_background", "summary": "We sell rockets."},
        {"tenant_id": "t1", "category": "persona", "summary": "You are Rocket Helper."},
    ])
    block = await ProfileInjector(repo).build_profile_block("t1")
    assert "Bối cảnh tổ chức" in block and "We sell rockets." in block
    assert "Vai trò của bạn" in block and "Rocket Helper" in block


@pytest.mark.asyncio
async def test_no_tenant_or_no_docs_yields_empty():
    assert await ProfileInjector(FakeRepo([])).build_profile_block(None) == ""
    assert await ProfileInjector(FakeRepo([])).build_profile_block("t1") == ""


@pytest.mark.asyncio
async def test_truncated_to_cap():
    repo = FakeRepo([{"tenant_id": "t1", "category": "persona", "summary": "x" * 100}])
    block = await ProfileInjector(repo, max_chars=40).build_profile_block("t1")
    assert len(block) <= 41 and block.endswith("…")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_profile.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/profile.py
"""Build the per-tenant persona/background block injected into the prompt."""

from __future__ import annotations

from typing import Any


class ProfileInjector:
    """Assembles tenant persona + company background into a prompt section."""

    def __init__(self, repo: Any, max_chars: int = 8000) -> None:
        self._repo = repo
        self._max_chars = max_chars

    async def build_profile_block(self, tenant_id: str | None) -> str:
        if not tenant_id:
            return ""
        docs = await self._repo.summaries_for_inject(
            tenant_id, ["company_background", "persona"]
        )
        background = [d["summary"] for d in docs if d["category"] == "company_background"]
        persona = [d["summary"] for d in docs if d["category"] == "persona"]
        parts: list[str] = []
        if background:
            parts.append("## Bối cảnh tổ chức\n" + "\n\n".join(background))
        if persona:
            parts.append("## Vai trò của bạn\n" + "\n\n".join(persona))
        block = "\n\n".join(parts)
        if len(block) > self._max_chars:
            block = block[: self._max_chars] + "…"
        return block

    async def has_persona(self, tenant_id: str | None) -> bool:
        if not tenant_id:
            return False
        docs = await self._repo.summaries_for_inject(tenant_id, ["persona"])
        return any(d["category"] == "persona" for d in docs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_profile.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/profile.py tests/knowledge/test_profile.py
git commit -m "feat(knowledge): profile injector for persona/background"
```

---

### Task 14: knowledge_query ToolSpec + registry wiring

**Files:**
- Create: `minder/core/knowledge/tool.py`
- Modify: `minder/core/context_engineering/tools/registry.py` (register the core ToolSpec into `_skill_specs`)
- Test: `tests/knowledge/test_tool.py`

**Interfaces:**
- Consumes: `ToolSpec` from `minder.core.skill_tools`; `DocumentsProvider` (Task 11); `SearchContext`.
- Produces: `build_knowledge_tool_spec(provider, resolve_context: Callable[[], SearchContext]) -> ToolSpec` named `knowledge_query`, params `{question: str (required), category?: enum, k?: int}`. Handler resolves `SearchContext` from the runtime (principal) — never accepts `tenant_id` — calls `provider.search`, returns `{"hits": [...], "note": ...}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_tool.py
from minder.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults
from minder.core.knowledge.tool import build_knowledge_tool_spec


class FakeProvider:
    def search(self, question, filters, limit, context):
        assert "tenant_id" not in filters  # tenant never model-supplied
        return SourceResults(
            source="documents",
            hits=[SearchHit("1#0", "documents", "A", "alpha", 0.9, {"citation": "A [1] · 1#0"})],
        )


def test_tool_spec_shape_and_no_tenant_param():
    spec = build_knowledge_tool_spec(FakeProvider(), lambda: SearchContext("U1"))
    assert spec.name == "knowledge_query"
    props = spec.parameters["properties"]
    assert "question" in props and "tenant_id" not in props
    assert spec.parameters["required"] == ["question"]


def test_handler_returns_hits():
    spec = build_knowledge_tool_spec(FakeProvider(), lambda: SearchContext("U1"))
    out = spec.handler(question="alpha", category="reference_docs", k=3)
    assert out["hits"][0]["metadata"]["citation"] == "A [1] · 1#0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_tool.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/tool.py
"""The agent-facing knowledge_query tool (core-owned ToolSpec)."""

from __future__ import annotations

from typing import Any, Callable

from minder.core.knowledge.categories import Category
from minder.core.skill_tools import ToolSpec


def build_knowledge_tool_spec(
    provider: Any, resolve_context: Callable[[], Any]
) -> ToolSpec:
    """Build the knowledge_query ToolSpec. tenant_id comes from resolve_context()."""

    def handler(question: str, category: str | None = None, k: int = 6) -> dict[str, Any]:
        filters = {"category": category} if category else {}
        results = provider.search(question, filters, k, resolve_context())
        return {"hits": [h.to_dict() for h in results.hits], "note": results.note}

    return ToolSpec(
        name="knowledge_query",
        description=(
            "Search the tenant's knowledge base (policies, PDFs, FAQs, workflows). "
            "Returns cited passages. Answer only from these; keep the citations."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The user's question."},
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": "Category to search (default reference_docs).",
                },
                "k": {"type": "integer", "description": "Max passages (default 6)."},
            },
            "required": ["question"],
        },
        handler=handler,
    )
```

In `registry.py`, after the skill-spec merge loop (line ~206), register the core knowledge tool if its dependencies can be built. Add this block right after `for _name, _spec in self._skill_specs.items(): ...`:

```python
        # Core-owned knowledge_query tool (registered like a skill spec so it
        # gets an LLM schema via _build_skill_schemas and appears in the
        # assistant allowlist). Never fatal if wiring is unavailable.
        try:
            from minder.core.knowledge.wiring import build_knowledge_tool_spec_default

            _kspec = build_knowledge_tool_spec_default()
            if _kspec is not None:
                self._skill_specs[_kspec.name] = _kspec
                self._handlers[_kspec.name] = self._make_skill_handler(_kspec)
        except Exception as _kexc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning("knowledge tool not registered: %s", _kexc)
```

Create the wiring factory `minder/core/knowledge/wiring.py` (returns `None` if `DATABASE_URL`/deps missing, so tests and non-DB contexts stay green):

```python
# minder/core/knowledge/wiring.py
"""Construct knowledge components from env; returns None when unavailable."""

from __future__ import annotations

import os
from typing import Any

from minder.core.context_engineering.search.types import SearchContext


def _resolve_tenant(context: SearchContext) -> str | None:
    # Web threads identity via SearchContext.user_id → tenant map (future);
    # dev fallback lets local runs work without Keycloak.
    if os.environ.get("MINDER_ENV") == "dev":
        return os.environ.get("KNOWLEDGE_DEV_TENANT")
    return context.user_id


def build_knowledge_tool_spec_default() -> Any:
    if not os.environ.get("DATABASE_URL"):
        return None
    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.provider import DocumentsProvider
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.tool import build_knowledge_tool_spec
    from minder.db.connection import get_sessionmaker

    import asyncio

    sm = asyncio.run(get_sessionmaker())
    repo = KnowledgeRepository(sm)
    provider = DocumentsProvider(KnowledgeEmbedder(), repo, KnowledgeGraph(), _resolve_tenant)
    return build_knowledge_tool_spec(provider, lambda: SearchContext(os.environ.get("MINDER_SEARCH_USER_ID")))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_tool.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/tool.py minder/core/knowledge/wiring.py minder/core/context_engineering/tools/registry.py tests/knowledge/test_tool.py
git commit -m "feat(knowledge): knowledge_query tool + registry wiring"
```

---

### Task 15: Assistant prompt injection

**Files:**
- Modify: `minder/core/agents/assistant_agent.py:54-70` (`build_system_prompt`)
- Test: `tests/knowledge/test_assistant_injection.py`

**Interfaces:**
- Consumes: `ProfileInjector` (Task 13), `KnowledgeRepository`.
- Produces: `AssistantAgent.build_system_prompt` now appends the tenant profile block (background + persona). When the tenant has a persona, the persona block replaces the default identity by being placed first with an explicit override header; safety/operational content from `system/assistant` remains. A module-level helper `load_profile_block_sync(tenant_id) -> str` bridges the async injector to the sync prompt builder.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_assistant_injection.py
from minder.core.knowledge import assistant_profile


def test_profile_block_prepended_when_present(monkeypatch):
    monkeypatch.setattr(
        assistant_profile, "load_profile_block_sync", lambda tenant: "## Vai trò của bạn\nRocket Helper"
    )
    out = assistant_profile.apply_profile("BASE PROMPT", tenant_id="t1")
    assert out.startswith("## Vai trò của bạn")
    assert "BASE PROMPT" in out


def test_no_profile_returns_base(monkeypatch):
    monkeypatch.setattr(assistant_profile, "load_profile_block_sync", lambda tenant: "")
    assert assistant_profile.apply_profile("BASE PROMPT", tenant_id="t1") == "BASE PROMPT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_assistant_injection.py -v`
Expected: FAIL with `ModuleNotFoundError: minder.core.knowledge.assistant_profile`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/assistant_profile.py
"""Bridge the async ProfileInjector into the synchronous prompt builder."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def load_profile_block_sync(tenant_id: str | None) -> str:
    """Return the tenant profile block, or '' on any failure/unavailability."""
    if not tenant_id or not os.environ.get("DATABASE_URL"):
        return ""
    try:
        from minder.core.knowledge.profile import ProfileInjector
        from minder.core.knowledge.repository import KnowledgeRepository
        from minder.db.connection import get_sessionmaker

        async def _run() -> str:
            sm = await get_sessionmaker()
            return await ProfileInjector(KnowledgeRepository(sm)).build_profile_block(tenant_id)

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile block load failed: %s", exc)
        return ""


def apply_profile(base_prompt: str, tenant_id: str | None) -> str:
    """Prepend the tenant profile block to the base prompt when present.

    The persona block leads, replacing the default identity framing; the base
    prompt's operational/safety sections stay intact below it.
    """
    block = load_profile_block_sync(tenant_id)
    if not block:
        return base_prompt
    return f"{block}\n\n{base_prompt}"
```

Modify `AssistantAgent.build_system_prompt` in `assistant_agent.py` to apply it
(insert before `self._system_stable = full`):

```python
        full = base + ("\n\n" + block if block else "")
        # Replace default identity with the tenant persona/background when present.
        from minder.core.knowledge.assistant_profile import apply_profile

        tenant_id = getattr(self, "_tenant_id", None) or os.environ.get("KNOWLEDGE_DEV_TENANT")
        full = apply_profile(full, tenant_id)
        self._system_stable = full
```

Add `import os` at the top of `assistant_agent.py` if not present.

> Implementer note: `self._tenant_id` is set by the web executor from
> `request.state.principal.tenant_id` when constructing the assistant agent. If
> that attribute is not yet wired, the dev fallback keeps local runs working;
> add the one-line assignment where `AssistantAgent(...)` is instantiated.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_assistant_injection.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/assistant_profile.py minder/core/agents/assistant_agent.py tests/knowledge/test_assistant_injection.py
git commit -m "feat(knowledge): inject tenant persona/background into assistant prompt"
```

---

### Task 16: Web routes (rescan + list) and scheduler wiring

**Files:**
- Create: `minder/web/routes/knowledge.py`
- Modify: web app factory (`minder/web/server.py` or `minder/web/app.py` — where routers are included and `init_schema` runs) to include the router and register two `BackgroundScheduler` tasks
- Test: `tests/knowledge/test_web_routes.py`

**Interfaces:**
- Produces FastAPI router with:
  - `POST /knowledge/rescan` → runs `scan_seed_dir(KNOWLEDGE_SEED_DIR, repo)` then `service.drain_queue()`; returns `{"enqueued": n, "processed": m}`.
  - `GET /knowledge/documents` → `service.list_documents(tenant_id)` (tenant from principal / dev fallback).
- Scheduler: on startup register `knowledge_seed` (interval e.g. 3600s, also invoked once at startup) → scan+drain, and `knowledge_drain` (interval e.g. 30s) → `drain_queue`.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_web_routes.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from minder.web.routes.knowledge import build_router


class FakeService:
    async def list_documents(self, tenant_id):
        return [{"id": 1, "title": "Doc", "status": "ready", "category": "reference_docs"}]

    async def drain_queue(self, batch=5):
        return 2


def test_list_documents_endpoint():
    app = FastAPI()
    app.include_router(
        build_router(service_factory=lambda: FakeService(), tenant_factory=lambda req: "t1",
                     seed_scan=lambda: 3)
    )
    client = TestClient(app)
    resp = client.get("/knowledge/documents")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Doc"


def test_rescan_endpoint_reports_counts():
    app = FastAPI()
    app.include_router(
        build_router(service_factory=lambda: FakeService(), tenant_factory=lambda req: "t1",
                     seed_scan=lambda: 3)
    )
    client = TestClient(app)
    resp = client.post("/knowledge/rescan")
    assert resp.json() == {"enqueued": 3, "processed": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_web_routes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/web/routes/knowledge.py
"""HTTP endpoints for the knowledge base: rescan + document listing."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Request


def build_router(
    service_factory: Callable[[], Any],
    tenant_factory: Callable[[Request], str | None],
    seed_scan: Callable[[], int],
) -> APIRouter:
    """Build the knowledge router.

    Args:
        service_factory: Returns a KnowledgeService (async methods).
        tenant_factory: Resolves tenant_id from the request principal.
        seed_scan: Runs the seed scan and returns the count of newly enqueued docs.
    """
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.get("/documents")
    async def list_documents(request: Request) -> list[dict[str, Any]]:
        service = service_factory()
        return await service.list_documents(tenant_factory(request))

    @router.post("/rescan")
    async def rescan() -> dict[str, int]:
        enqueued = seed_scan()
        processed = await service_factory().drain_queue()
        return {"enqueued": enqueued, "processed": processed}

    return router
```

In the web app factory, after `init_schema()` and router includes, wire the
router + scheduler (adapt names to the actual factory; grep for
`BackgroundScheduler` / other `include_router` calls):

```python
    from minder.core.knowledge.wiring import build_knowledge_service, run_seed_scan
    from minder.web.routes.knowledge import build_router as build_knowledge_router

    app.include_router(
        build_knowledge_router(
            service_factory=build_knowledge_service,
            tenant_factory=lambda req: getattr(getattr(req.state, "principal", None), "tenant_id", None)
            or os.environ.get("KNOWLEDGE_DEV_TENANT"),
            seed_scan=run_seed_scan,
        )
    )
    scheduler.add_task("knowledge_drain", lambda: build_knowledge_service().drain_queue(), 30)
    scheduler.add_task("knowledge_seed", _knowledge_seed_and_drain, 3600)
```

Add the two factory helpers to `minder/core/knowledge/wiring.py`:

```python
def build_knowledge_service() -> Any:
    import asyncio

    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.ingestion import IngestionService
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.service import KnowledgeService
    from minder.db.connection import get_sessionmaker

    sm = asyncio.run(get_sessionmaker())
    repo = KnowledgeRepository(sm)
    embedder = KnowledgeEmbedder()
    ingestion = IngestionService(repo, embedder, KnowledgeGraph(), _default_chat_fn())
    return KnowledgeService(repo, ingestion, embedder)


def run_seed_scan() -> int:
    import asyncio
    import os

    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.seed import scan_seed_dir
    from minder.db.connection import get_sessionmaker

    root = os.environ.get("KNOWLEDGE_SEED_DIR", "")

    async def _run() -> int:
        sm = await get_sessionmaker()
        return len(await scan_seed_dir(root, KnowledgeRepository(sm)))

    return asyncio.run(_run())
```

`_default_chat_fn()` returns a callable `(messages) -> str` over the app's
configured OpenAI-compatible chat model (reuse the same client the agent uses;
grep the agent's LLM client). `_knowledge_seed_and_drain` is a small async
wrapper: `run_seed_scan()` then `await build_knowledge_service().drain_queue()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_web_routes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/web/routes/knowledge.py minder/core/knowledge/wiring.py tests/knowledge/test_web_routes.py
# plus the modified web app factory file
git commit -m "feat(knowledge): web rescan/list routes + scheduler wiring"
```

---

### Task 17: CLI commands

**Files:**
- Modify: `minder/cli.py` (add a `knowledge` subcommand group)
- Test: `tests/knowledge/test_cli.py`

**Interfaces:**
- Produces `minder knowledge {list,rescan,query,reingest,delete}`:
  - `list [--tenant T]` → prints doc id, status, category, title
  - `rescan` → runs seed scan + drain, prints counts
  - `query "<q>" [--tenant T] [--category C] [--k N]` → prints hits + citations
  - `reingest <doc_id>` / `delete <doc_id>`
- Command bodies delegate to a testable `minder/core/knowledge/cli_ops.py` with pure-ish async functions taking a service/provider, so the CLI wiring is thin.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_cli.py
import pytest

from minder.core.knowledge.cli_ops import format_documents, format_hits


def test_format_documents_table():
    out = format_documents([{"id": 1, "status": "ready", "category": "reference_docs", "title": "Doc"}])
    assert "ready" in out and "Doc" in out and "1" in out


def test_format_hits_lists_citations():
    hits = [{"metadata": {"citation": "A [1] · 1#0"}, "snippet": "alpha"}]
    out = format_hits(hits)
    assert "A [1] · 1#0" in out and "alpha" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# minder/core/knowledge/cli_ops.py
"""Formatting + thin operations for the `minder knowledge` CLI."""

from __future__ import annotations

from typing import Any


def format_documents(docs: list[dict[str, Any]]) -> str:
    if not docs:
        return "(no documents)"
    lines = [f"{d['id']:>4}  {d['status']:<10}  {d['category']:<18}  {d['title']}" for d in docs]
    return "\n".join(lines)


def format_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(no hits)"
    lines = []
    for h in hits:
        citation = h.get("metadata", {}).get("citation", "")
        lines.append(f"- {citation}\n  {h.get('snippet', '')}")
    return "\n".join(lines)
```

Then add a thin `knowledge` argparse/typer subcommand group in `minder/cli.py`
(follow the existing subcommand style — grep `def main` / how `mcp` subcommands
are declared). Each command builds the service/provider via
`minder.core.knowledge.wiring` and prints `format_documents` / `format_hits`.
Example for `list`:

```python
    # inside the knowledge subcommand dispatch:
    if args.knowledge_cmd == "list":
        from minder.core.knowledge.cli_ops import format_documents
        from minder.core.knowledge.wiring import build_knowledge_service

        import asyncio

        tenant = args.tenant or os.environ.get("KNOWLEDGE_DEV_TENANT", "dev")
        docs = asyncio.run(build_knowledge_service().list_documents(tenant))
        print(format_documents(docs))
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add minder/core/knowledge/cli_ops.py minder/cli.py tests/knowledge/test_cli.py
git commit -m "feat(knowledge): minder knowledge CLI commands"
```

---

### Task 18: Integration test (real Qdrant + Postgres + Neo4j)

**Files:**
- Create: `tests/knowledge/test_integration_ingest_query.py`
- Create: sample seed files under `tests/knowledge/fixtures/dev/{reference_docs,persona}/`

**Interfaces:** exercises the real stack. Guarded by an env flag so it is skipped in the default unit run.

- [ ] **Step 1: Write the test**

```python
# tests/knowledge/test_integration_ingest_query.py
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_IT") != "1",
    reason="integration test; set KNOWLEDGE_IT=1 with Qdrant+Postgres+Neo4j up",
)


@pytest.mark.asyncio
async def test_seed_ingest_then_query_is_tenant_scoped():
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.seed import scan_seed_dir
    from minder.core.knowledge.wiring import build_knowledge_service
    from minder.db.connection import get_sessionmaker, init_schema

    await init_schema()
    sm = await get_sessionmaker()
    repo = KnowledgeRepository(sm)

    root = os.path.join(os.path.dirname(__file__), "fixtures")
    await scan_seed_dir(root, repo)
    service = build_knowledge_service()
    await service.drain_queue(batch=50)

    docs = await service.list_documents("dev")
    assert any(d["status"] == "ready" for d in docs)
    # tenant isolation: a different tenant sees nothing
    assert await service.list_documents("other-tenant") == []
```

Create fixture files (small):
- `tests/knowledge/fixtures/dev/reference_docs/leave-policy.md` — a few paragraphs.
- `tests/knowledge/fixtures/dev/persona/agent.md` — a short persona.

- [ ] **Step 2: Run against the local stack**

```bash
docker compose -f docker-compose.dev.yml up -d db qdrant neo4j
export KNOWLEDGE_IT=1 MINDER_ENV=dev KNOWLEDGE_DEV_TENANT=dev
export DATABASE_URL=postgresql://minder:minder@localhost:5432/minder
export QDRANT_URL=http://localhost:6333
export KNOWLEDGE_NEO4J_URI=bolt://localhost:7687 KNOWLEDGE_NEO4J_USER=neo4j KNOWLEDGE_NEO4J_PASSWORD=minder-neo4j
export KNOWLEDGE_GRAPH_ENABLED=1 OPENAI_API_KEY=$OPENAI_API_KEY
uv run pytest tests/knowledge/test_integration_ingest_query.py -v
```

Expected: PASS (documents reach `ready`; cross-tenant list is empty).

- [ ] **Step 3: Commit**

```bash
git add tests/knowledge/test_integration_ingest_query.py tests/knowledge/fixtures
git commit -m "test(knowledge): integration ingest+query with tenant isolation"
```

---

### Task 19: End-to-end verification (real agent)

**Files:** none new — a manual/scripted verification per CLAUDE.md.

- [ ] **Step 1: Bring up the full stack**

```bash
docker compose -f docker-compose.dev.yml up -d
mkdir -p knowledge/dev/{persona,company_background,reference_docs}
# drop a persona.md, company.md, and a policy.pdf/md into those folders
```

- [ ] **Step 2: Ingest via rescan**

```bash
curl -X POST http://localhost:8080/api/knowledge/rescan   # path via nginx
# or: minder knowledge rescan
minder knowledge list --tenant dev   # expect status "ready"
```

- [ ] **Step 3: Query retrieval directly**

```bash
minder knowledge query "what is the leave policy?" --tenant dev
# expect hits with citations from reference_docs
```

- [ ] **Step 4: Ask the agent (real API)**

With `OPENAI_API_KEY` set and `MINDER_AGENT_MODE=assistant`, open the chat and
ask a question answerable only from the seeded reference docs. Confirm:
(a) the answer cites the reference doc, (b) the agent reflects the tenant
persona/background from its prompt (e.g. correct company name/role).

- [ ] **Step 5: Commit any fixups discovered during e2e**

```bash
git add -A && git commit -m "fix(knowledge): e2e adjustments"
```

---

## Self-Review

**Spec coverage:**
- Multi-tenant hard isolation → Tasks 4/5 (tenant_id columns+filters), 6 (Qdrant filter), 11 (provider), 18 (isolation test). ✓
- Categories + behaviors → Task 1; consumed in 9/13. ✓
- Knowledge graph (build + 2-hop expand, best-effort) → Tasks 7/8/9/11. ✓
- Persona replaces identity, safety kept → Tasks 13/15. ✓
- Two ingest sources, one pipeline → Tasks 9 (pipeline), 10 (seed), 12 (upload+drain), 16 (routes). ✓
- Background ingestion → Tasks 12 (drain), 16 (scheduler). ✓
- Summarize-then-inject → Tasks 8 (summarize), 9 (on ingest), 13 (inject). ✓
- Seed folder structure + upsert-only + idempotent hash → Task 10. ✓
- Agent tool + CLI, no UI → Tasks 14, 17. ✓
- Error handling fail-safe → Tasks 9 (failed status), 7 (graph best-effort), 11 (empty on missing tenant). ✓
- FTS + dense + rrf_fuse → Tasks 5, 6, 11. ✓
- Config via env → wiring in 14/16; infra already applied. ✓
- Tests unit/integration/e2e → Tasks 1-17 (unit), 18 (integration), 19 (e2e). ✓

**Placeholder scan:** Wiring tasks (12/15/16/17) contain implementer notes where an exact existing symbol must be grepped (`ArtifactService` path accessor, web app factory, agent LLM client, CLI subcommand style). These are real seams, not logic gaps — each names the file to grep and a stable target signature. No `TODO`/`add error handling`/`similar to Task N` placeholders remain in logic code.

**Type consistency:** External id format `"{document_id}#{chunk_index}"` and citation `"{title} [{document_id}] · {document_id}#{chunk_index}"` are identical across Tasks 9, 11, 5. `KnowledgeRepository` method names referenced by 9/11/12/13 (`get_document`, `fts_search`, `chunk_payload`, `summaries_for_inject`, `pending_document_ids`, `delete_document`) are all defined in Task 5 (+ the Task 9 addition). `ToolSpec(name, description, parameters, handler)` matches usage in Task 14.
