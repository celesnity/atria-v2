# Maintenance Copilot — Phase 2: Ingestion & Retrieval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest synthetic AMM/MEL/CDL/TSM manuals, chunk them with Chonkie `RecursiveChunker`, embed chunks via TEI, index them in Qdrant with metadata, and retrieve version-aware, cited passages for a query.

**Architecture:** Four small modules under `modules/maintenance_copilot/scripts/` — `corpus.py` (parse doc → `Document` with front-matter + metadata), `chunking.py` (Chonkie `RecursiveChunker` → chunk records carrying citation anchors), `index_store.py` (Qdrant collection: embed via `RoleClient` + upsert + version/ATA-filtered query), and new `copilot.py` subcommands `ingest`/`index`/`query`/`list`/`reset`. Retrieval returns ranked cited passages as JSON; LLM answer-synthesis and guardrails are Phase 4.

**Tech Stack:** Chonkie (`RecursiveChunker`), `qdrant-client` (real `:memory:` client in unit tests), the Phase 1 `RoleClient` (TEI `index_embed` role) and `config`.

**Spec:** `docs/superpowers/specs/2026-07-02-maintenance-copilot-design.md`
**Builds on:** Phase 1 (`config.py`, `client.py`, `copilot.py` health command) — all committed on `design/maintenance-copilot`.

## Global Constraints

- Line length ≤ 100 (Black + Ruff). Type hints on public functions; Google-style docstrings.
- Tests run with `uv run pytest`. Module tests live at `tests/test_maintenance_copilot_*.py`, load module files via `importlib`, and register each loaded module in `sys.modules` under a unique sentinel name immediately after `module_from_spec` (Python 3.14 dataclass requirement, established in Phase 1).
- Module scripts add `sys.path.insert(0, str(Path(__file__).resolve().parent))` before sibling imports (`import config`, `import client`).
- Module-local only — no imports from `atria/`.
- Unit tests must NOT hit the network: use `QdrantClient(":memory:")` for real store behavior, and inject a deterministic fake embedding function (do not call TEI).
- Sample-manual fixtures live at `modules/maintenance_copilot/sample_manuals/` (TRACKED — they are source fixtures, not runtime state). Runtime index state stays under `modules/maintenance_copilot/data/` (gitignored).
- Retrieval defaults to the current revision (version-awareness); superseded revisions are queryable only when explicitly requested.
- Commits must NOT include a `Co-Authored-By: Claude` trailer.
- Branch: `design/maintenance-copilot` (already checked out). Do not create branches.

---

### Task 1: Synthetic sample corpus + document parser

**Files:**
- Create: `modules/maintenance_copilot/sample_manuals/amm_ata32.md`
- Create: `modules/maintenance_copilot/sample_manuals/mel_ata32.md`
- Create: `modules/maintenance_copilot/sample_manuals/cdl_ata52.md`
- Create: `modules/maintenance_copilot/sample_manuals/tsm_ata32.md`
- Create: `modules/maintenance_copilot/scripts/corpus.py`
- Test: `tests/test_maintenance_copilot_corpus.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Document` with fields `doc_type: str`, `title: str`, `revision: str`, `effective_date: str`, `ata_chapter: str`, `path: str`, `text: str`.
  - `parse_document(path: str) -> Document` — reads a `.md`/`.txt` file, parses leading YAML-style front-matter delimited by `---` lines, and returns a `Document`. Missing front-matter keys raise `ValueError` naming the missing key.
  - `load_corpus(root: str) -> list[Document]` — parses every `.md`/`.txt` file directly under `root`, sorted by filename.

- [ ] **Step 1: Create the four sample manual fixtures**

Each file begins with front-matter then prose. Create `modules/maintenance_copilot/sample_manuals/amm_ata32.md`:

```markdown
---
doc_type: AMM
title: Landing Gear — Main Gear Removal/Installation
revision: Rev-42
effective_date: 2026-05-01
ata_chapter: "32"
---

# 32-11-00 Main Landing Gear

## Task 32-11-00-000-801 — Removal of the Main Landing Gear

Warning: Make sure the aircraft is on jacks and the gear is safetied before
removal. Depressurize the hydraulic system per AMM 29-00-00.

1. Remove the retraction actuator (AMM 32-31-00).
2. Disconnect the brake hydraulic lines and cap them.
3. Support the gear leg and remove the main pivot pin.

## Task 32-11-00-400-801 — Installation of the Main Landing Gear

Install in reverse order. Torque the pivot pin nut to 1200 in-lb.
```

