# EK Knowledge Graph (Permission-Aware GraphRAG) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Neo4j knowledge graph to the `enterprise_knowledge` (EK) module that improves retrieval quality (GraphRAG) while preserving EK's permission-aware, cited, Vietnamese-only answers.

**Architecture:** Two build passes over EK's existing corpus — a deterministic metadata/tag backbone (no LLM) plus an optional, cached LLM entity/relation extraction pass — write an `:EKNode`-labeled subgraph into the shared Neo4j service. At query time, vector hits seed an ACL-filtered graph expansion whose candidate chunks are re-checked with the *same* `acl.can_access` predicate as the vector path, merged, and fed to the existing synthesis. Graph is fully optional: disabled or unreachable → behavior is byte-identical to today's vector-only pipeline.

**Tech Stack:** Python 3.10+, Neo4j 5 (Community, `neo4j>=5.24` driver, Cypher), Qdrant (existing), Chonkie (existing), OpenAI-compatible clients (existing `RoleClient`), pytest + pytest-asyncio (`asyncio_mode=auto`).

## Global Constraints

- **Line length 100**; Black + Ruff; mypy strict; Google-style docstrings (verbatim from repo `pyproject.toml`).
- **No prompt tables** — plain prose/bullets in any LLM prompt (CLAUDE.md).
- **Module scripts import siblings by bare name** after `sys.path.insert(0, str(Path(__file__).resolve().parent))`; tests load them via the `importlib.util.spec_from_file_location(sentinel, ...)` `_load` helper (repo convention — see existing `tests/test_enterprise_knowledge_*.py`).
- **Scripts print JSON to stdout** (`json.dumps(..., ensure_ascii=False, indent=2)`) and resolve repo paths from `__file__`, never CWD.
- **ACL single source of truth:** `acl.can_access(user, {"classification":..., "department":...})` is the authoritative gate on *every* chunk that reaches synthesis or citations, on both retrieval paths. Cypher-level filtering is a first-line optimization only.
- **Namespace isolation:** every EK graph node carries the label `:EKNode` (plus its type label). All EK reads/writes/reset are scoped to `:EKNode` so EK never reads or deletes `maintenance_copilot` graph data. (Realizes the spec's `namespace="ek"`.)
- **Vietnamese-only answers** and existing citation/guardrail behavior are unchanged; synthesis interface is untouched.
- **Graph is optional:** `EK_GRAPH_ENABLED=0` (default) → `query` is vector-only; `EK_GRAPH_EXTRACT=0` (default) → build is metadata-backbone only.

## Interfaces defined by this plan (consistency reference)

New module `graph_store.py`:
- `NS_LABEL = "EKNode"`
- `RunFn = Callable[[str, dict], list]`
- `class EKGraphStore(run_fn: RunFn)` with:
  - `ensure_constraints() -> None`
  - `upsert_document(doc: dict) -> None` — keys: `doc_id,title,department,classification,owner,knowledge_space,last_updated,tags(list[str])`
  - `upsert_chunk(chunk: dict) -> None` — keys: `chunk_id,doc_id,text,title,department,classification,knowledge_space,citation`
  - `upsert_extraction(chunk_id: str, ext: GraphExtraction) -> tuple[int, int]`
  - `neighbors_via_entities(seed_chunk_ids: list[str], hops: int, acl: dict, limit: int) -> list[dict]`
  - `neighbors_via_tags(seed_chunk_ids: list[str], acl: dict, limit: int) -> list[dict]`
  - `stats() -> dict`
  - `reset() -> None`
- `neo4j_run_fn(driver) -> RunFn`
- `build_driver(env: Mapping[str,str] | None = None) -> object` (reads `EK_NEO4J_URI|USER|PASSWORD`)
- `acl_params(user) -> dict` — `{"is_exec": bool, "dept": str, "open": ["Public","Internal"], "conf": "Confidential"}`

New module `extraction.py` (EK): `ALLOWED_ENTITY_TYPES`, `ALLOWED_EDGE_TYPES`, `Entity`, `Edge`, `GraphExtraction`, `build_extraction_messages(chunk_text)`, `parse_extraction(raw, provenance)`, `extract_graph(chunk_text, chat_fn, provenance)`.

New module `graph_build.py`: `ExtractionCache(path)`, `build_backbone(store, docs, chunk_fn) -> dict`, `build_extraction(store, docs, chunk_fn, chat_fn, cache) -> dict`, `doc_to_node(doc) -> dict`, `chunk_to_node(rec) -> dict`.

New module `graph_retrieval.py`: `expand(store, seed_hits, user, hops, max_neighbors) -> list[dict]`, `merge_hits(vector_hits, graph_hits, cap, boost=0.1) -> list[dict]`.

Changes: `config.py` (+`kg_extract` role), `corpus.py` (+`tags`), `knowledge.py` (+`graph` subcommands, `--graph` on `query`, Neo4j health probe), `requirements.txt` (+`neo4j`), `docker-compose.yml` (+`EK_NEO4J_*`), `SKILL.md`.

---

## Phase 1 — Foundations (deterministic; no LLM, no live Neo4j)

### Task 1: Add the `kg_extract` role to config

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/config.py:17` and `:32-37`
- Test: `tests/test_enterprise_knowledge_config.py` (append)

**Interfaces:**
- Produces: `load_config()` returns a dict that includes key `"kg_extract"` → `RoleConfig`; env overrides `EK_KG_EXTRACT_PROVIDER|MODEL|BASE_URL|API_KEY`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_config.py` (use the file's existing `_load` helper; if the file has none, add the standard one shown in Task 2):

```python
def test_kg_extract_role_present_and_overridable():
    config = _load("config", "ek_config_kg")
    cfg = config.load_config(env={
        "EK_KG_EXTRACT_MODEL": "openai/gpt-4o-mini",
        "EK_KG_EXTRACT_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY": "sk-or-x",
    })
    assert "kg_extract" in cfg
    assert cfg["kg_extract"].model == "openai/gpt-4o-mini"
    assert cfg["kg_extract"].base_url == "https://openrouter.ai/api/v1"
    assert cfg["kg_extract"].api_key == "sk-or-x"  # host-matched fallback key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_config.py::test_kg_extract_role_present_and_overridable -v`
Expected: FAIL with `KeyError: 'kg_extract'` (role not in ROLES).

- [ ] **Step 3: Write minimal implementation**

In `config.py`, extend `ROLES` and `_DEFAULTS`:

```python
ROLES = ("index_embed", "synthesis", "kg_extract")
```

```python
_DEFAULTS: Dict[str, RoleConfig] = {
    "index_embed": RoleConfig("openai", "text-embedding-3-small",
                              "https://api.openai.com/v1", ""),
    "synthesis": RoleConfig("openai", "gpt-4o-mini",
                            "https://api.openai.com/v1", ""),
    # Entity/relation extraction for the knowledge graph. Any chat model works;
    # override per deployment via EK_KG_EXTRACT_* (mirrors EK_SYNTHESIS_*).
    "kg_extract": RoleConfig("openai", "gpt-4o-mini",
                             "https://api.openai.com/v1", ""),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/config.py tests/test_enterprise_knowledge_config.py
git commit -m "feat(enterprise_knowledge): add kg_extract role to graph config"
```

---

### Task 2: Parse `tags` front-matter into Document

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/corpus.py:23-36` (dataclass) and `:81-92` (constructor)
- Test: `tests/test_enterprise_knowledge_corpus.py` (append)

**Interfaces:**
- Produces: `Document.tags: tuple[str, ...]` (empty tuple when the `tags:` key is absent); comma-separated front-matter value split + stripped, empties dropped.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_corpus.py`:

```python
def test_parse_document_reads_tags(tmp_path):
    corpus = _load("corpus", "ek_corpus_tags")
    p = tmp_path / "DOC001.md"
    p.write_text(
        "---\n"
        "doc_id: DOC001\ntitle: Sổ tay\ndepartment: COMP\n"
        "classification: Public\ntags: sổ, company, public\n---\nBody\n",
        encoding="utf-8",
    )
    doc = corpus.parse_document(str(p))
    assert doc.tags == ("sổ", "company", "public")


def test_parse_document_tags_default_empty(tmp_path):
    corpus = _load("corpus", "ek_corpus_notags")
    p = tmp_path / "DOC002.md"
    p.write_text(
        "---\ndoc_id: DOC002\ntitle: X\ndepartment: HR\n"
        "classification: Internal\n---\nBody\n",
        encoding="utf-8",
    )
    assert corpus.parse_document(str(p)).tags == ()
```

If `tests/test_enterprise_knowledge_corpus.py` lacks the `_load` helper, add at the top:

```python
import importlib.util, sys
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"

def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_corpus.py::test_parse_document_reads_tags -v`
Expected: FAIL with `AttributeError: 'Document' object has no attribute 'tags'`.

- [ ] **Step 3: Write minimal implementation**

Add a `tags` field (with default, so existing positional/keyword construction stays valid) to the `Document` dataclass in `corpus.py`, after `text`:

```python
    path: str
    text: str
    tags: tuple[str, ...] = ()
```

Add a parser helper above `parse_document`:

```python
def _parse_tags(raw: str) -> tuple[str, ...]:
    """Split a comma-separated front-matter ``tags`` value into a clean tuple."""
    return tuple(t.strip() for t in raw.split(",") if t.strip())
```

Pass it in the `Document(...)` construction inside `parse_document`:

```python
        path=path,
        text=body,
        tags=_parse_tags(meta.get("tags", "")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_corpus.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/corpus.py tests/test_enterprise_knowledge_corpus.py
git commit -m "feat(enterprise_knowledge): parse document tags for graph seeds"
```

---

### Task 3: Graph store — nodes, constraints, reset, stats (fake run_fn)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/graph_store.py`
- Test: `tests/test_enterprise_knowledge_graph_store.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (self-contained; `GraphExtraction` is imported lazily in Task 6).
- Produces: `EKGraphStore`, `NS_LABEL="EKNode"`, `RunFn`, `neo4j_run_fn`, `build_driver`, `acl_params` (see Interfaces section). `upsert_document`/`upsert_chunk`/`reset`/`stats`/`ensure_constraints` in this task; `upsert_extraction` and `neighbors_*` added in Tasks 6/11.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enterprise_knowledge_graph_store.py`:

```python
"""EKGraphStore tests using an in-memory fake run_fn (no live Neo4j)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeRun:
    """Record every (cypher, params) and return a canned rows list."""

    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    def __call__(self, cypher, params):
        self.calls.append((cypher, params))
        return self._rows


def test_ensure_constraints_covers_all_ek_labels():
    gs = _load("graph_store", "ek_gs_constraints")
    fake = FakeRun()
    gs.EKGraphStore(fake).ensure_constraints()
    joined = " ".join(c for c, _ in fake.calls)
    for label, key in [("EKDocument", "doc_id"), ("EKChunk", "chunk_id"),
                       ("EKEntity", "key"), ("EKTag", "name")]:
        assert f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE" in joined


def test_upsert_document_merges_doc_department_and_tags():
    gs = _load("graph_store", "ek_gs_doc")
    fake = FakeRun()
    gs.EKGraphStore(fake).upsert_document({
        "doc_id": "DOC001", "title": "Sổ tay", "department": "COMP",
        "classification": "Public", "owner": "COMP",
        "knowledge_space": "Company Knowledge", "last_updated": "2025-02-04",
        "tags": ["sổ", "company"],
    })
    cyphers = " ".join(c for c, _ in fake.calls)
    assert "MERGE (d:EKDocument:EKNode {doc_id: $doc_id})" in cyphers
    assert ":IN_DEPARTMENT]->" in cyphers
    assert ":TAGGED]->" in cyphers
    # one TAGGED merge per tag
    assert sum("MERGE (t:EKTag:EKNode {name: $name})" in c for c, _ in fake.calls) == 2


def test_reset_only_deletes_ek_namespace():
    gs = _load("graph_store", "ek_gs_reset")
    fake = FakeRun()
    gs.EKGraphStore(fake).reset()
    assert fake.calls == [("MATCH (n:EKNode) DETACH DELETE n", {})]


def test_acl_params_executive_vs_employee():
    gs = _load("graph_store", "ek_gs_acl")
    ident = _load("identity", "ek_ident_gs")
    ex = gs.acl_params(ident.User("U", "n", "Executive", "EXEC", "Active"))
    emp = gs.acl_params(ident.User("U", "n", "Employee", "ENG", "Active"))
    assert ex["is_exec"] is True
    assert emp["is_exec"] is False and emp["dept"] == "ENG"
    assert emp["open"] == ["Public", "Internal"] and emp["conf"] == "Confidential"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py -v`
Expected: FAIL with `ModuleNotFoundError`/`spec` assertion (file does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `modules/enterprise_knowledge/scripts/graph_store.py`:

```python
"""Neo4j-backed knowledge graph store for the enterprise_knowledge module.

All database access goes through an injected ``run_fn(cypher, params) -> rows``
so unit tests supply a fake and never touch a server. Every EK node carries the
``:EKNode`` label (plus a type label), so all reads, writes, and reset stay
scoped to EK data and never touch a co-located module's graph (the compose
Neo4j is a single shared Community-edition database).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity import User  # type: ignore[import-not-found]

NS_LABEL = "EKNode"
RunFn = Callable[[str, dict], list]

_DOC = "EKDocument"
_CHUNK = "EKChunk"
_ENTITY = "EKEntity"
_TAG = "EKTag"
_DEPT = "EKDepartment"


def acl_params(user: User) -> dict:
    """Cypher parameters mirroring ``acl.build_filter`` for graph traversal.

    The authoritative gate remains ``acl.can_access`` (applied in
    ``graph_retrieval``); these params are a first-line WHERE filter only.
    """
    return {
        "is_exec": user.role == "Executive",
        "dept": user.department,
        "open": ["Public", "Internal"],
        "conf": "Confidential",
    }


class EKGraphStore:
    """Create constraints, upsert the EK subgraph, and query it."""

    def __init__(self, run_fn: RunFn):
        self._run = run_fn

    def ensure_constraints(self) -> None:
        """One uniqueness constraint per EK node label on its key property."""
        for label, key in ((_DOC, "doc_id"), (_CHUNK, "chunk_id"),
                           (_ENTITY, "key"), (_TAG, "name")):
            self._run(
                f"CREATE CONSTRAINT ek_{label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE",
                {},
            )

    def upsert_document(self, doc: dict) -> None:
        """MERGE a Document node plus its Department and Tag edges."""
        self._run(
            f"MERGE (d:{_DOC}:{NS_LABEL} {{doc_id: $doc_id}}) SET d += $props",
            {"doc_id": doc["doc_id"], "props": {
                "title": doc["title"], "department": doc["department"],
                "classification": doc["classification"], "owner": doc.get("owner", ""),
                "knowledge_space": doc.get("knowledge_space", ""),
                "last_updated": doc.get("last_updated", ""),
            }},
        )
        self._run(
            f"MERGE (dep:{_DEPT}:{NS_LABEL} {{department_id: $dept}}) "
            f"WITH dep MATCH (d:{_DOC} {{doc_id: $doc_id}}) "
            "MERGE (d)-[:IN_DEPARTMENT]->(dep)",
            {"dept": doc["department"], "doc_id": doc["doc_id"]},
        )
        for tag in doc.get("tags", []) or []:
            self._run(
                f"MERGE (t:{_TAG}:{NS_LABEL} {{name: $name}}) "
                f"WITH t MATCH (d:{_DOC} {{doc_id: $doc_id}}) "
                "MERGE (d)-[:TAGGED]->(t)",
                {"name": tag, "doc_id": doc["doc_id"]},
            )

    def upsert_chunk(self, chunk: dict) -> None:
        """MERGE a Chunk node (with passage text) and link it to its Document."""
        self._run(
            f"MERGE (c:{_CHUNK}:{NS_LABEL} {{chunk_id: $chunk_id}}) SET c += $props",
            {"chunk_id": chunk["chunk_id"], "props": {
                "doc_id": chunk["doc_id"], "text": chunk["text"],
                "title": chunk["title"], "department": chunk["department"],
                "classification": chunk["classification"],
                "knowledge_space": chunk.get("knowledge_space", ""),
                "citation": chunk["citation"],
            }},
        )
        self._run(
            f"MATCH (c:{_CHUNK} {{chunk_id: $chunk_id}}), (d:{_DOC} {{doc_id: $doc_id}}) "
            "MERGE (c)-[:PART_OF]->(d)",
            {"chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"]},
        )

    def stats(self) -> dict:
        """Return EK node and edge counts."""
        rows = self._run(
            f"MATCH (n:{NS_LABEL}) WITH count(n) AS nodes "
            f"OPTIONAL MATCH (:{NS_LABEL})-[r]->(:{NS_LABEL}) "
            "RETURN nodes, count(r) AS edges",
            {},
        )
        if not rows:
            return {"nodes": 0, "edges": 0}
        return {"nodes": rows[0].get("nodes", 0), "edges": rows[0].get("edges", 0)}

    def reset(self) -> None:
        """Delete every EK node and its relationships (never touches other modules)."""
        self._run(f"MATCH (n:{NS_LABEL}) DETACH DELETE n", {})


def neo4j_run_fn(driver) -> RunFn:
    """Build a run_fn that executes each statement in its own Neo4j session."""

    def _run(cypher: str, params: dict) -> list:
        with driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    return _run


def build_driver(env: Optional[Mapping[str, str]] = None):
    """Construct a Neo4j driver from ``EK_NEO4J_URI|USER|PASSWORD``."""
    from neo4j import GraphDatabase  # local import: heavy optional dep

    src = os.environ if env is None else env
    return GraphDatabase.driver(
        src.get("EK_NEO4J_URI", "bolt://localhost:7687"),
        auth=(src.get("EK_NEO4J_USER", "neo4j"),
              src.get("EK_NEO4J_PASSWORD", "minder-neo4j")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/graph_store.py tests/test_enterprise_knowledge_graph_store.py
git commit -m "feat(enterprise_knowledge): EKGraphStore nodes/constraints/reset (namespaced)"
```

---

## Phase 2 — Ingestion (metadata backbone + optional LLM extraction)

### Task 4: EK entity/relation extraction

**Files:**
- Create: `modules/enterprise_knowledge/scripts/extraction.py`
- Test: `tests/test_enterprise_knowledge_extraction.py`

**Interfaces:**
- Consumes: `budget.input_budget`, `budget.estimate_tokens`, `budget.fit_text` (existing).
- Produces: `ALLOWED_ENTITY_TYPES`, `ALLOWED_EDGE_TYPES`, `Entity`, `Edge`, `GraphExtraction`, `build_extraction_messages`, `parse_extraction`, `extract_graph`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enterprise_knowledge_extraction.py`:

```python
"""EK graph extraction: JSON parsing, allow-list validation, provenance stamping."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_extraction_keeps_allowed_drops_unknown():
    ex = _load("extraction", "ek_ext_parse")
    raw = json.dumps({
        "entities": [
            {"type": "Policy", "key": "leave_policy", "props": {}},
            {"type": "Bogus", "key": "x", "props": {}},   # dropped: unknown type
            {"type": "Concept", "key": "", "props": {}},   # dropped: empty key
        ],
        "relationships": [
            {"type": "RELATED_TO", "src": "leave_policy", "dst": "hr_handbook",
             "confidence": 0.9},
            {"type": "NOPE", "src": "a", "dst": "b"},       # dropped: unknown type
        ],
    })
    out = ex.parse_extraction(raw, {"source_doc": "DOC001", "page": "DOC001#0"})
    assert [e.key for e in out.entities] == ["leave_policy"]
    assert out.entities[0].props["status"] == "unverified"
    assert out.entities[0].props["source_doc"] == "DOC001"
    assert [(e.src_key, e.dst_key) for e in out.edges] == [("leave_policy", "hr_handbook")]
    assert out.edges[0].props["confidence"] == 0.9


def test_parse_extraction_rejects_non_json():
    ex = _load("extraction", "ek_ext_bad")
    with pytest.raises(ValueError):
        ex.parse_extraction("not json at all", {})


def test_extract_graph_calls_chat_fn_and_parses():
    ex = _load("extraction", "ek_ext_call")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return json.dumps({"entities": [{"type": "Concept", "key": "k", "props": {}}],
                           "relationships": []})

    out = ex.extract_graph("Nội dung tiếng Việt", chat_fn, {"source_doc": "DOC002"})
    assert out.entities[0].key == "k"
    assert captured["messages"][0]["role"] == "system"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_extraction.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `modules/enterprise_knowledge/scripts/extraction.py`:

```python
"""Extract enterprise entities/relationships from a chunk via the kg_extract LLM.

The LLM is asked for strict JSON. Output is validated against fixed entity/edge
type allow-lists (unknown types are dropped, not trusted), and every surviving
node/edge is stamped with provenance, a confidence score, and
``status="unverified"`` so an LLM-built graph stays auditable.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import budget  # type: ignore[import-not-found]

ALLOWED_ENTITY_TYPES = frozenset(
    {"Policy", "Process", "Concept", "Person", "Org", "Amount", "Date", "Term"}
)
ALLOWED_EDGE_TYPES = frozenset({"RELATED_TO"})

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class Entity:
    """A graph node: a typed, keyed entity with stamped props."""

    type: str
    key: str
    props: dict


@dataclass(frozen=True)
class Edge:
    """A graph relationship between two entity keys with stamped props."""

    type: str
    src_key: str
    dst_key: str
    props: dict


@dataclass(frozen=True)
class GraphExtraction:
    """The validated entities and edges extracted from one chunk."""

    entities: list[Entity]
    edges: list[Edge]


def build_extraction_messages(chunk_text: str) -> list[dict]:
    """Build the chat messages that ask the LLM for strict-JSON extraction."""
    system = (
        "You extract a knowledge graph from a Vietnamese enterprise document. "
        "Return ONLY JSON, no prose. Shape: "
        '{"entities":[{"type":<T>,"key":<str>,"props":{}}],'
        '"relationships":[{"type":"RELATED_TO","src":<key>,"dst":<key>,'
        '"confidence":<0-1>}]}. '
        f"Entity types: {sorted(ALLOWED_ENTITY_TYPES)}. "
        "Use a short lowercase slug of the entity name as its key (e.g. "
        "'chinh_sach_nghi_phep'). Link two entities with RELATED_TO only when the "
        "text states a real relationship. Omit anything you are unsure of."
    )
    remaining = budget.input_budget("kg_extract") - budget.estimate_tokens(system) - 16
    chunk_text = budget.fit_text(chunk_text, remaining)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": chunk_text},
    ]


def _confidence(raw: object) -> float:
    """Coerce an item-supplied confidence to a 0–1 float, defaulting to 0.5."""
    if isinstance(raw, (int, float)) and 0.0 <= float(raw) <= 1.0:
        return float(raw)
    return 0.5


def _stamp(props: object, provenance: dict, item: dict) -> dict:
    """Merge model props with provenance + status + confidence."""
    base = dict(props) if isinstance(props, dict) else {}
    base.update(provenance)
    base["status"] = "unverified"
    base["confidence"] = _confidence(item.get("confidence"))
    return base


def parse_extraction(raw: str, provenance: dict) -> GraphExtraction:
    """Parse + validate the LLM's JSON into a :class:`GraphExtraction`.

    Args:
        raw: The raw LLM response (may be fenced with ```json).
        provenance: Keys stamped onto every node/edge (e.g. source_doc, page).

    Returns:
        Validated entities/edges; unknown types are dropped.

    Raises:
        ValueError: If ``raw`` is not JSON or lacks the expected shape.
    """
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extraction output is not JSON: {exc}") from exc
    if not isinstance(data, dict) or "entities" not in data or "relationships" not in data:
        raise ValueError("extraction JSON must have 'entities' and 'relationships'")

    entities: list[Entity] = []
    for item in data["entities"]:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_ENTITY_TYPES:
            continue
        if not item.get("key"):
            continue
        entities.append(Entity(type=item["type"], key=str(item["key"]),
                               props=_stamp(item.get("props"), provenance, item)))

    edges: list[Edge] = []
    for item in data["relationships"]:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_EDGE_TYPES:
            continue
        if not item.get("src") or not item.get("dst"):
            continue
        edges.append(Edge(type=item["type"], src_key=str(item["src"]),
                          dst_key=str(item["dst"]),
                          props=_stamp(item.get("props"), provenance, item)))
    return GraphExtraction(entities=entities, edges=edges)


def extract_graph(
    chunk_text: str, chat_fn: Callable[[list], str], provenance: dict
) -> GraphExtraction:
    """Run the kg_extract LLM over ``chunk_text`` and parse its output."""
    raw = chat_fn(build_extraction_messages(chunk_text))
    return parse_extraction(raw, provenance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_extraction.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/extraction.py tests/test_enterprise_knowledge_extraction.py
git commit -m "feat(enterprise_knowledge): LLM entity/relation extraction for the graph"
```

---

### Task 5: Graph store — MENTIONS / RELATED_TO upsert

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/graph_store.py` (add `upsert_extraction`)
- Test: `tests/test_enterprise_knowledge_graph_store.py` (append)

**Interfaces:**
- Consumes: `extraction.GraphExtraction`, `extraction.Entity`, `extraction.Edge` (Task 4).
- Produces: `EKGraphStore.upsert_extraction(chunk_id, ext) -> tuple[int, int]` — MERGEs Entity nodes, `MENTIONS` chunk→entity edges, `RELATED_TO` entity→entity edges.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_graph_store.py`:

```python
def test_upsert_extraction_merges_entities_mentions_and_relations():
    gs = _load("graph_store", "ek_gs_ext")
    ext_mod = _load("extraction", "ek_ext_for_gs")
    fake = FakeRun()
    ext = ext_mod.GraphExtraction(
        entities=[ext_mod.Entity("Policy", "leave", {"status": "unverified"})],
        edges=[ext_mod.Edge("RELATED_TO", "leave", "handbook", {"confidence": 0.8})],
    )
    n, e = gs.EKGraphStore(fake).upsert_extraction("DOC001#0", ext)
    assert (n, e) == (1, 1)
    cyphers = " ".join(c for c, _ in fake.calls)
    assert "MERGE (n:EKEntity:EKNode {key: $key})" in cyphers
    assert ":MENTIONS]->" in cyphers
    assert ":RELATED_TO]->" in cyphers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py::test_upsert_extraction_merges_entities_mentions_and_relations -v`
Expected: FAIL with `AttributeError: 'EKGraphStore' object has no attribute 'upsert_extraction'`.

- [ ] **Step 3: Write minimal implementation**

Add to `EKGraphStore` in `graph_store.py` (after `upsert_chunk`):

```python
    def upsert_extraction(self, chunk_id: str, ext) -> tuple[int, int]:
        """MERGE entities, chunk->entity MENTIONS, and entity->entity RELATED_TO.

        Args:
            chunk_id: The source chunk whose entities these are.
            ext: An ``extraction.GraphExtraction``.

        Returns:
            ``(entity_count, edge_count)`` upserted.
        """
        for ent in ext.entities:
            self._run(
                f"MERGE (n:{_ENTITY}:{NS_LABEL} {{key: $key}}) SET n += $props, n.etype = $etype",
                {"key": ent.key, "props": ent.props, "etype": ent.type},
            )
            self._run(
                f"MATCH (c:{_CHUNK} {{chunk_id: $chunk_id}}), (n:{_ENTITY} {{key: $key}}) "
                "MERGE (c)-[:MENTIONS]->(n)",
                {"chunk_id": chunk_id, "key": ent.key},
            )
        for edge in ext.edges:
            self._run(
                f"MATCH (a:{_ENTITY} {{key: $src}}), (b:{_ENTITY} {{key: $dst}}) "
                "MERGE (a)-[r:RELATED_TO]->(b) SET r += $props",
                {"src": edge.src_key, "dst": edge.dst_key, "props": edge.props},
            )
        return len(ext.entities), len(ext.edges)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/graph_store.py tests/test_enterprise_knowledge_graph_store.py
git commit -m "feat(enterprise_knowledge): upsert entities/MENTIONS/RELATED_TO into the graph"
```

---

### Task 6: Extraction cache + build orchestrator

**Files:**
- Create: `modules/enterprise_knowledge/scripts/graph_build.py`
- Test: `tests/test_enterprise_knowledge_graph_build.py`

**Interfaces:**
- Consumes: `EKGraphStore` (Tasks 3/5), `extraction.extract_graph` (Task 4), `chunk_document` (existing), `corpus.Document` (existing).
- Produces: `doc_to_node(doc) -> dict`, `chunk_to_node(rec) -> dict`, `ExtractionCache(path)`, `build_backbone(store, docs, chunk_fn) -> dict`, `build_extraction(store, docs, chunk_fn, chat_fn, cache) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enterprise_knowledge_graph_build.py`:

```python
"""Graph build orchestration: backbone always, extraction cached + toggled."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class RecordingStore:
    def __init__(self):
        self.docs, self.chunks, self.extractions = [], [], []

    def upsert_document(self, d):
        self.docs.append(d)

    def upsert_chunk(self, c):
        self.chunks.append(c)

    def upsert_extraction(self, chunk_id, ext):
        self.extractions.append(chunk_id)
        return (0, 0)


def _doc(corpus):
    return corpus.Document(
        doc_id="DOC001", title="Sổ tay", department="COMP", classification="Public",
        owner="COMP", knowledge_space="Company Knowledge", last_updated="2025-02-04",
        language="vi", path="/x/DOC001.md", text="đoạn một. đoạn hai.", tags=("sổ",),
    )


def test_build_backbone_upserts_docs_and_chunks():
    gb = _load("graph_build", "ek_gb_backbone")
    corpus = _load("corpus", "ek_corpus_gb")

    def chunk_fn(doc):
        return [type("C", (), {"chunk_id": "DOC001#0", "doc_id": "DOC001",
                               "text": "đoạn một", "title": "Sổ tay", "department": "COMP",
                               "classification": "Public", "knowledge_space": "Company Knowledge",
                               "citation": "Sổ tay [DOC001] · DOC001#0"})()]

    store = RecordingStore()
    stats = gb.build_backbone(store, [_doc(corpus)], chunk_fn)
    assert stats == {"documents": 1, "chunks": 1}
    assert store.docs[0]["tags"] == ["sổ"]
    assert store.chunks[0]["chunk_id"] == "DOC001#0"


def test_build_extraction_skips_cached_chunks(tmp_path):
    gb = _load("graph_build", "ek_gb_extract")
    corpus = _load("corpus", "ek_corpus_gb2")
    calls = {"n": 0}

    def chunk_fn(doc):
        return [type("C", (), {"chunk_id": "DOC001#0", "text": "đoạn một"})()]

    def chat_fn(messages):
        calls["n"] += 1
        return json.dumps({"entities": [], "relationships": []})

    cache = gb.ExtractionCache(str(tmp_path / "cache.json"))
    store = RecordingStore()
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, cache)
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, cache)  # 2nd run cached
    assert calls["n"] == 1  # LLM called once; second run served from cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_build.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `modules/enterprise_knowledge/scripts/graph_build.py`:

```python
"""Build the EK knowledge graph from the corpus.

Two passes: a deterministic backbone (Document/Chunk/Tag/Department nodes and
their structural edges — no LLM), and an optional LLM extraction pass that adds
Entity/MENTIONS/RELATED_TO. Extraction is cached by chunk-content hash so a
rebuild re-upserts from cache without re-calling the (rate-limited) LLM.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extraction  # type: ignore[import-not-found]


def doc_to_node(doc) -> dict:
    """Project a ``corpus.Document`` into the node dict ``upsert_document`` wants."""
    return {
        "doc_id": doc.doc_id, "title": doc.title, "department": doc.department,
        "classification": doc.classification, "owner": doc.owner,
        "knowledge_space": doc.knowledge_space, "last_updated": doc.last_updated,
        "tags": list(doc.tags),
    }


def chunk_to_node(rec) -> dict:
    """Project a ``chunking.ChunkRecord`` into the node dict ``upsert_chunk`` wants."""
    return {
        "chunk_id": rec.chunk_id, "doc_id": rec.doc_id, "text": rec.text,
        "title": rec.title, "department": rec.department,
        "classification": rec.classification,
        "knowledge_space": getattr(rec, "knowledge_space", ""), "citation": rec.citation,
    }


class ExtractionCache:
    """A JSON sidecar mapping chunk-content hash -> serialized GraphExtraction."""

    def __init__(self, path: str):
        self._path = Path(path)
        self._data: dict = {}
        if self._path.is_file():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    @staticmethod
    def key(text: str) -> str:
        """Stable content hash for a chunk's text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str):
        """Return a cached ``GraphExtraction`` for ``text`` or ``None``."""
        item = self._data.get(self.key(text))
        if item is None:
            return None
        return extraction.GraphExtraction(
            entities=[extraction.Entity(**e) for e in item["entities"]],
            edges=[extraction.Edge(**x) for x in item["edges"]],
        )

    def put(self, text: str, ext) -> None:
        """Cache ``ext`` for ``text`` and flush to disk."""
        self._data[self.key(text)] = {
            "entities": [{"type": e.type, "key": e.key, "props": e.props}
                         for e in ext.entities],
            "edges": [{"type": x.type, "src_key": x.src_key, "dst_key": x.dst_key,
                       "props": x.props} for x in ext.edges],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")


def build_backbone(store, docs, chunk_fn: Callable) -> dict:
    """Upsert Document/Chunk/Tag/Department nodes and structural edges (no LLM)."""
    n_docs = n_chunks = 0
    for doc in docs:
        store.upsert_document(doc_to_node(doc))
        n_docs += 1
        for rec in chunk_fn(doc):
            store.upsert_chunk(chunk_to_node(rec))
            n_chunks += 1
    return {"documents": n_docs, "chunks": n_chunks}


def build_extraction(store, docs, chunk_fn: Callable, chat_fn: Callable,
                     cache: ExtractionCache) -> dict:
    """Extract Entity/RELATED_TO per chunk (LLM), cached by content hash."""
    n_chunks = n_llm = 0
    for doc in docs:
        for rec in chunk_fn(doc):
            n_chunks += 1
            ext = cache.get(rec.text)
            if ext is None:
                ext = extraction.extract_graph(
                    rec.text, chat_fn, {"source_doc": rec.doc_id, "page": rec.chunk_id}
                )
                cache.put(rec.text, ext)
                n_llm += 1
            store.upsert_extraction(rec.chunk_id, ext)
    return {"chunks": n_chunks, "llm_calls": n_llm}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_build.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/graph_build.py tests/test_enterprise_knowledge_graph_build.py
git commit -m "feat(enterprise_knowledge): graph build orchestrator + cached extraction"
```

---

### Task 7: `graph` CLI subcommands (build/stats/reset)

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/knowledge.py` (parser + dispatch + `_build_graph_store`)
- Test: `tests/test_enterprise_knowledge_cli.py` (append)

**Interfaces:**
- Consumes: `graph_store` (build_driver, neo4j_run_fn, EKGraphStore), `graph_build`, `RoleClient`.
- Produces: CLI verbs `graph build [--extract] [--samples ...]`, `graph stats`, `graph reset`; helper `_build_graph_store(run_fn=None) -> EKGraphStore`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_cli.py` (uses the file's existing `_load`/`build_parser` conventions):

```python
def test_parser_accepts_graph_build_and_flags():
    knowledge = _load("knowledge", "ek_cli_graph")
    args = knowledge.build_parser().parse_args(["graph", "build", "--extract"])
    assert args.command == "graph" and args.graph_command == "build" and args.extract is True


def test_parser_accepts_graph_stats_and_reset():
    knowledge = _load("knowledge", "ek_cli_graph2")
    a = knowledge.build_parser().parse_args(["graph", "stats"])
    b = knowledge.build_parser().parse_args(["graph", "reset"])
    assert a.graph_command == "stats" and b.graph_command == "reset"


def test_query_parser_has_graph_flag():
    knowledge = _load("knowledge", "ek_cli_graph3")
    args = knowledge.build_parser().parse_args(["query", "q", "--user", "U001", "--graph"])
    assert args.graph is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py -k graph -v`
Expected: FAIL (`invalid choice: 'graph'` / no `--graph`).

- [ ] **Step 3: Write minimal implementation**

In `knowledge.py`, add imports near the top sibling imports:

```python
import graph_store  # type: ignore[import-not-found]
import graph_build  # type: ignore[import-not-found]
```

Add a graph-store builder next to `_build_store`:

```python
def _build_graph_store(run_fn: Callable | None = None) -> "graph_store.EKGraphStore":
    """Build an EKGraphStore from EK_NEO4J_* (or an injected run_fn for tests)."""
    if run_fn is None:
        run_fn = graph_store.neo4j_run_fn(graph_store.build_driver())
    return graph_store.EKGraphStore(run_fn)


def _kg_extract_chat_fn() -> Callable[[list], str]:
    rc = RoleClient(load_config())
    return lambda messages: rc.chat("kg_extract", messages)
```

Add command handlers:

```python
def _cmd_graph_build(samples: str, extract: bool) -> int:
    store = _build_graph_store()
    store.ensure_constraints()
    docs = load_corpus(samples)
    stats = graph_build.build_backbone(store, docs, chunk_document)
    if extract:
        cache = graph_build.ExtractionCache(
            str(Path(__file__).resolve().parent.parent / "data" / "graph_extract_cache.json")
        )
        stats["extraction"] = graph_build.build_extraction(
            store, docs, chunk_document, _kg_extract_chat_fn(), cache
        )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def _cmd_graph_stats() -> int:
    print(json.dumps(_build_graph_store().stats(), indent=2, ensure_ascii=False))
    return 0


def _cmd_graph_reset() -> int:
    _build_graph_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0
```

In `build_parser()`, add the `graph` subcommand group before `return parser`:

```python
    p_graph = sub.add_parser("graph", help="Knowledge-graph build/inspect (GraphRAG).")
    gsub = p_graph.add_subparsers(dest="graph_command", required=True)
    g_build = gsub.add_parser("build", help="Build backbone (+ optional LLM extraction).")
    g_build.add_argument("--samples", default=None)
    g_build.add_argument("--extract", action="store_true",
                         help="Also run the LLM entity/relation pass.")
    gsub.add_parser("stats", help="Show graph node/edge counts.")
    gsub.add_parser("reset", help="Delete all EK graph nodes.")
```

Add `--graph` to the existing `query` parser (after the `--users` line):

```python
    p_query.add_argument("--graph", action="store_true",
                         help="Expand retrieval with the knowledge graph (GraphRAG).")
```

In `main()`, add dispatch inside the `try` block:

```python
        if args.command == "graph":
            if args.graph_command == "build":
                return _cmd_graph_build(args.samples or _samples_dir(), args.extract)
            if args.graph_command == "stats":
                return _cmd_graph_stats()
            if args.graph_command == "reset":
                return _cmd_graph_reset()
            return 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py -k graph -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/knowledge.py tests/test_enterprise_knowledge_cli.py
git commit -m "feat(enterprise_knowledge): graph build/stats/reset CLI + --graph query flag"
```

---

## Phase 3 — Retrieval (ACL-filtered expansion + merge)

### Task 8: Graph traversal (entity + tag neighbors, ACL-filtered in Cypher)

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/graph_store.py` (add `neighbors_via_entities`, `neighbors_via_tags`)
- Test: `tests/test_enterprise_knowledge_graph_store.py` (append)

**Interfaces:**
- Produces:
  - `neighbors_via_entities(seed_chunk_ids: list[str], hops: int, acl: dict, limit: int) -> list[dict]`
  - `neighbors_via_tags(seed_chunk_ids: list[str], acl: dict, limit: int) -> list[dict]`
  - Each returns candidate chunk dicts: `{chunk_id, doc_id, text, title, department, classification, knowledge_space, citation}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_graph_store.py`:

```python
def test_neighbors_via_entities_builds_acl_scoped_cypher():
    gs = _load("graph_store", "ek_gs_nbr_e")
    rows = [{"chunk_id": "DOC002#0", "doc_id": "DOC002", "text": "t", "title": "T",
             "department": "COMP", "classification": "Internal",
             "knowledge_space": "Company Knowledge", "citation": "c"}]
    fake = FakeRun(rows)
    acl = {"is_exec": False, "dept": "ENG", "open": ["Public", "Internal"],
           "conf": "Confidential"}
    out = gs.EKGraphStore(fake).neighbors_via_entities(["DOC001#0"], hops=1, acl=acl, limit=20)
    assert out == rows
    cypher, params = fake.calls[0]
    assert ":MENTIONS]->" in cypher and "RELATED_TO" in cypher
    assert "$is_exec" in cypher and "$open" in cypher and "$conf" in cypher
    assert params["seeds"] == ["DOC001#0"] and params["dept"] == "ENG"
    assert "*0..1" in cypher  # hops inlined as a sanitized int


def test_neighbors_via_tags_builds_acl_scoped_cypher():
    gs = _load("graph_store", "ek_gs_nbr_t")
    fake = FakeRun([])
    acl = {"is_exec": True, "dept": "EXEC", "open": ["Public", "Internal"],
           "conf": "Confidential"}
    gs.EKGraphStore(fake).neighbors_via_tags(["DOC001#0"], acl=acl, limit=10)
    cypher, params = fake.calls[0]
    assert ":TAGGED]" in cypher and ":PART_OF]" in cypher
    assert params["seeds"] == ["DOC001#0"] and params["limit"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py -k neighbors -v`
Expected: FAIL with `AttributeError` (methods missing).

- [ ] **Step 3: Write minimal implementation**

Add to `EKGraphStore` in `graph_store.py`. Note the shared ACL WHERE fragment and the sanitized-int hop bound (Cypher cannot parameterize var-length bounds):

```python
    _ACL_WHERE = (
        "(cand.classification IN $open OR $is_exec "
        "OR (cand.classification = $conf AND cand.department = $dept))"
    )

    @staticmethod
    def _return_chunk(var: str = "cand") -> str:
        return (
            f"RETURN DISTINCT {var}.chunk_id AS chunk_id, {var}.doc_id AS doc_id, "
            f"{var}.text AS text, {var}.title AS title, {var}.department AS department, "
            f"{var}.classification AS classification, "
            f"{var}.knowledge_space AS knowledge_space, {var}.citation AS citation"
        )

    def neighbors_via_entities(self, seed_chunk_ids, hops, acl, limit) -> list[dict]:
        """Candidate chunks reachable seed-chunk → entity → RELATED_TO* → entity → chunk."""
        depth = max(0, int(hops))
        cypher = (
            f"MATCH (c:{_CHUNK})-[:MENTIONS]->(seed:{_ENTITY}) "
            "WHERE c.chunk_id IN $seeds "
            f"MATCH (seed)-[:RELATED_TO*0..{depth}]-(rel:{_ENTITY}) "
            f"MATCH (rel)<-[:MENTIONS]-(cand:{_CHUNK}) "
            "WHERE NOT cand.chunk_id IN $seeds AND " + self._ACL_WHERE + " "
            + self._return_chunk() + " LIMIT $limit"
        )
        return self._run(cypher, {"seeds": list(seed_chunk_ids), "limit": int(limit), **acl})

    def neighbors_via_tags(self, seed_chunk_ids, acl, limit) -> list[dict]:
        """Candidate chunks in documents sharing a tag with a seed chunk's document."""
        cypher = (
            f"MATCH (c:{_CHUNK})-[:PART_OF]->(:{_DOC})-[:TAGGED]->(t:{_TAG}) "
            "WHERE c.chunk_id IN $seeds "
            f"MATCH (t)<-[:TAGGED]-(:{_DOC})<-[:PART_OF]-(cand:{_CHUNK}) "
            "WHERE NOT cand.chunk_id IN $seeds AND " + self._ACL_WHERE + " "
            + self._return_chunk() + " LIMIT $limit"
        )
        return self._run(cypher, {"seeds": list(seed_chunk_ids), "limit": int(limit), **acl})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_store.py -k neighbors -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/graph_store.py tests/test_enterprise_knowledge_graph_store.py
git commit -m "feat(enterprise_knowledge): ACL-scoped graph neighbor traversal (entities + tags)"
```

---

### Task 9: Retrieval expansion + merge, with authoritative ACL re-check

**Files:**
- Create: `modules/enterprise_knowledge/scripts/graph_retrieval.py`
- Test: `tests/test_enterprise_knowledge_graph_retrieval.py`

**Interfaces:**
- Consumes: `EKGraphStore.neighbors_*`, `graph_store.acl_params`, `acl.can_access`, `identity.User`.
- Produces: `expand(store, seed_hits, user, hops, max_neighbors) -> list[dict]` (ACL-safe graph chunks), `merge_hits(vector_hits, graph_hits, cap, boost=0.1) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enterprise_knowledge_graph_retrieval.py`:

```python
"""Graph retrieval: ACL re-check on graph candidates, and vector+graph merge."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class StubStore:
    """Returns preset candidates, incl. one the user must NOT be able to access."""

    def __init__(self, ent, tag):
        self._ent, self._tag = ent, tag

    def neighbors_via_entities(self, seeds, hops, acl, limit):
        return self._ent

    def neighbors_via_tags(self, seeds, acl, limit):
        return self._tag


def _chunk(cid, cls, dept):
    return {"chunk_id": cid, "doc_id": cid.split("#")[0], "text": "t", "title": "T",
            "department": dept, "classification": cls,
            "knowledge_space": "Department Knowledge", "citation": f"[{cid}]"}


def test_expand_drops_forbidden_candidate_even_if_store_returns_it():
    gr = _load("graph_retrieval", "ek_gr_expand")
    identity = _load("identity", "ek_ident_gr")
    # Store leaks a Confidential HR chunk to an ENG employee; expand() MUST drop it.
    store = StubStore(
        ent=[_chunk("DOC050#0", "Confidential", "HR"), _chunk("DOC002#0", "Internal", "COMP")],
        tag=[],
    )
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    out = gr.expand(store, [{"chunk_id": "DOC001#0"}], eng, hops=1, max_neighbors=20)
    ids = {h["chunk_id"] for h in out}
    assert "DOC002#0" in ids
    assert "DOC050#0" not in ids  # authoritative acl.can_access re-check blocks it


def test_merge_dedups_and_appends_graph_only_below_vector():
    gr = _load("graph_retrieval", "ek_gr_merge")
    vector = [{"chunk_id": "A#0", "score": 0.9, "citation": "[A]"},
              {"chunk_id": "B#0", "score": 0.5, "citation": "[B]"}]
    graph = [{"chunk_id": "B#0", "citation": "[B]"},          # dup of a vector hit
             {"chunk_id": "C#0", "citation": "[C]"}]          # graph-only
    merged = gr.merge_hits(vector, graph, cap=10, boost=0.1)
    ids = [h["chunk_id"] for h in merged]
    assert ids[:2] == ["A#0", "B#0"]          # vector hits lead
    assert "C#0" in ids                         # graph-only appended
    assert merged[0]["score"] >= merged[1]["score"]  # ordering preserved


def test_merge_respects_cap():
    gr = _load("graph_retrieval", "ek_gr_cap")
    vector = [{"chunk_id": "A#0", "score": 0.9, "citation": "[A]"}]
    graph = [{"chunk_id": f"G{i}#0", "citation": f"[G{i}]"} for i in range(10)]
    assert len(gr.merge_hits(vector, graph, cap=3)) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_retrieval.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `modules/enterprise_knowledge/scripts/graph_retrieval.py`:

```python
"""Query-time GraphRAG expansion for the enterprise_knowledge module.

Vector hits seed a graph traversal (entity- and tag-based). Every candidate
chunk the graph returns is re-checked with the authoritative ``acl.can_access``
predicate — the same gate as the vector path — before it can enter synthesis.
The graph never grants access; it only surfaces candidate chunks faster.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import acl  # type: ignore[import-not-found]
import graph_store  # type: ignore[import-not-found]


def expand(store, seed_hits, user, hops: int, max_neighbors: int) -> list[dict]:
    """Return ACL-safe graph-neighbor chunks for the given vector seed hits.

    Args:
        store: An ``EKGraphStore`` (or compatible) exposing ``neighbors_*``.
        seed_hits: Vector hits; each must carry ``chunk_id``.
        user: The querying identity (RBAC scope).
        hops: Entity-graph traversal depth.
        max_neighbors: Per-strategy candidate cap.

    Returns:
        Candidate chunk dicts (same shape as vector hits) that pass
        ``acl.can_access`` — de-duplicated across the entity and tag strategies.
    """
    seeds = [h["chunk_id"] for h in seed_hits if h.get("chunk_id")]
    if not seeds:
        return []
    aclp = graph_store.acl_params(user)
    candidates = (
        store.neighbors_via_entities(seeds, hops, aclp, max_neighbors)
        + store.neighbors_via_tags(seeds, aclp, max_neighbors)
    )
    safe: list[dict] = []
    seen: set[str] = set()
    for cand in candidates:
        cid = cand["chunk_id"]
        if cid in seen:
            continue
        decision = acl.can_access(
            user, {"classification": cand["classification"], "department": cand["department"]}
        )
        if decision.allowed:
            seen.add(cid)
            safe.append(cand)
    return safe


def merge_hits(vector_hits, graph_hits, cap: int, boost: float = 0.1) -> list[dict]:
    """Merge vector and graph hits: vector leads (with a connectivity boost),
    graph-only chunks are appended below, de-duplicated, capped at ``cap``.
    """
    graph_ids = {h["chunk_id"] for h in graph_hits}
    merged: list[dict] = []
    seen: set[str] = set()
    for hit in vector_hits:
        h = dict(hit)
        if h["chunk_id"] in graph_ids:  # connectivity boost (Approach B)
            h["score"] = float(h.get("score", 0.0)) * (1.0 + boost)
        merged.append(h)
        seen.add(h["chunk_id"])
    merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    floor = min((float(h.get("score", 0.0)) for h in vector_hits), default=0.0)
    for gh in graph_hits:
        if gh["chunk_id"] in seen:
            continue
        g = dict(gh)
        g.setdefault("score", max(0.0, floor - 1e-3))  # rank below vector hits
        merged.append(g)
        seen.add(g["chunk_id"])
    return merged[:cap]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_retrieval.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/graph_retrieval.py tests/test_enterprise_knowledge_graph_retrieval.py
git commit -m "feat(enterprise_knowledge): ACL-safe graph expansion + vector/graph merge"
```

---

### Task 10: Wire `--graph` into the query command (with vector-only fallback)

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/knowledge.py` (`_cmd_query`, `main` dispatch)
- Test: `tests/test_enterprise_knowledge_cli.py` (append)

**Interfaces:**
- Consumes: `graph_retrieval.expand/merge_hits`, `_build_graph_store`, `guard_accessible` (existing).
- Produces: `_cmd_query(..., graph: bool, graph_store_obj=None)`; when `graph=True`, expands + merges + re-guards before synthesis; on any graph error, logs and falls back to vector-only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_cli.py`:

```python
def test_cmd_query_graph_merges_safe_graph_hits(capsys, monkeypatch):
    knowledge = _load("knowledge", "ek_cli_qgraph")

    class FakeStore:
        def query(self, text, k, acl_filter, department=None):
            return [{"score": 0.9, "citation": "[A]", "text": "a", "doc_id": "DOCA",
                     "chunk_id": "DOCA#0", "title": "A", "department": "COMP",
                     "classification": "Public", "knowledge_space": "Company Knowledge"}]

    class FakeGraphStore:
        def neighbors_via_entities(self, seeds, hops, acl, limit):
            return [{"chunk_id": "DOCB#0", "doc_id": "DOCB", "text": "b", "title": "B",
                     "department": "COMP", "classification": "Internal",
                     "knowledge_space": "Company Knowledge", "citation": "[B]"}]

        def neighbors_via_tags(self, seeds, acl, limit):
            return []

    # Point the user resolver at a known user without touching the real CSV.
    monkeypatch.setenv("EK_USERS_CSV", str(_MOD.parent / "access" / "users.csv"))
    rc = knowledge._cmd_query(
        "q", "U001", 5, None, synthesize=False, users_path=None,
        store=FakeStore(), graph=True, graph_store_obj=FakeGraphStore(),
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    ids = {h["chunk_id"] for h in out["hits"]}
    assert {"DOCA#0", "DOCB#0"} <= ids  # vector + safe graph hit both present
```

(If `json`/`_MOD` are not imported in this test file, add `import json` and the `_MOD`/`_load` block from Task 2.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py::test_cmd_query_graph_merges_safe_graph_hits -v`
Expected: FAIL with `TypeError` (`_cmd_query` has no `graph`/`graph_store_obj` parameters).

- [ ] **Step 3: Write minimal implementation**

Add the import near the other sibling imports in `knowledge.py`:

```python
import graph_retrieval  # type: ignore[import-not-found]
```

Change the `_cmd_query` signature and insert the graph step after the initial vector retrieval + guard. Replace the current body from the `hits = store.query(...)` line through the `guard_accessible` line with:

```python
def _cmd_query(text: str, user_id: str, k: int, department: str | None,
               synthesize: bool, users_path: str | None, store: IndexStore | None = None,
               graph: bool = False, graph_store_obj: object | None = None) -> int:
    user = _resolve_user(user_id, users_path)
    if store is None:
        store = _build_store()
    hits = store.query(text, k=k, acl_filter=acl.build_filter(user), department=department)
    hits, blocked = guard_accessible(user, hits)
    if graph:
        hits = _augment_with_graph(text, user, hits, k, graph_store_obj)
```

Add the augmentation helper above `_cmd_query` (graph settings read inline, matching the module's decentralized env style; any graph error degrades to vector-only):

```python
def _augment_with_graph(text: str, user: "identity.User", hits: list[dict], k: int,
                        graph_store_obj: object | None) -> list[dict]:
    """Expand ``hits`` with ACL-safe graph neighbors; fall back to ``hits`` on error."""
    try:
        gs = graph_store_obj or _build_graph_store()
        hops = int(_env("EK_GRAPH_HOPS", "1"))
        max_neighbors = int(_env("EK_GRAPH_MAX_NEIGHBORS", "20"))
        graph_hits = graph_retrieval.expand(gs, hits, user, hops, max_neighbors)
        merged = graph_retrieval.merge_hits(hits, graph_hits, cap=max(k, len(hits)))
        safe, _blocked = guard_accessible(user, merged)  # belt-and-suspenders re-check
        return safe
    except Exception as exc:  # noqa: BLE001 - graph is optional; never fail the query
        print(f"[graph] disabled for this query: {exc}", file=sys.stderr)
        return hits
```

Update the `main()` dispatch for `query` to pass the flag:

```python
        if args.command == "query":
            return _cmd_query(args.text, args.user, args.k, args.department,
                              args.synthesize, args.users, graph=args.graph)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py -k query -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/knowledge.py tests/test_enterprise_knowledge_cli.py
git commit -m "feat(enterprise_knowledge): --graph augments query with vector-only fallback"
```

---

### Task 11: ACL leakage regression test (end-to-end, in-memory)

**Files:**
- Test: `tests/test_enterprise_knowledge_graph_acl_leakage.py`

**Interfaces:**
- Consumes: `graph_retrieval.expand`, `EKGraphStore` with a fake `run_fn` backed by an in-memory graph.

This task is a test-only safety net: it proves the graph path cannot leak a document a user may not see, across matrix corners. It has no production code change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enterprise_knowledge_graph_acl_leakage.py`:

```python
"""Adversarial: the graph path must never surface a chunk the user can't access.

We wire an EKGraphStore to a tiny in-memory graph where a permitted seed chunk's
entity links to Restricted and other-department Confidential chunks, then assert
those never survive expand() for a non-executive.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


# An in-memory graph: seed entity 'e' is mentioned by the seed chunk and by three
# candidate chunks of different classifications/departments.
_CANDIDATES = {
    "pub": {"chunk_id": "DOCP#0", "doc_id": "DOCP", "text": "t", "title": "P",
            "department": "COMP", "classification": "Public",
            "knowledge_space": "Company Knowledge", "citation": "[P]"},
    "conf_hr": {"chunk_id": "DOCH#0", "doc_id": "DOCH", "text": "t", "title": "H",
                "department": "HR", "classification": "Confidential",
                "knowledge_space": "Department Knowledge", "citation": "[H]"},
    "restricted": {"chunk_id": "DOCR#0", "doc_id": "DOCR", "text": "t", "title": "R",
                   "department": "EXEC", "classification": "Restricted",
                   "knowledge_space": "Executive Knowledge", "citation": "[R]"},
}


def _acl_ok(cand, aclp):
    return (cand["classification"] in aclp["open"] or aclp["is_exec"]
            or (cand["classification"] == aclp["conf"] and cand["department"] == aclp["dept"]))


def _run_fn(cypher, params):
    # Emulate the Cypher ACL WHERE using the same params expand() passes down.
    if ":MENTIONS]->" in cypher:
        return [c for c in _CANDIDATES.values() if _acl_ok(c, params)]
    return []  # no tag edges in this fixture


@pytest.mark.parametrize("role,dept,expected_ids", [
    ("Employee", "ENG", {"DOCP#0"}),                     # only Public survives
    ("Employee", "HR", {"DOCP#0", "DOCH#0"}),            # + own-dept Confidential
    ("Executive", "EXEC", {"DOCP#0", "DOCH#0", "DOCR#0"}),  # sees all
])
def test_graph_expand_never_leaks(role, dept, expected_ids):
    gs_mod = _load("graph_store", f"ek_leak_gs_{role}_{dept}")
    gr = _load("graph_retrieval", f"ek_leak_gr_{role}_{dept}")
    identity = _load("identity", f"ek_leak_id_{role}_{dept}")
    store = gs_mod.EKGraphStore(_run_fn)
    user = identity.User("U", "n", role, dept, "Active")
    out = gr.expand(store, [{"chunk_id": "SEED#0"}], user, hops=1, max_neighbors=20)
    assert {h["chunk_id"] for h in out} == expected_ids
```

- [ ] **Step 2: Run test to verify it fails (then passes) — confirm the safety net holds**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_acl_leakage.py -v`
Expected: PASS immediately (the production ACL re-check from Task 9 already enforces this). If any case FAILS, stop — it means `graph_retrieval.expand` is leaking; fix `expand` before proceeding.

- [ ] **Step 3: (No production change — this task locks in the invariant.)**

- [ ] **Step 4: Run the full graph test set**

Run: `uv run pytest tests/test_enterprise_knowledge_graph_acl_leakage.py tests/test_enterprise_knowledge_graph_retrieval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_enterprise_knowledge_graph_acl_leakage.py
git commit -m "test(enterprise_knowledge): adversarial ACL-leakage guard for the graph path"
```

---

## Phase 4 — Validation & operations

### Task 12: Neo4j health probe

**Files:**
- Modify: `modules/enterprise_knowledge/scripts/knowledge.py` (`_cmd_health`)
- Test: `tests/test_enterprise_knowledge_cli.py` (append)

**Interfaces:**
- Produces: `health` output includes a `neo4j` key (`"ok"` / `"error: ..."`); health still never raises.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enterprise_knowledge_cli.py`:

```python
def test_health_reports_neo4j_key(capsys, monkeypatch):
    knowledge = _load("knowledge", "ek_cli_health_neo4j")
    # Force the neo4j probe to fail fast (no server) — health must still return a dict.
    monkeypatch.setenv("EK_NEO4J_URI", "bolt://127.0.0.1:59999")
    knowledge._cmd_health()
    out = json.loads(capsys.readouterr().out)
    assert "neo4j" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py::test_health_reports_neo4j_key -v`
Expected: FAIL with `KeyError: 'neo4j'`.

- [ ] **Step 3: Write minimal implementation**

In `_cmd_health` in `knowledge.py`, add a neo4j probe after the `qdrant` probe:

```python
    def neo4j_probe() -> None:
        driver = graph_store.build_driver()
        try:
            graph_store.neo4j_run_fn(driver)("RETURN 1 AS ok", {})
        finally:
            driver.close()

    probe("neo4j", neo4j_probe)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_cli.py::test_health_reports_neo4j_key -v`
Expected: PASS (the probe records `error: ...`, `neo4j` key present).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/knowledge.py tests/test_enterprise_knowledge_cli.py
git commit -m "feat(enterprise_knowledge): neo4j reachability in health check"
```

---

### Task 13: Offline eval harness (Public_Evaluation: ACL + recall)

**Files:**
- Create: `modules/enterprise_knowledge/tools/sync_eval.py` (xlsx → CSV fixture)
- Create: `modules/enterprise_knowledge/access/public_evaluation.csv` (committed fixture subset — see Step 1)
- Create: `modules/enterprise_knowledge/scripts/evaluate.py` (offline runner)
- Test: `tests/test_enterprise_knowledge_evaluate.py`

**Interfaces:**
- Produces: `evaluate.load_cases(path) -> list[dict]`; `evaluate.run_case(case, query_fn) -> dict` returning `{question_id, permission_ok, doc_recall_hit}`; `evaluate.summarize(results) -> dict`.

- [ ] **Step 1: Create the committed eval fixture (small, representative)**

Create `modules/enterprise_knowledge/access/public_evaluation.csv` with the matrix-corner cases already used in the ACL tests (columns copied from the dataset's `Public_Evaluation` sheet). This keeps the eval offline and committed; `tools/sync_eval.py` (Step 4) regenerates the full 52-row version from the workspace xlsx.

```csv
question_id,user_id,user_role,user_department,question_vi,expected_permission,expected_document_id
P010,U001,Employee,HR,Chính sách nghỉ phép của phòng nhân sự?,Allow,DOC007
P009,U004,Employee,ENG,Khung lương phòng nhân sự?,Deny,DOC007
P008,U007,Executive,EXEC,Tài liệu chiến lược điều hành?,Allow,DOC020
P007,U010,Employee,PROD,Tài liệu điều hành mật?,Deny,DOC020
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_enterprise_knowledge_evaluate.py`:

```python
"""Offline eval harness over the Public_Evaluation fixture."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"
_ACCESS = _MOD.parent / "access"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_cases_reads_fixture():
    ev = _load("evaluate", "ek_eval_load")
    cases = ev.load_cases(str(_ACCESS / "public_evaluation.csv"))
    assert len(cases) >= 4
    assert cases[0]["expected_permission"] in ("Allow", "Deny")


def test_run_case_scores_permission_and_recall():
    ev = _load("evaluate", "ek_eval_run")

    # Fake query_fn: Allow-with-expected-doc returns that doc; Deny returns no hits.
    def query_fn(question, user_id):
        if user_id == "U001":
            return {"hits": [{"doc_id": "DOC007"}]}
        return {"hits": []}

    allow_case = {"question_id": "P010", "user_id": "U001", "expected_permission": "Allow",
                  "expected_document_id": "DOC007", "question_vi": "?"}
    deny_case = {"question_id": "P009", "user_id": "U004", "expected_permission": "Deny",
                 "expected_document_id": "DOC007", "question_vi": "?"}
    r_allow = ev.run_case(allow_case, query_fn)
    r_deny = ev.run_case(deny_case, query_fn)
    assert r_allow["permission_ok"] and r_allow["doc_recall_hit"]
    assert r_deny["permission_ok"] and not r_deny["doc_recall_hit"]


def test_summarize_counts_regressions():
    ev = _load("evaluate", "ek_eval_sum")
    results = [{"permission_ok": True, "doc_recall_hit": True},
               {"permission_ok": False, "doc_recall_hit": False}]
    s = ev.summarize(results)
    assert s["total"] == 2 and s["permission_regressions"] == 1 and s["recall_hits"] == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_enterprise_knowledge_evaluate.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 4: Write minimal implementation**

Create `modules/enterprise_knowledge/scripts/evaluate.py`:

```python
"""Offline evaluation over the dataset's Public_Evaluation cases.

For each labeled case, checks two things against a ``query_fn``:
- permission_ok: an Allow case returns >=1 hit; a Deny case returns none.
- doc_recall_hit: the expected_document_id appears among returned hits (Allow only).

Used to prove graph-augmented retrieval keeps every Allow/Deny outcome and does
not reduce expected-document recall vs. the vector-only baseline.
"""
from __future__ import annotations

import csv
from typing import Callable


def load_cases(path: str) -> list[dict]:
    """Load evaluation cases from a Public_Evaluation CSV export."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def run_case(case: dict, query_fn: Callable[[str, str], dict]) -> dict:
    """Score one case against ``query_fn(question_vi, user_id) -> {"hits": [...]}``."""
    result = query_fn(case["question_vi"], case["user_id"])
    hits = result.get("hits", [])
    doc_ids = {h.get("doc_id") for h in hits}
    is_allow = case["expected_permission"] == "Allow"
    permission_ok = bool(hits) == is_allow
    doc_recall_hit = is_allow and case.get("expected_document_id") in doc_ids
    return {"question_id": case.get("question_id"), "permission_ok": permission_ok,
            "doc_recall_hit": doc_recall_hit}


def summarize(results: list[dict]) -> dict:
    """Aggregate case results into totals + regression/recall counts."""
    return {
        "total": len(results),
        "permission_regressions": sum(1 for r in results if not r["permission_ok"]),
        "recall_hits": sum(1 for r in results if r["doc_recall_hit"]),
    }
```

Create `modules/enterprise_knowledge/tools/sync_eval.py` (operational; regenerates the full CSV from the workspace xlsx):

```python
#!/usr/bin/env python
"""Regenerate access/public_evaluation.csv from the workspace dataset xlsx.

Usage: python tools/sync_eval.py "<path to ai_workspace_dataset_...xlsx>"
Reads the Public_Evaluation sheet and writes the columns the eval harness needs.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

_COLS = ["question_id", "user_id", "user_role", "user_department",
         "question_vi", "expected_permission", "expected_document_id"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: sync_eval.py <dataset.xlsx>", file=sys.stderr)
        return 2
    from openpyxl import load_workbook

    ws = load_workbook(argv[1], read_only=True, data_only=True)["Public_Evaluation"]
    rows = [r for r in ws.iter_rows(values_only=True) if r and r[0] == "question_id" or
            (r and str(r[0]).startswith("P"))]
    header = [str(c) for c in rows[0]]
    idx = {name: header.index(name) for name in _COLS if name in header}
    out_path = Path(__file__).resolve().parent.parent / "access" / "public_evaluation.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_COLS)
        for r in rows[1:]:
            writer.writerow([r[idx[name]] if name in idx else "" for name in _COLS])
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_enterprise_knowledge_evaluate.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add modules/enterprise_knowledge/scripts/evaluate.py modules/enterprise_knowledge/tools/sync_eval.py modules/enterprise_knowledge/access/public_evaluation.csv tests/test_enterprise_knowledge_evaluate.py
git commit -m "feat(enterprise_knowledge): offline Public_Evaluation harness (ACL + recall)"
```

---

### Task 14: Dependencies, compose wiring, and SKILL docs

**Files:**
- Modify: `modules/enterprise_knowledge/requirements.txt`
- Modify: `docker-compose.yml` (add `EK_NEO4J_*` to `minder` and `minder-worker`)
- Modify: `modules/enterprise_knowledge/SKILL.md`

**Interfaces:** none (packaging/ops/docs). Verified by the `neo4j` import resolving and health check reaching the compose Neo4j.

- [ ] **Step 1: Add the driver dependency**

Append to `modules/enterprise_knowledge/requirements.txt`:

```
neo4j>=5.24
```

- [ ] **Step 2: Wire compose env passthrough**

In `docker-compose.yml`, under the `minder` service `environment:` block, after the EK block (the `EK_QDRANT_URL` line), add:

```yaml
      # enterprise_knowledge knowledge graph — reuse the shared neo4j service.
      - EK_NEO4J_URI=${EK_NEO4J_URI:-bolt://neo4j:7687}
      - EK_NEO4J_USER=${EK_NEO4J_USER:-neo4j}
      - EK_NEO4J_PASSWORD=${EK_NEO4J_PASSWORD:-minder-neo4j}
      - EK_GRAPH_ENABLED=${EK_GRAPH_ENABLED:-0}
      - EK_GRAPH_EXTRACT=${EK_GRAPH_EXTRACT:-0}
      - EK_GRAPH_HOPS=${EK_GRAPH_HOPS:-1}
      - EK_GRAPH_MAX_NEIGHBORS=${EK_GRAPH_MAX_NEIGHBORS:-20}
      - EK_KG_EXTRACT_BASE_URL=${EK_KG_EXTRACT_BASE_URL:-https://openrouter.ai/api/v1}
      - EK_KG_EXTRACT_MODEL=${EK_KG_EXTRACT_MODEL:-openai/gpt-4o-mini}
```

Add the same block to the `minder-worker` service `environment:` (after its `EK_QDRANT_URL` line). Add `depends_on: neo4j` to both services if not already present (the `neo4j` service already exists in the file).

- [ ] **Step 3: Document in SKILL.md**

Add a short section to `modules/enterprise_knowledge/SKILL.md` (plain prose, no tables):

```markdown
## GraphRAG (optional)

For richer answers, the retrieval can be augmented with a knowledge graph.
Build it once, then pass `--graph` on a query:

- `python <modules>/enterprise_knowledge/scripts/knowledge.py graph build` — build the
  metadata + tag backbone (no LLM). Add `--extract` to also run the LLM
  entity/relation pass (cached; needs EK_KG_EXTRACT_* and is slower on free tiers).
- `python <modules>/enterprise_knowledge/scripts/knowledge.py query "<Q>" --user U004 --graph --synthesize`
  — expand retrieval with the graph. Access control is identical to the vector
  path: every graph-surfaced passage is re-checked with the same permission rules,
  so `--graph` never widens what a user can see. If the graph is unavailable, the
  query silently falls back to vector-only.
```

- [ ] **Step 4: Verify the module still imports and unit tests pass**

Run: `uv run pytest tests/ -k enterprise_knowledge -v`
Expected: PASS (all EK tests, including the new graph suites).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/requirements.txt docker-compose.yml modules/enterprise_knowledge/SKILL.md
git commit -m "feat(enterprise_knowledge): neo4j dep + compose EK_NEO4J_* wiring + SKILL docs"
```

---

### Task 15: Full-suite regression + live smoke (real API + Neo4j)

**Files:** none (verification task per CLAUDE.md testing policy).

- [ ] **Step 1: Run the full EK unit suite**

Run: `uv run pytest tests/ -k enterprise_knowledge -v`
Expected: PASS.

- [ ] **Step 2: Bring up the graph-relevant services**

Run: `docker compose up -d neo4j qdrant`
Expected: both healthy (`docker compose ps`).

- [ ] **Step 3: Live smoke — build backbone + graph query (real key + Neo4j)**

With `OPENAI_API_KEY`/`OPENROUTER_API_KEY` and `EK_*` set (per `.env`), from `modules/enterprise_knowledge/scripts/`:

```bash
export EK_NEO4J_URI=bolt://localhost:7687
python knowledge.py ingest
python knowledge.py graph build            # backbone only (deterministic)
python knowledge.py graph stats            # expect nodes>0, edges>0
python knowledge.py query "chính sách nghỉ phép" --user U001 --graph --synthesize
python knowledge.py health                 # expect index_embed/synthesis/qdrant/neo4j = ok
```
Expected: `graph stats` shows nodes/edges; the `--graph` query returns a cited Vietnamese answer; `health` reports `neo4j: ok`. Confirm a non-executive query never cites an out-of-scope document.

- [ ] **Step 4: Commit (nothing to commit — verification only)**

If any check fails, open a fix task; do not mark the plan complete.

---

## Self-review — spec coverage

- Neo4j store, best quality → Tasks 3/5/8 (`EKGraphStore`), Task 14 (compose). ✅
- Hybrid metadata + optional LLM → Task 6 (`build_backbone` + `build_extraction`), Task 7 (`--extract`). ✅
- Tags as free entity seeds → Task 2 (parse), Task 3 (`TAGGED`), Task 8 (`neighbors_via_tags`), Task 13 (`sync_eval` sibling `sync_tags` pattern noted). ✅ (A dedicated `sync_tags.py` tool mirrors `sync_eval.py`; backbone degrades gracefully when tags absent — Task 3 iterates `doc.get("tags", []) or []`.)
- Extraction caching / free-tier safety → Task 6 (`ExtractionCache`). ✅
- Approach A (entity-seeded ACL-filtered expansion into synthesis) → Tasks 8/9/10. ✅
- Approach B (connectivity boost) → Task 9 (`merge_hits` boost). ✅
- Three ACL gates: vector pre-filter (existing) + per-hop Cypher filter (Task 8) + citation-time re-check (Task 9 `expand` + Task 10 `guard_accessible`) → ✅; adversarial guard Task 11. ✅
- `:EKNode` namespace isolation → Task 3. ✅
- Graceful vector-only fallback → Task 10 (`_augment_with_graph` try/except), Task 12 (health). ✅
- Eval harness + definition of done → Task 13; live smoke Task 15. ✅
- Config/env switches (`EK_GRAPH_ENABLED`, `EK_GRAPH_EXTRACT`, `EK_GRAPH_HOPS`, `EK_GRAPH_MAX_NEIGHBORS`, `EK_KG_EXTRACT_*`, `EK_NEO4J_*`) → Task 1 (`kg_extract`), Task 10 (hops/max), Task 14 (compose). ✅
- Community-edition single-DB caveat (MC's global `reset` can wipe EK) → documented risk in spec §11; EK's own reset is namespaced (Task 3). Noted for operators.

## Self-review — notes

- `EK_GRAPH_ENABLED` is the compose-level master switch; the CLI `--graph` flag is the per-query trigger. The dashboard toggle from the spec is intentionally **not** in this plan (marked defer-able); add later if wanted.
- Type consistency check: candidate chunk dicts share the key set `{chunk_id, doc_id, text, title, department, classification, knowledge_space, citation}` across `neighbors_*` (Task 8), `expand`/`merge_hits` (Task 9), and the leakage fixture (Task 11). Vector hits additionally carry `score`; `merge_hits` assigns a below-floor `score` to graph-only hits. Consistent. ✅