Create `modules/maintenance_copilot/sample_manuals/mel_ata32.md`:

```markdown
---
doc_type: MEL
title: Minimum Equipment List — ATA 32 Landing Gear
revision: Rev-18
effective_date: 2026-06-01
ata_chapter: "32"
---

# MEL 32-30-01 — Landing Gear Position Indicating

Category: C. Number installed: 3. Number required for dispatch: 2.

Placarding required: Placard the affected gear position indicator INOP.
One indicator may be inoperative provided alternate procedures are established
and used. Repair interval: 10 calendar days (Category C).
```

Create `modules/maintenance_copilot/sample_manuals/cdl_ata52.md`:

```markdown
---
doc_type: CDL
title: Configuration Deviation List — ATA 52 Doors
revision: Rev-07
effective_date: 2026-04-15
ata_chapter: "52"
---

# CDL 52-10-1 — Access Panel 191AB

Aircraft may be dispatched with access panel 191AB missing.
Performance penalty: 5 kg additional fuel per flight hour. No placard required.
```

Create `modules/maintenance_copilot/sample_manuals/tsm_ata32.md`:

```markdown
---
doc_type: TSM
title: Troubleshooting Manual — ATA 32 Landing Gear
revision: Rev-31
effective_date: 2026-05-20
ata_chapter: "32"
---

# TSM 32-31 — Gear Fails to Retract

Fault code 32-3101: Retraction actuator does not extend.

Step 1: Check hydraulic pressure at the actuator (AMM 29-00-00).
Step 2: Inspect the retraction actuator wiring for continuity.
Step 3: If pressure and wiring are good, replace the actuator per AMM 32-31-00.
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_maintenance_copilot_corpus.py
"""Tests for the maintenance_copilot document parser + sample corpus."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MOD_ROOT = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot"
_CORPUS_PY = _MOD_ROOT / "scripts" / "corpus.py"
_SAMPLES = _MOD_ROOT / "sample_manuals"


def _load():
    spec = importlib.util.spec_from_file_location("mc_corpus_uut", _CORPUS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["mc_corpus_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_document_reads_frontmatter_and_body():
    mod = _load()
    doc = mod.parse_document(str(_SAMPLES / "amm_ata32.md"))
    assert doc.doc_type == "AMM"
    assert doc.revision == "Rev-42"
    assert doc.ata_chapter == "32"
    assert "Main Landing Gear" in doc.text
    # Body must exclude the front-matter delimiters.
    assert "doc_type:" not in doc.text


def test_parse_document_missing_key_raises():
    mod = _load()
    tmp = _SAMPLES.parent / "data" / "_bad.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("---\ndoc_type: AMM\n---\nbody", encoding="utf-8")
    try:
        with pytest.raises(ValueError) as exc:
            mod.parse_document(str(tmp))
        assert "title" in str(exc.value)
    finally:
        tmp.unlink()


def test_load_corpus_returns_all_four_sorted():
    mod = _load()
    docs = mod.load_corpus(str(_SAMPLES))
    assert [d.doc_type for d in docs] == ["AMM", "CDL", "MEL", "TSM"]  # sorted by filename
    assert {d.ata_chapter for d in docs} == {"32", "52"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_corpus.py -v`
Expected: FAIL — `corpus.py` does not exist (`spec` load error / `AttributeError`).

- [ ] **Step 4: Write `corpus.py`**

```python
# modules/maintenance_copilot/scripts/corpus.py
"""Parse maintenance documents into structured Document records.

A source file starts with a ``---``-delimited front-matter block declaring
``doc_type``, ``title``, ``revision``, ``effective_date``, and ``ata_chapter``,
followed by the document body. Only ``.md`` / ``.txt`` are handled in the pilot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

_REQUIRED = ("doc_type", "title", "revision", "effective_date", "ata_chapter")


@dataclass(frozen=True)
class Document:
    """A parsed maintenance document: front-matter metadata plus body text."""

    doc_type: str
    title: str
    revision: str
    effective_date: str
    ata_chapter: str
    path: str
    text: str


def _split_frontmatter(raw: str) -> tuple[Dict[str, str], str]:
    """Return (metadata, body). Front-matter is a leading ``---`` ... ``---`` block."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta: Dict[str, str] = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        key, sep, value = lines[i].partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip('"').strip("'")
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return meta, body


def parse_document(path: str) -> Document:
    """Parse a single ``.md``/``.txt`` file into a :class:`Document`.

    Args:
        path: Filesystem path to the document.

    Returns:
        The parsed document.

    Raises:
        ValueError: If a required front-matter key is missing.
    """
    raw = Path(path).read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    for key in _REQUIRED:
        if key not in meta:
            raise ValueError(f"{path}: missing front-matter key {key!r}")
    return Document(
        doc_type=meta["doc_type"],
        title=meta["title"],
        revision=meta["revision"],
        effective_date=meta["effective_date"],
        ata_chapter=str(meta["ata_chapter"]),
        path=path,
        text=body,
    )


def load_corpus(root: str) -> List[Document]:
    """Parse every ``.md``/``.txt`` directly under ``root``, sorted by filename."""
    paths = sorted(
        p for p in Path(root).iterdir() if p.suffix in (".md", ".txt") and p.is_file()
    )
    return [parse_document(str(p)) for p in paths]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_corpus.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/sample_manuals modules/maintenance_copilot/scripts/corpus.py \
        tests/test_maintenance_copilot_corpus.py
git commit -m "feat(maintenance_copilot): synthetic sample manuals + document parser"
```

---

### Task 2: Chunking with citation anchors

**Files:**
- Create: `modules/maintenance_copilot/scripts/chunking.py`
- Modify: `modules/maintenance_copilot/requirements.txt` (add `chonkie`)
- Test: `tests/test_maintenance_copilot_chunking.py`

**Interfaces:**
- Consumes: `corpus.Document` from Task 1.
- Produces:
  - `@dataclass(frozen=True) ChunkRecord` with fields `chunk_id: str`, `text: str`, `start_index: int`, `end_index: int`, `token_count: int`, `doc_type: str`, `title: str`, `revision: str`, `ata_chapter: str`, `source_path: str`, `citation: str`.
  - `chunk_document(doc: Document, chunker=None) -> list[ChunkRecord]` — splits `doc.text` with a Chonkie `RecursiveChunker` (default `chunk_size=512`); `chunker` is injectable for tests. `chunk_id` is `f"{Path(doc.path).stem}#{i}"`; `citation` is `f"{doc.doc_type} {doc.title} ({doc.revision}) · {chunk_id}"`.

- [ ] **Step 1: Add the dependency**

Add `chonkie` to `modules/maintenance_copilot/requirements.txt` (append a line):

```text
chonkie>=1.0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_maintenance_copilot_chunking.py
"""Tests for maintenance_copilot chunking + citation anchors."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeChunk:
    def __init__(self, text, start_index, end_index, token_count):
        self.text = text
        self.start_index = start_index
        self.end_index = end_index
        self.token_count = token_count


class _FakeChunker:
    """Splits on blank lines so tests are deterministic and offline."""

    def chunk(self, text):
        chunks = []
        cursor = 0
        for para in text.split("\n\n"):
            start = text.index(para, cursor)
            end = start + len(para)
            cursor = end
            chunks.append(_FakeChunk(para, start, end, len(para.split())))
        return chunks


def _sample_doc(corpus):
    return corpus.Document(
        doc_type="AMM", title="Landing Gear", revision="Rev-42",
        effective_date="2026-05-01", ata_chapter="32",
        path="/x/amm_ata32.md", text="Para one text.\n\nPara two text here.",
    )


def test_chunk_document_builds_records_with_citation_and_offsets():
    corpus = _load("corpus", "mc_corpus_for_chunk")
    chunking = _load("chunking", "mc_chunking_uut")
    recs = chunking.chunk_document(_sample_doc(corpus), chunker=_FakeChunker())
    assert len(recs) == 2
    assert recs[0].chunk_id == "amm_ata32#0"
    assert recs[0].citation == "AMM Landing Gear (Rev-42) · amm_ata32#0"
    # Offsets index back into the original text.
    assert _sample_doc(corpus).text[recs[1].start_index:recs[1].end_index] == recs[1].text
    assert recs[0].ata_chapter == "32" and recs[0].revision == "Rev-42"


def test_chunk_document_carries_metadata_to_every_record():
    corpus = _load("corpus", "mc_corpus_for_chunk2")
    chunking = _load("chunking", "mc_chunking_uut2")
    recs = chunking.chunk_document(_sample_doc(corpus), chunker=_FakeChunker())
    assert all(r.doc_type == "AMM" and r.source_path.endswith("amm_ata32.md") for r in recs)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_chunking.py -v`
Expected: FAIL — `chunking.py` does not exist.

- [ ] **Step 4: Write `chunking.py`**

```python
# modules/maintenance_copilot/scripts/chunking.py
"""Split a Document into chunk records carrying citation anchors.

Uses Chonkie's ``RecursiveChunker`` (structure-aware, no embedding model). Each
chunk keeps its character offsets so a returned passage can be traced back to
the exact span of the source document.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Document  # type: ignore[import-not-found]


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk plus the metadata needed to cite and filter it."""

    chunk_id: str
    text: str
    start_index: int
    end_index: int
    token_count: int
    doc_type: str
    title: str
    revision: str
    ata_chapter: str
    source_path: str
    citation: str


def _default_chunker():
    from chonkie import RecursiveChunker  # local import: heavy optional dep

    return RecursiveChunker(chunk_size=512)


def chunk_document(doc: Document, chunker: Optional[object] = None) -> List[ChunkRecord]:
    """Chunk ``doc.text`` into citation-anchored records.

    Args:
        doc: The parsed document to split.
        chunker: An object with ``.chunk(text) -> list`` of chunk objects
            exposing ``text``, ``start_index``, ``end_index``, ``token_count``.
            Defaults to a Chonkie ``RecursiveChunker``.

    Returns:
        One :class:`ChunkRecord` per chunk, in document order.
    """
    ch = chunker or _default_chunker()
    stem = Path(doc.path).stem
    records: List[ChunkRecord] = []
    for i, chunk in enumerate(ch.chunk(doc.text)):
        chunk_id = f"{stem}#{i}"
        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                text=chunk.text,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                token_count=chunk.token_count,
                doc_type=doc.doc_type,
                title=doc.title,
                revision=doc.revision,
                ata_chapter=doc.ata_chapter,
                source_path=doc.path,
                citation=f"{doc.doc_type} {doc.title} ({doc.revision}) · {chunk_id}",
            )
        )
    return records
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_chunking.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/scripts/chunking.py \
        modules/maintenance_copilot/requirements.txt \
        tests/test_maintenance_copilot_chunking.py
git commit -m "feat(maintenance_copilot): RecursiveChunker chunking with citation anchors"
```

---

### Task 3: Qdrant index store (embed + upsert + version-aware query)

**Files:**
- Create: `modules/maintenance_copilot/scripts/index_store.py`
- Test: `tests/test_maintenance_copilot_index_store.py`

**Interfaces:**
- Consumes: `chunking.ChunkRecord` (Task 2); `client.RoleClient` (Phase 1) for embeddings.
- Produces:
  - `COLLECTION = "manual_chunks"`.
  - `class IndexStore(qdrant, embed_fn, collection=COLLECTION)` — `qdrant` is a `QdrantClient`; `embed_fn(texts: list[str]) -> list[list[float]]` (in production, `lambda ts: role_client.embed("index_embed", ts)`).
  - `IndexStore.ensure_collection(dim: int) -> None` — creates the collection with cosine distance if absent.
  - `IndexStore.upsert_chunks(records: list[ChunkRecord]) -> int` — embeds each record's text, upserts one point per record (payload holds all `ChunkRecord` fields plus `text`), returns the count.
  - `IndexStore.query(text, k=5, ata_chapter=None, revision="current") -> list[dict]` — embeds `text`, searches top-k. When `revision="current"`, filter to the latest revision per doc_type that was indexed; when a specific revision string is passed, filter to it; when `revision=None`, no revision filter. Each hit dict has `score`, `citation`, `text`, `doc_type`, `revision`, `ata_chapter`, `chunk_id`.
  - `IndexStore.list_indexed() -> dict` and `IndexStore.reset() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_copilot_index_store.py
"""Tests for the Qdrant-backed index store (real in-memory Qdrant, fake embeddings)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _rec(chunking, chunk_id, text, revision="Rev-42", ata="32", doc_type="AMM"):
    return chunking.ChunkRecord(
        chunk_id=chunk_id, text=text, start_index=0, end_index=len(text),
        token_count=len(text.split()), doc_type=doc_type, title="T",
        revision=revision, ata_chapter=ata, source_path=f"/x/{chunk_id}.md",
        citation=f"{doc_type} T ({revision}) · {chunk_id}",
    )


def _embed_fn(texts):
    # Deterministic 3-dim vectors: keyword presence for "gear"/"door"/"brake".
    out = []
    for t in texts:
        low = t.lower()
        out.append([
            1.0 if "gear" in low else 0.0,
            1.0 if "door" in low else 0.0,
            1.0 if "brake" in low else 0.0,
        ])
    return out


@pytest.fixture()
def store():
    from qdrant_client import QdrantClient
    chunking = _load("chunking", "mc_chunking_for_store")
    index_store = _load("index_store", "mc_index_store_uut")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    return s, chunking, index_store


def test_upsert_then_query_ranks_relevant_chunk_first(store):
    s, chunking, _ = store
    n = s.upsert_chunks([
        _rec(chunking, "amm_ata32#0", "Main landing gear removal"),
        _rec(chunking, "cdl_ata52#0", "Access door panel missing", ata="52", doc_type="CDL"),
    ])
    assert n == 2
    hits = s.query("gear leg", k=1, revision=None)
    assert len(hits) == 1
    assert hits[0]["chunk_id"] == "amm_ata32#0"
    assert hits[0]["citation"].startswith("AMM T (Rev-42)")


def test_query_filters_by_ata_chapter(store):
    s, chunking, _ = store
    s.upsert_chunks([
        _rec(chunking, "amm_ata32#0", "gear removal"),
        _rec(chunking, "cdl_ata52#0", "door panel", ata="52", doc_type="CDL"),
    ])
    hits = s.query("door", k=5, ata_chapter="52", revision=None)
    assert [h["chunk_id"] for h in hits] == ["cdl_ata52#0"]


def test_query_current_revision_excludes_superseded(store):
    s, chunking, _ = store
    s.upsert_chunks([
        _rec(chunking, "amm_old#0", "gear removal old", revision="Rev-41"),
        _rec(chunking, "amm_new#0", "gear removal new", revision="Rev-42"),
    ])
    hits = s.query("gear", k=5, revision="current")
    ids = [h["chunk_id"] for h in hits]
    assert "amm_new#0" in ids and "amm_old#0" not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_index_store.py -v`
Expected: FAIL — `index_store.py` does not exist.

- [ ] **Step 3: Write `index_store.py`**

```python
# modules/maintenance_copilot/scripts/index_store.py
"""Qdrant-backed vector index for manual chunks.

Embeds chunk text with an injected ``embed_fn`` (production: TEI via the
``index_embed`` role) and stores one point per chunk with its full metadata
payload. Queries are version-aware: by default only the latest indexed revision
per ``doc_type`` is searched.
"""

from __future__ import annotations

import uuid
from typing import Callable, Dict, List, Optional

from qdrant_client import QdrantClient, models

COLLECTION = "manual_chunks"

# Fixed namespace so uuid5(citation) is stable across processes → idempotent re-index.
_POINT_NS = uuid.UUID("6f6b1e2a-1c1a-4f2b-9a3e-2b0c7c9d4e11")

EmbedFn = Callable[[List[str]], List[List[float]]]


class IndexStore:
    """Create/populate/query the ``manual_chunks`` collection."""

    def __init__(self, qdrant: QdrantClient, embed_fn: EmbedFn, collection: str = COLLECTION):
        self._q = qdrant
        self._embed = embed_fn
        self._collection = collection

    def ensure_collection(self, dim: int) -> None:
        """Create the collection with cosine distance if it does not exist."""
        if self._q.collection_exists(self._collection):
            return
        self._q.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )

    def upsert_chunks(self, records: List[object]) -> int:
        """Embed and upsert one point per record. Returns the number stored.

        Point ids are a stable ``uuid5`` of the citation, so re-indexing the
        same chunk (even in a new process) updates in place rather than
        duplicating.
        """
        if not records:
            return 0
        vectors = self._embed([r.text for r in records])  # type: ignore[attr-defined]
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(_POINT_NS, rec.citation)),  # type: ignore[attr-defined]
                vector=vec,
                payload={
                    "chunk_id": rec.chunk_id,          # type: ignore[attr-defined]
                    "text": rec.text,                  # type: ignore[attr-defined]
                    "doc_type": rec.doc_type,          # type: ignore[attr-defined]
                    "title": rec.title,                # type: ignore[attr-defined]
                    "revision": rec.revision,          # type: ignore[attr-defined]
                    "ata_chapter": rec.ata_chapter,    # type: ignore[attr-defined]
                    "source_path": rec.source_path,    # type: ignore[attr-defined]
                    "citation": rec.citation,          # type: ignore[attr-defined]
                },
            )
            for rec, vec in zip(records, vectors)
        ]
        self._q.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    def _latest_revision_by_doctype(self) -> Dict[str, str]:
        """Scan payloads to find the max revision string per doc_type."""
        latest: Dict[str, str] = {}
        offset = None
        while True:
            recs, offset = self._q.scroll(
                collection_name=self._collection, with_payload=True, limit=256, offset=offset
            )
            for r in recs:
                dt = r.payload["doc_type"]
                rev = r.payload["revision"]
                if dt not in latest or rev > latest[dt]:
                    latest[dt] = rev
            if offset is None:
                break
        return latest

    def query(
        self,
        text: str,
        k: int = 5,
        ata_chapter: Optional[str] = None,
        revision: Optional[str] = "current",
    ) -> List[Dict]:
        """Embed ``text`` and return the top-``k`` filtered hits.

        Args:
            text: The query text.
            k: Max hits to return.
            ata_chapter: If set, restrict to this ATA chapter.
            revision: ``"current"`` (latest per doc_type), a specific revision
                string, or ``None`` for no revision filter.

        Returns:
            Hit dicts with score, citation, text, and metadata.
        """
        must: List[models.FieldCondition] = []
        if ata_chapter is not None:
            must.append(
                models.FieldCondition(key="ata_chapter", match=models.MatchValue(value=ata_chapter))
            )
        should_current = revision == "current"
        if revision is not None and not should_current:
            must.append(
                models.FieldCondition(key="revision", match=models.MatchValue(value=revision))
            )
        vector = self._embed([text])[0]
        result = self._q.query_points(
            collection_name=self._collection,
            query=vector,
            limit=k if not should_current else max(k * 4, k),
            query_filter=models.Filter(must=must) if must else None,
        )
        latest = self._latest_revision_by_doctype() if should_current else {}
        hits: List[Dict] = []
        for point in result.points:
            p = point.payload
            if should_current and p["revision"] != latest.get(p["doc_type"]):
                continue
            hits.append(
                {
                    "score": point.score,
                    "citation": p["citation"],
                    "text": p["text"],
                    "doc_type": p["doc_type"],
                    "revision": p["revision"],
                    "ata_chapter": p["ata_chapter"],
                    "chunk_id": p["chunk_id"],
                }
            )
            if len(hits) >= k:
                break
        return hits

    def list_indexed(self) -> Dict:
        """Return the point count and the latest revision per doc_type."""
        count = self._q.count(collection_name=self._collection).count
        return {"count": count, "latest_revision": self._latest_revision_by_doctype()}

    def reset(self) -> None:
        """Delete the collection if it exists."""
        if self._q.collection_exists(self._collection):
            self._q.delete_collection(self._collection)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_index_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/maintenance_copilot/scripts/index_store.py \
        tests/test_maintenance_copilot_index_store.py
git commit -m "feat(maintenance_copilot): Qdrant index store with version-aware query"
```

---

### Task 4: CLI wiring — `ingest` / `index` / `query` / `list` / `reset`

**Files:**
- Modify: `modules/maintenance_copilot/scripts/copilot.py` (add subcommands; add a helper that builds an `IndexStore` from config + `RoleClient`)
- Test: `tests/test_maintenance_copilot_ingest_cli.py`

**Interfaces:**
- Consumes: `corpus.load_corpus`, `chunking.chunk_document`, `index_store.IndexStore`, `client.RoleClient`, `config.load_config` (all prior).
- Produces (additions to `copilot.py`):
  - `_build_store(embed_fn=None, qdrant=None) -> IndexStore` — builds an `IndexStore` from `MC_QDRANT_URL` and a `RoleClient` `index_embed` embedder; both injectable for tests.
  - Subcommands, each printing JSON and returning 0 on success:
    - `ingest [--samples DIR]` — parse + chunk + upsert the corpus (default DIR = the module's `sample_manuals/`); prints `{"documents": N, "chunks": M}`.
    - `index` — alias of `ingest` for the default corpus (spec parity).
    - `query "<text>" [--ata NN] [--k 5] [--revision current]` — prints `{"query": ..., "hits": [...]}`.
    - `list` — prints `IndexStore.list_indexed()`.
    - `reset` — drops the collection; prints `{"reset": true}`.
  - `EMBED_DIM = 1024` module constant (TEI `Qwen/Qwen3-Embedding-0.6B` output dim; used by `ensure_collection`). Add a code comment that this must match the deployed TEI model.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_copilot_ingest_cli.py
"""Tests for the ingest/query CLI wiring (in-memory Qdrant, fake embeddings)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_CLI = (
    Path(__file__).resolve().parent.parent
    / "modules" / "maintenance_copilot" / "scripts" / "copilot.py"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("mc_ingest_cli_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_ingest_cli_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def _embed_fn(texts):
    out = []
    for t in texts:
        low = t.lower()
        out.append([1.0 if "gear" in low else 0.0, 1.0 if "door" in low else 0.0,
                    1.0 if "brake" in low else 0.0])
    return out


@pytest.fixture()
def cli(monkeypatch):
    mod = _load_cli()
    from qdrant_client import QdrantClient
    shared = QdrantClient(":memory:")

    def fake_build_store(embed_fn=None, qdrant=None):
        store = mod.IndexStore(shared, _embed_fn)  # type: ignore[attr-defined]
        store.ensure_collection(dim=3)
        return store

    monkeypatch.setattr(mod, "_build_store", fake_build_store)
    return mod


def test_ingest_then_query_returns_cited_hits(cli, capsys):
    rc = cli.main(["ingest"])
    assert rc == 0
    ingest_out = json.loads(capsys.readouterr().out)
    assert ingest_out["documents"] == 4 and ingest_out["chunks"] >= 4

    rc = cli.main(["query", "main landing gear removal", "--k", "2", "--revision", "current"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["query"] == "main landing gear removal"
    assert len(out["hits"]) >= 1
    assert all("citation" in h for h in out["hits"])
    assert any(h["doc_type"] == "AMM" for h in out["hits"])


def test_query_ata_filter_narrows_results(cli, capsys):
    cli.main(["ingest"])
    capsys.readouterr()
    cli.main(["query", "door panel", "--ata", "52", "--revision", "none"])
    out = json.loads(capsys.readouterr().out)
    assert all(h["ata_chapter"] == "52" for h in out["hits"])


def test_reset_clears_index(cli, capsys):
    cli.main(["ingest"])
    capsys.readouterr()
    rc = cli.main(["reset"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["reset"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_ingest_cli.py -v`
Expected: FAIL — the new subcommands / `_build_store` / `IndexStore` symbol are not in `copilot.py`.

- [ ] **Step 3: Extend `copilot.py`**

Add these imports near the existing sibling imports (after `from client import RoleClient`):

```python
from corpus import load_corpus  # type: ignore[import-not-found]
from chunking import chunk_document  # type: ignore[import-not-found]
from index_store import IndexStore  # type: ignore[import-not-found]
```

Add the module constant near the top (after imports):

```python
# Output dimension of the deployed TEI embedding model (Qwen3-Embedding-0.6B).
# Must match the model configured for the index_embed role.
EMBED_DIM = 1024


def _samples_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "sample_manuals")


def _build_store(embed_fn=None, qdrant=None) -> IndexStore:
    """Build an IndexStore from MC_QDRANT_URL + a RoleClient index_embed embedder."""
    from qdrant_client import QdrantClient

    if qdrant is None:
        qdrant = QdrantClient(url=_env("MC_QDRANT_URL", "http://localhost:6333"))
    if embed_fn is None:
        rc = RoleClient(load_config())
        embed_fn = lambda texts: rc.embed("index_embed", texts)  # noqa: E731
    store = IndexStore(qdrant, embed_fn)
    store.ensure_collection(dim=EMBED_DIM)
    return store
```

Add subcommand handlers:

```python
def _cmd_ingest(samples: str) -> int:
    store = _build_store()
    docs = load_corpus(samples)
    total = 0
    for doc in docs:
        total += store.upsert_chunks(chunk_document(doc))
    print(json.dumps({"documents": len(docs), "chunks": total}, indent=2))
    return 0


def _cmd_query(text: str, k: int, ata: Optional[str], revision: str) -> int:
    rev: Optional[str] = None if revision.lower() == "none" else revision
    store = _build_store()
    hits = store.query(text, k=k, ata_chapter=ata, revision=rev)
    print(json.dumps({"query": text, "hits": hits}, indent=2))
    return 0


def _cmd_list() -> int:
    print(json.dumps(_build_store().list_indexed(), indent=2))
    return 0


def _cmd_reset() -> int:
    _build_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0
```

Extend `build_parser()` (add after the existing `health` subparser):

```python
    p_ingest = sub.add_parser("ingest", help="Parse + chunk + index the sample manuals.")
    p_ingest.add_argument("--samples", default=None, help="Corpus dir (default: sample_manuals/).")
    sub.add_parser("index", help="Alias of ingest for the default corpus.")
    p_query = sub.add_parser("query", help="Retrieve top cited passages for a question.")
    p_query.add_argument("text")
    p_query.add_argument("--ata", default=None, help="Restrict to an ATA chapter.")
    p_query.add_argument("--k", type=int, default=5, help="Max hits (default 5).")
    p_query.add_argument("--revision", default="current",
                         help="'current' (default), a revision string, or 'none'.")
    sub.add_parser("list", help="Show index stats.")
    sub.add_parser("reset", help="Delete the index collection.")
```

Extend `main()` dispatch (add branches alongside `health`):

```python
    if args.command in ("ingest", "index"):
        return _cmd_ingest(args.samples if getattr(args, "samples", None) else _samples_dir())
    if args.command == "query":
        return _cmd_query(args.text, args.k, args.ata, args.revision)
    if args.command == "list":
        return _cmd_list()
    if args.command == "reset":
        return _cmd_reset()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_ingest_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full module suite + lint**

Run: `uv run pytest tests/test_maintenance_copilot_*.py -v`
Expected: PASS (all Phase 1 + Phase 2 tests).
Run: `uv run ruff check modules/maintenance_copilot tests/test_maintenance_copilot_*.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/scripts/copilot.py \
        tests/test_maintenance_copilot_ingest_cli.py
git commit -m "feat(maintenance_copilot): ingest/query/list/reset CLI over Qdrant"
```

- [ ] **Step 7: Real end-to-end (deferred — needs live TEI + Qdrant)**

Record for a Docker host (not run in CI/sandbox):

```bash
docker compose -f docker-compose.dev.yml up -d tei qdrant
docker compose -f docker-compose.dev.yml exec atria \
    python /app/modules/maintenance_copilot/scripts/copilot.py ingest
docker compose -f docker-compose.dev.yml exec atria \
    python /app/modules/maintenance_copilot/scripts/copilot.py query "gear fails to retract" --ata 32
```

Expected: `ingest` reports 4 documents / several chunks; `query` returns TSM/AMM hits for ATA 32 with citations. Confirm `EMBED_DIM` matches the live TEI model's output dimension (adjust the constant if the deployed model differs).

---

## Phase 2 self-review

- **Spec coverage (Phase 2 slice):** parse sample corpus → Task 1; RecursiveChunker + citation anchors (spec §4 step 2, as amended) → Task 2; TEI embed + Qdrant upsert with metadata payload + version-aware/ATA-filtered retrieval (spec §4.1, §4.3) → Task 3; `ingest`/`index`/`query`/`list`/`reset` (spec §5) → Task 4. LLM answer-synthesis, mandatory-citation post-validation, confidence thresholds, and the audit trail are Phase 4 — intentionally excluded here (`query` returns ranked cited passages, not a synthesized answer).
- **Placeholder scan:** none — every step ships runnable code or an exact command.
- **Type consistency:** `Document` (Task 1) is consumed as-is by `chunk_document` (Task 2); `ChunkRecord` fields (Task 2) are read by `IndexStore.upsert_chunks` payload (Task 3) and surfaced in `query` hit dicts; `IndexStore` constructor/`ensure_collection`/`upsert_chunks`/`query`/`list_indexed`/`reset` names match between definition (Task 3) and CLI use (Task 4); `_build_store`/`IndexStore`/`EMBED_DIM` names match between `copilot.py` and its test.
- **Known follow-up for review:** `EMBED_DIM = 1024` is an assumption about the TEI model's output dim; Task 4 Step 7 flags verifying it against the live model (adjust the constant if the deployed model differs). Point ids use `uuid5(_POINT_NS, citation)` — stable across processes, so re-ingest updates in place.

## Roadmap — remaining phases (each its own plan)

- **Phase 3 — Knowledge graph:** `kg_extract` LLM → strict-JSON entities/edges, Neo4j schema, provenance/confidence/`status`, `graph` command + multi-hop context in `query`.
- **Phase 4 — Validation & guardrails + synthesis:** `validate`, `recommend-refs`, `check`; LLM answer synthesis grounded in retrieved chunks; citation post-validation, confidence thresholds, advisory-only framing, `data/audit.log.jsonl`.
- **Phase 5 — Dashboard:** Query / Graph / Audit tabs on `dashboard.html` via the module bridge.
