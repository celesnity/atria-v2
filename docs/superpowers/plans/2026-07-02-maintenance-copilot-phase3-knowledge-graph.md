# Maintenance Copilot — Phase 3: Knowledge Graph — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract aviation entities/relationships from manual chunks with the local `kg_extract` LLM, store them in Neo4j with provenance + confidence + verification status, and expose them via a `graph` CLI plus optional multi-hop context in `query`.

**Architecture:** Three new modules under `modules/maintenance_copilot/scripts/` — `extraction.py` (LLM → strict-JSON → validated `GraphExtraction` with provenance), `graph_store.py` (a `GraphStore` over an injectable `run_fn(cypher, params)`; production wraps a Neo4j session, tests inject a fake), and additions to `copilot.py` (`graph build|show|confirm|stats|reset` and a `--graph` option on `query`). Every LLM-extracted node/edge is written `status="unverified"` with `confidence` and provenance, and is never presented as fact until an engineer confirms it.

**Tech Stack:** the Phase 1 `RoleClient` (`kg_extract` role) + `config`; Phase 2 `corpus`/`chunking`; `neo4j` Python driver (lazy-imported; unit tests inject a fake `run_fn` and never touch a server).

**Spec:** `docs/superpowers/specs/2026-07-02-maintenance-copilot-design.md` (§4.2 graph extract, §4.2 schema, §5 `graph`)
**Builds on:** Phases 1–2 (config, client, corpus, chunking, index_store, CLI) — all committed on `design/maintenance-copilot`.

## Global Constraints

- Line length ≤ 100 (verify with `uvx ruff check ...` AND `awk 'length>100{print FILENAME":"NR}'` — Ruff's default select does not flag E501 in this repo). Type hints on public functions; Google-style docstrings; use builtin generics (`list`/`dict`/`X | None`), not `typing.List/Dict/Optional`.
- Tests run with `uv run pytest`. Module tests live at `tests/test_maintenance_copilot_*.py`, load module files via `importlib`, and register each loaded module in `sys.modules` under a unique sentinel name immediately after `module_from_spec`.
- Module scripts add `sys.path.insert(0, str(Path(__file__).resolve().parent))` before sibling imports.
- Module-local only — no imports from `atria/`.
- Unit tests must NOT hit the network or a database: inject a fake `run_fn` for the graph store and a fake `chat_fn` for extraction. Do NOT require a live Neo4j.
- Every extracted node and edge carries `source_doc`, `revision`, `page` (chunk_id), `extracted_by` (model id), `confidence` (0–1), and `status` (`"unverified"` until confirmed). This is non-negotiable — it is what makes an LLM-built graph auditable.
- Retrieval/graph output is advisory; the `query`/`graph show` output must never present an `unverified` edge as established fact (flag it).
- Commits must NOT include a `Co-Authored-By: Claude` trailer.
- Branch: `design/maintenance-copilot` (already checked out). Do not create branches.

---

### Task 1: Graph extraction (LLM → validated GraphExtraction)

**Files:**
- Create: `modules/maintenance_copilot/scripts/extraction.py`
- Test: `tests/test_maintenance_copilot_extraction.py`

**Interfaces:**
- Consumes: nothing from earlier phases at runtime (operates on plain text + an injected `chat_fn`).
- Produces:
  - `ALLOWED_ENTITY_TYPES: frozenset[str]` = `{"ATAChapter","Part","MELItem","CDLItem","FaultCode","Procedure","Defect","Document"}`
  - `ALLOWED_EDGE_TYPES: frozenset[str]` = `{"IN_CHAPTER","RELIEVES","REQUIRES","SIMILAR_TO","TROUBLESHOT_BY","MENTIONS"}`
  - `@dataclass(frozen=True) Entity` — `type: str`, `key: str`, `props: dict`
  - `@dataclass(frozen=True) Edge` — `type: str`, `src_key: str`, `dst_key: str`, `props: dict`
  - `@dataclass(frozen=True) GraphExtraction` — `entities: list[Entity]`, `edges: list[Edge]`
  - `build_extraction_messages(chunk_text: str) -> list[dict]` — system+user messages instructing strict-JSON output.
  - `parse_extraction(raw: str, provenance: dict) -> GraphExtraction` — strips ```` ```json ```` fences, `json.loads`, drops items whose `type` is not allowed, and stamps every entity's and edge's `props` with `provenance` keys plus `status="unverified"` and a `confidence` (item-supplied `confidence` if a 0–1 float, else `0.5`). Raises `ValueError` on non-JSON or when the top-level shape is not `{"entities":[...],"relationships":[...]}`.
  - `extract_graph(chunk_text: str, chat_fn, provenance: dict) -> GraphExtraction` — `chat_fn(messages) -> str`; calls it with `build_extraction_messages` and parses.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_copilot_extraction.py
"""Tests for LLM graph extraction → validated GraphExtraction with provenance."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


_PROV = {"source_doc": "mel_ata32.md", "revision": "Rev-18", "page": "mel_ata32#0",
         "extracted_by": "Qwen2.5-1.5B"}

_GOOD = """```json
{"entities": [
   {"type": "MELItem", "key": "32-30-01", "props": {"category": "C"}},
   {"type": "ATAChapter", "key": "32", "props": {}},
   {"type": "Alien", "key": "x", "props": {}}],
 "relationships": [
   {"type": "IN_CHAPTER", "src": "32-30-01", "dst": "32", "props": {}, "confidence": 0.9},
   {"type": "BOGUS", "src": "a", "dst": "b", "props": {}}]}
```"""


def test_parse_extraction_validates_types_and_stamps_provenance():
    ex = _load("extraction", "mc_extraction_uut")
    out = ex.parse_extraction(_GOOD, _PROV)
    # Unknown 'Alien' entity and 'BOGUS' edge dropped.
    assert [e.type for e in out.entities] == ["MELItem", "ATAChapter"]
    assert [e.type for e in out.edges] == ["IN_CHAPTER"]
    mel = out.entities[0]
    assert mel.props["source_doc"] == "mel_ata32.md"
    assert mel.props["revision"] == "Rev-18"
    assert mel.props["status"] == "unverified"
    assert mel.props["confidence"] == 0.5           # entity had no confidence → default
    assert out.edges[0].props["confidence"] == 0.9  # edge-supplied confidence preserved
    assert out.edges[0].props["status"] == "unverified"


def test_parse_extraction_raises_on_non_json():
    ex = _load("extraction", "mc_extraction_uut2")
    with pytest.raises(ValueError):
        ex.parse_extraction("the model refused to answer", _PROV)


def test_extract_graph_calls_chat_fn_with_messages():
    ex = _load("extraction", "mc_extraction_uut3")
    seen = {}

    def fake_chat(messages):
        seen["messages"] = messages
        return _GOOD

    out = ex.extract_graph("MEL 32-30-01 ...", fake_chat, _PROV)
    assert seen["messages"][-1]["role"] == "user"
    assert "MEL 32-30-01" in seen["messages"][-1]["content"]
    assert len(out.entities) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_extraction.py -v`
Expected: FAIL — `extraction.py` does not exist.

- [ ] **Step 3: Write `extraction.py`**

```python
# modules/maintenance_copilot/scripts/extraction.py
"""Extract aviation entities/relationships from a chunk via the kg_extract LLM.

The LLM is asked for strict JSON. Output is validated against a fixed set of
entity/edge types (unknown types are dropped, not trusted), and every surviving
node and edge is stamped with provenance, a confidence score, and
``status="unverified"`` — so an LLM-built graph stays auditable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

ALLOWED_ENTITY_TYPES = frozenset(
    {"ATAChapter", "Part", "MELItem", "CDLItem", "FaultCode", "Procedure", "Defect", "Document"}
)
ALLOWED_EDGE_TYPES = frozenset(
    {"IN_CHAPTER", "RELIEVES", "REQUIRES", "SIMILAR_TO", "TROUBLESHOT_BY", "MENTIONS"}
)

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
        "You extract a knowledge graph from aircraft maintenance text. "
        "Return ONLY JSON, no prose. Shape: "
        '{"entities":[{"type":<T>,"key":<str>,"props":{}}],'
        '"relationships":[{"type":<R>,"src":<key>,"dst":<key>,"props":{},"confidence":<0-1>}]}. '
        f"Entity types: {sorted(ALLOWED_ENTITY_TYPES)}. "
        f"Relationship types: {sorted(ALLOWED_EDGE_TYPES)}. "
        "Use identifiers as keys (ATA chapter number, MEL/CDL item id, part number, "
        "fault code, AMM task id). Omit anything you are unsure of."
    )
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
        provenance: Keys stamped onto every node/edge (source_doc, revision,
            page, extracted_by).

    Returns:
        Validated entities/edges; unknown types are dropped.

    Raises:
        ValueError: If ``raw`` is not JSON or lacks the expected top-level shape.
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
        entities.append(
            Entity(type=item["type"], key=str(item["key"]),
                   props=_stamp(item.get("props"), provenance, item))
        )

    edges: list[Edge] = []
    for item in data["relationships"]:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_EDGE_TYPES:
            continue
        if not item.get("src") or not item.get("dst"):
            continue
        edges.append(
            Edge(type=item["type"], src_key=str(item["src"]), dst_key=str(item["dst"]),
                 props=_stamp(item.get("props"), provenance, item))
        )
    return GraphExtraction(entities=entities, edges=edges)


def extract_graph(chunk_text: str, chat_fn: Callable[[list], str], provenance: dict) -> GraphExtraction:
    """Run the kg_extract LLM over ``chunk_text`` and parse its output.

    Args:
        chunk_text: The chunk to extract from.
        chat_fn: Callable taking chat messages and returning the raw string reply.
        provenance: Keys stamped onto every node/edge.

    Returns:
        The validated extraction.
    """
    raw = chat_fn(build_extraction_messages(chunk_text))
    return parse_extraction(raw, provenance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_extraction.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/maintenance_copilot/scripts/extraction.py \
        tests/test_maintenance_copilot_extraction.py
git commit -m "feat(maintenance_copilot): LLM graph extraction with provenance + validation"
```

---

### Task 2: Neo4j graph store (injectable run_fn)

**Files:**
- Create: `modules/maintenance_copilot/scripts/graph_store.py`
- Modify: `modules/maintenance_copilot/requirements.txt` (add `neo4j`)
- Test: `tests/test_maintenance_copilot_graph_store.py`

**Interfaces:**
- Consumes: `extraction.GraphExtraction`, `Entity`, `Edge` (Task 1).
- Produces:
  - `RunFn = Callable[[str, dict], list[dict]]` — executes a Cypher statement with params, returns records as dicts.
  - `class GraphStore(run_fn: RunFn)`.
  - `GraphStore.ensure_constraints() -> None` — one `CREATE CONSTRAINT ... IF NOT EXISTS` per allowed entity label requiring a unique `key`.
  - `GraphStore.upsert_extraction(ext: GraphExtraction) -> tuple[int, int]` — `MERGE` each node (label = entity type, key = `key`, `SET n += $props`) and each edge (`MERGE (a)-[r:TYPE]->(b) SET r += $props`, matching endpoints by `key`). Returns `(nodes, edges)`.
  - `GraphStore.neighbors(entity_key: str, hops: int = 1) -> list[dict]` — variable-length `MATCH` from the node with `key=$key`; returns rows `{"neighbor_key","neighbor_labels","edge_type","status","confidence"}`.
  - `GraphStore.confirm_edge(src_key: str, edge_type: str, dst_key: str) -> int` — `SET r.status='engineer_confirmed'`; returns the number updated.
  - `GraphStore.stats() -> dict` — `{"nodes": n, "edges": m, "unverified_edges": u}`.
  - `GraphStore.reset() -> None` — `MATCH (n) DETACH DELETE n`.
  - `neo4j_run_fn(driver) -> RunFn` — wraps a Neo4j driver: opens a session per call, runs the statement, returns `[record.data() for record in result]`. (Lazy — only used by the CLI in Task 3.)

- [ ] **Step 1: Add the dependency**

Append to `modules/maintenance_copilot/requirements.txt`:

```text
neo4j>=5.24
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_maintenance_copilot_graph_store.py
"""Tests for the Neo4j graph store using a fake in-memory run_fn (no server)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeRunner:
    """Captures every (cypher, params) call; returns canned rows when configured."""

    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    def __call__(self, cypher, params):
        self.calls.append((cypher, params))
        return self._rows


def _extraction(extraction_mod):
    prov = {"source_doc": "mel_ata32.md", "revision": "Rev-18",
            "page": "mel_ata32#0", "extracted_by": "m"}
    ent = extraction_mod.Entity("MELItem", "32-30-01",
                                {**prov, "status": "unverified", "confidence": 0.9})
    ata = extraction_mod.Entity("ATAChapter", "32",
                                {**prov, "status": "unverified", "confidence": 0.9})
    edge = extraction_mod.Edge("IN_CHAPTER", "32-30-01", "32",
                               {**prov, "status": "unverified", "confidence": 0.9})
    return extraction_mod.GraphExtraction([ent, ata], [edge])


def test_upsert_merges_nodes_and_edges_with_props():
    extraction = _load("extraction", "mc_extraction_for_graph")
    graph_store = _load("graph_store", "mc_graph_store_uut")
    runner = _FakeRunner()
    store = graph_store.GraphStore(runner)
    nodes, edges = store.upsert_extraction(_extraction(extraction))
    assert (nodes, edges) == (2, 1)
    # Every node MERGE carries a $props dict with status + confidence.
    merges = [c for c in runner.calls if "MERGE" in c[0]]
    assert any(c[1].get("props", {}).get("status") == "unverified" for c in merges)
    # The edge MERGE references the MELItem/ATAChapter keys.
    edge_calls = [c for c in runner.calls if "IN_CHAPTER" in c[0]]
    assert edge_calls and edge_calls[0][1]["src_key"] == "32-30-01"
    assert edge_calls[0][1]["dst_key"] == "32"


def test_neighbors_returns_rows_from_runner():
    _load("extraction", "mc_extraction_for_graph2")
    graph_store = _load("graph_store", "mc_graph_store_uut2")
    rows = [{"neighbor_key": "32", "neighbor_labels": ["ATAChapter"],
             "edge_type": "IN_CHAPTER", "status": "unverified", "confidence": 0.9}]
    runner = _FakeRunner(rows=rows)
    store = graph_store.GraphStore(runner)
    out = store.neighbors("32-30-01", hops=1)
    assert out == rows
    assert "MATCH" in runner.calls[0][0]
    assert runner.calls[0][1]["key"] == "32-30-01"


def test_confirm_edge_sets_status_and_counts():
    _load("extraction", "mc_extraction_for_graph3")
    graph_store = _load("graph_store", "mc_graph_store_uut3")
    runner = _FakeRunner(rows=[{"updated": 1}])
    store = graph_store.GraphStore(runner)
    n = store.confirm_edge("32-30-01", "IN_CHAPTER", "32")
    assert n == 1
    assert "engineer_confirmed" in runner.calls[0][0]
    assert runner.calls[0][1] == {"src_key": "32-30-01", "dst_key": "32"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_graph_store.py -v`
Expected: FAIL — `graph_store.py` does not exist.

- [ ] **Step 4: Write `graph_store.py`**

```python
# modules/maintenance_copilot/scripts/graph_store.py
"""Neo4j-backed knowledge graph store.

All database access goes through an injected ``run_fn(cypher, params) -> rows``,
so unit tests can supply a fake and never touch a server. The production
``run_fn`` (``neo4j_run_fn``) opens a session per call against a Neo4j driver.

Node labels are the entity type; nodes and edges are matched/merged by ``key``.
Every write carries the extraction's stamped props (provenance, confidence,
status), so an LLM-built edge stays ``unverified`` until an engineer confirms it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extraction import ALLOWED_ENTITY_TYPES, GraphExtraction  # type: ignore[import-not-found]

RunFn = Callable[[str, dict], list]


class GraphStore:
    """Create constraints, upsert extractions, and query the graph."""

    def __init__(self, run_fn: RunFn):
        self._run = run_fn

    def ensure_constraints(self) -> None:
        """One uniqueness constraint on ``key`` per allowed entity label."""
        for label in sorted(ALLOWED_ENTITY_TYPES):
            self._run(
                f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.key IS UNIQUE",
                {},
            )

    def upsert_extraction(self, ext: GraphExtraction) -> tuple[int, int]:
        """MERGE every node and edge; return (node_count, edge_count)."""
        for ent in ext.entities:
            self._run(
                f"MERGE (n:{ent.type} {{key: $key}}) SET n += $props",
                {"key": ent.key, "props": ent.props},
            )
        for edge in ext.edges:
            self._run(
                "MATCH (a {key: $src_key}), (b {key: $dst_key}) "
                f"MERGE (a)-[r:{edge.type}]->(b) SET r += $props",
                {"src_key": edge.src_key, "dst_key": edge.dst_key, "props": edge.props},
            )
        return len(ext.entities), len(ext.edges)

    def neighbors(self, entity_key: str, hops: int = 1) -> list:
        """Return entities reachable from ``entity_key`` within ``hops`` hops."""
        depth = max(1, int(hops))
        cypher = (
            f"MATCH (a {{key: $key}})-[r*1..{depth}]-(b) "
            "RETURN DISTINCT b.key AS neighbor_key, labels(b) AS neighbor_labels, "
            "type(last(r)) AS edge_type, last(r).status AS status, "
            "last(r).confidence AS confidence"
        )
        return self._run(cypher, {"key": entity_key})

    def confirm_edge(self, src_key: str, edge_type: str, dst_key: str) -> int:
        """Flip an edge's status to engineer_confirmed; return rows updated."""
        cypher = (
            "MATCH (a {key: $src_key})-[r:" + edge_type + "]->(b {key: $dst_key}) "
            "SET r.status = 'engineer_confirmed' RETURN count(r) AS updated"
        )
        rows = self._run(cypher, {"src_key": src_key, "dst_key": dst_key})
        return int(rows[0]["updated"]) if rows else 0

    def stats(self) -> dict:
        """Return node/edge counts and the number of unverified edges."""
        rows = self._run(
            "MATCH (n) WITH count(n) AS nodes "
            "MATCH ()-[r]->() "
            "RETURN nodes, count(r) AS edges, "
            "sum(CASE WHEN r.status='unverified' THEN 1 ELSE 0 END) AS unverified_edges",
            {},
        )
        if not rows:
            return {"nodes": 0, "edges": 0, "unverified_edges": 0}
        row = rows[0]
        return {
            "nodes": row.get("nodes", 0),
            "edges": row.get("edges", 0),
            "unverified_edges": row.get("unverified_edges", 0),
        }

    def reset(self) -> None:
        """Delete all nodes and relationships."""
        self._run("MATCH (n) DETACH DELETE n", {})


def neo4j_run_fn(driver) -> RunFn:
    """Build a run_fn that executes each statement in its own Neo4j session."""

    def _run(cypher: str, params: dict) -> list:
        with driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    return _run
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_graph_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Add `neo4j` to core deps (per project dependency policy) and commit**

```bash
uv add neo4j
git add modules/maintenance_copilot/scripts/graph_store.py \
        modules/maintenance_copilot/requirements.txt \
        tests/test_maintenance_copilot_graph_store.py pyproject.toml uv.lock
git commit -m "feat(maintenance_copilot): Neo4j graph store with provenance + confirm"
```

---

### Task 3: `graph` CLI — build / show / confirm / stats / reset

**Files:**
- Modify: `modules/maintenance_copilot/scripts/copilot.py`
- Test: `tests/test_maintenance_copilot_graph_cli.py`

**Interfaces:**
- Consumes: `corpus.load_corpus`, `chunking.chunk_document`, `extraction.extract_graph`, `graph_store.GraphStore`/`neo4j_run_fn`, `client.RoleClient`, `config.load_config`.
- Produces (additions to `copilot.py`):
  - `_build_graph_store(run_fn=None) -> GraphStore` — builds from `MC_NEO4J_URI`/`MC_NEO4J_USER`/`MC_NEO4J_PASSWORD` via `neo4j_run_fn`, or an injected `run_fn` (tests). Calls `ensure_constraints()`.
  - `_kg_chat_fn()` — returns `lambda messages: RoleClient(load_config()).chat("kg_extract", messages)`.
  - Handlers returning 0 on success, printing JSON:
    - `graph build [--samples DIR]` — for each chunk of each doc, `extract_graph(chunk.text, chat_fn, provenance)` then `upsert_extraction`; provenance = `{source_doc, revision, page=chunk_id, extracted_by=<kg_extract model>}`. Prints `{"chunks","nodes","edges"}`.
    - `graph show <key> [--hops 1]` — prints `{"key","neighbors":[...],"unverified": <count>}`; each neighbor row includes its `status` so `unverified` links are visibly flagged.
    - `graph confirm <src> <edge_type> <dst>` — prints `{"confirmed": N}`.
    - `graph stats` — prints `GraphStore.stats()`.
    - `graph reset` — prints `{"reset": true}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_copilot_graph_cli.py
"""Tests for the `graph` CLI subcommands (fake graph store + fake extractor)."""

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
    spec = importlib.util.spec_from_file_location("mc_graph_cli_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_graph_cli_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_EXTRACT_JSON = """{"entities":[{"type":"ATAChapter","key":"32","props":{}}],
"relationships":[]}"""


@pytest.fixture()
def cli(monkeypatch):
    mod = _load_cli()

    calls = {"upserts": 0}

    class _FakeStore:
        def ensure_constraints(self):
            pass

        def upsert_extraction(self, ext):
            calls["upserts"] += 1
            return len(ext.entities), len(ext.edges)

        def neighbors(self, key, hops=1):
            return [{"neighbor_key": "32-30-01", "neighbor_labels": ["MELItem"],
                     "edge_type": "IN_CHAPTER", "status": "unverified", "confidence": 0.9}]

        def confirm_edge(self, s, t, d):
            return 1

        def stats(self):
            return {"nodes": 1, "edges": 0, "unverified_edges": 0}

        def reset(self):
            pass

    monkeypatch.setattr(mod, "_build_graph_store", lambda run_fn=None: _FakeStore())
    monkeypatch.setattr(mod, "_kg_chat_fn", lambda: (lambda messages: _EXTRACT_JSON))
    return mod, calls


def test_graph_build_extracts_and_upserts(cli, capsys):
    mod, calls = cli
    rc = mod.main(["graph", "build"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["chunks"] >= 4          # one per sample-manual chunk
    assert out["nodes"] >= 1
    assert calls["upserts"] >= 4


def test_graph_show_flags_unverified(cli, capsys):
    mod, _ = cli
    rc = mod.main(["graph", "show", "32", "--hops", "1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["key"] == "32"
    assert out["neighbors"][0]["status"] == "unverified"
    assert out["unverified"] == 1


def test_graph_confirm_and_stats(cli, capsys):
    mod, _ = cli
    assert mod.main(["graph", "confirm", "32-30-01", "IN_CHAPTER", "32"]) == 0
    assert json.loads(capsys.readouterr().out)["confirmed"] == 1
    assert mod.main(["graph", "stats"]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_graph_cli.py -v`
Expected: FAIL — no `graph` subcommand / `_build_graph_store` symbol.

- [ ] **Step 3: Extend `copilot.py`**

Add sibling imports (after the Phase-2 imports):

```python
from extraction import extract_graph  # type: ignore[import-not-found]
from graph_store import GraphStore, neo4j_run_fn  # type: ignore[import-not-found]
```

Add builders:

```python
def _kg_chat_fn():
    """Return a chat callable bound to the kg_extract role."""
    rc = RoleClient(load_config())
    return lambda messages: rc.chat("kg_extract", messages)


def _build_graph_store(run_fn=None) -> GraphStore:
    """Build a GraphStore from MC_NEO4J_* env (or an injected run_fn) + constraints."""
    if run_fn is None:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            _env("MC_NEO4J_URI", "bolt://localhost:7687"),
            auth=(_env("MC_NEO4J_USER", "neo4j"), _env("MC_NEO4J_PASSWORD", "atria-neo4j")),
        )
        run_fn = neo4j_run_fn(driver)
    store = GraphStore(run_fn)
    store.ensure_constraints()
    return store
```

Add handlers:

```python
def _cmd_graph_build(samples: str) -> int:
    store = _build_graph_store()
    chat_fn = _kg_chat_fn()
    docs = load_corpus(samples)
    chunks = nodes = edges = 0
    for doc in docs:
        for rec in chunk_document(doc):
            chunks += 1
            prov = {"source_doc": Path(rec.source_path).name, "revision": rec.revision,
                    "page": rec.chunk_id, "extracted_by": load_config()["kg_extract"].model}
            ext = extract_graph(rec.text, chat_fn, prov)
            n, e = store.upsert_extraction(ext)
            nodes += n
            edges += e
    print(json.dumps({"chunks": chunks, "nodes": nodes, "edges": edges}, indent=2))
    return 0


def _cmd_graph_show(key: str, hops: int) -> int:
    store = _build_graph_store()
    rows = store.neighbors(key, hops=hops)
    unverified = sum(1 for r in rows if r.get("status") == "unverified")
    print(json.dumps({"key": key, "neighbors": rows, "unverified": unverified}, indent=2))
    return 0


def _cmd_graph_confirm(src: str, edge_type: str, dst: str) -> int:
    store = _build_graph_store()
    print(json.dumps({"confirmed": store.confirm_edge(src, edge_type, dst)}, indent=2))
    return 0


def _cmd_graph_stats() -> int:
    print(json.dumps(_build_graph_store().stats(), indent=2))
    return 0


def _cmd_graph_reset() -> int:
    _build_graph_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0
```

Extend `build_parser()` — add a `graph` subcommand with its own sub-subcommands:

```python
    p_graph = sub.add_parser("graph", help="Knowledge-graph build/query/verify.")
    graph_sub = p_graph.add_subparsers(dest="graph_command", required=True)
    g_build = graph_sub.add_parser("build", help="Extract + upsert the graph from the corpus.")
    g_build.add_argument("--samples", default=None)
    g_show = graph_sub.add_parser("show", help="Show neighbors of an entity.")
    g_show.add_argument("key")
    g_show.add_argument("--hops", type=int, default=1)
    g_confirm = graph_sub.add_parser("confirm", help="Mark an edge engineer_confirmed.")
    g_confirm.add_argument("src")
    g_confirm.add_argument("edge_type")
    g_confirm.add_argument("dst")
    graph_sub.add_parser("stats", help="Graph node/edge counts.")
    graph_sub.add_parser("reset", help="Delete all graph data.")
```

Extend `main()` dispatch:

```python
    if args.command == "graph":
        if args.graph_command == "build":
            return _cmd_graph_build(
                args.samples if getattr(args, "samples", None) else _samples_dir()
            )
        if args.graph_command == "show":
            return _cmd_graph_show(args.key, args.hops)
        if args.graph_command == "confirm":
            return _cmd_graph_confirm(args.src, args.edge_type, args.dst)
        if args.graph_command == "stats":
            return _cmd_graph_stats()
        if args.graph_command == "reset":
            return _cmd_graph_reset()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_graph_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Full suite + lint**

Run: `uv run pytest tests/test_maintenance_copilot_*.py -v` → all pass.
Run: `uvx ruff check modules/maintenance_copilot tests/test_maintenance_copilot_*.py` → clean.
Run: `awk 'length>100{print FILENAME":"NR": "length}' modules/maintenance_copilot/scripts/*.py` → no output.

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/scripts/copilot.py \
        tests/test_maintenance_copilot_graph_cli.py
git commit -m "feat(maintenance_copilot): graph build/show/confirm/stats/reset CLI"
```

---

### Task 4: Multi-hop graph context in `query`

**Files:**
- Modify: `modules/maintenance_copilot/scripts/copilot.py` (`_cmd_query` + `query` subparser)
- Test: `tests/test_maintenance_copilot_query_graph.py`

**Interfaces:**
- Consumes: `_build_graph_store` (Task 3), the existing `_cmd_query` (Phase 2).
- Produces:
  - `query` gains `--graph` (store_true). When set, after retrieval the command looks up graph neighbors for the top hit's `ata_chapter` and adds `"graph_context"` to the JSON: `{"ata_chapter": <c>, "related": [neighbor rows]}`. When `--graph` is absent, output is unchanged from Phase 2 (no Neo4j needed).
  - `_cmd_query(text, k, ata, revision, with_graph=False)` — new trailing param, default `False` keeps the Phase-2 signature behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_copilot_query_graph.py
"""Tests for --graph multi-hop context attached to query results."""

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
    spec = importlib.util.spec_from_file_location("mc_query_graph_uut", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mc_query_graph_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def _embed_fn(texts):
    return [[1.0 if "gear" in t.lower() else 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture()
def cli(monkeypatch):
    mod = _load_cli()
    from qdrant_client import QdrantClient
    shared = QdrantClient(":memory:")

    def fake_store(embed_fn=None, qdrant=None):
        s = mod.IndexStore(shared, _embed_fn)
        s.ensure_collection(dim=3)
        return s

    class _FakeGraph:
        def neighbors(self, key, hops=1):
            return [{"neighbor_key": "32-30-01", "neighbor_labels": ["MELItem"],
                     "edge_type": "IN_CHAPTER", "status": "unverified", "confidence": 0.9}]

    monkeypatch.setattr(mod, "_build_store", fake_store)
    monkeypatch.setattr(mod, "_build_graph_store", lambda run_fn=None: _FakeGraph())
    return mod


def test_query_without_graph_flag_has_no_graph_context(cli, capsys):
    cli.main(["ingest"])
    capsys.readouterr()
    cli.main(["query", "gear", "--revision", "none"])
    out = json.loads(capsys.readouterr().out)
    assert "graph_context" not in out


def test_query_with_graph_flag_attaches_related(cli, capsys):
    cli.main(["ingest"])
    capsys.readouterr()
    cli.main(["query", "gear removal", "--ata", "32", "--revision", "none", "--graph"])
    out = json.loads(capsys.readouterr().out)
    assert out["graph_context"]["ata_chapter"] == "32"
    assert out["graph_context"]["related"][0]["neighbor_key"] == "32-30-01"
    assert out["graph_context"]["related"][0]["status"] == "unverified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_maintenance_copilot_query_graph.py -v`
Expected: FAIL — `query` has no `--graph` flag / `_cmd_query` has no `with_graph`.

- [ ] **Step 3: Extend `_cmd_query` and the `query` subparser**

Replace the Phase-2 `_cmd_query` with this signature + body (keeps all prior behavior when `with_graph=False`):

```python
def _cmd_query(text: str, k: int, ata: Optional[str], revision: str,
               with_graph: bool = False) -> int:
    rev: Optional[str] = None if revision.lower() == "none" else revision
    store = _build_store()
    hits = store.query(text, k=k, ata_chapter=ata, revision=rev)
    payload = {"query": text, "hits": hits}
    if with_graph and hits:
        chapter = ata or hits[0].get("ata_chapter")
        related = _build_graph_store().neighbors(chapter, hops=1) if chapter else []
        payload["graph_context"] = {"ata_chapter": chapter, "related": related}
    print(json.dumps(payload, indent=2))
    return 0
```

Add the flag to the `query` subparser (next to `--revision`):

```python
    p_query.add_argument("--graph", action="store_true",
                         help="Attach related knowledge-graph entities (needs Neo4j).")
```

Update the `query` dispatch branch in `main()`:

```python
    if args.command == "query":
        return _cmd_query(args.text, args.k, args.ata, args.revision, args.graph)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_maintenance_copilot_query_graph.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full suite + lint**

Run: `uv run pytest tests/test_maintenance_copilot_*.py -v` → all pass.
Run: `uvx ruff check modules/maintenance_copilot tests/test_maintenance_copilot_*.py` → clean.
Run: `awk 'length>100{print FILENAME":"NR": "length}' modules/maintenance_copilot/scripts/*.py` → no output.

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/scripts/copilot.py \
        tests/test_maintenance_copilot_query_graph.py
git commit -m "feat(maintenance_copilot): optional multi-hop graph context in query"
```

- [ ] **Step 7: Real end-to-end (deferred — needs live Neo4j + TEI + Qdrant + LLM)**

Record for a Docker host (not run in CI/sandbox):

```bash
docker compose -f docker-compose.dev.yml up -d tei qdrant neo4j
# (LLM: add --profile gpu + copilot-llm, or set MC_KG_EXTRACT_BASE_URL to a reachable endpoint)
docker compose -f docker-compose.dev.yml exec atria \
    python /app/modules/maintenance_copilot/scripts/copilot.py graph build
docker compose -f docker-compose.dev.yml exec atria \
    python /app/modules/maintenance_copilot/scripts/copilot.py graph show 32 --hops 2
docker compose -f docker-compose.dev.yml exec atria \
    python /app/modules/maintenance_copilot/scripts/copilot.py query "gear fails to retract" --ata 32 --graph
```

Expected: `graph build` reports chunks/nodes/edges > 0; `graph show 32` returns related MEL/procedure entities with `status:"unverified"`; `query --graph` attaches `graph_context`. Extraction quality depends on the LLM; all edges start `unverified`.

---

## Phase 3 self-review

- **Spec coverage (Phase 3 slice):** LLM `kg_extract` → strict-JSON entities/edges (spec §4 step 4) → Task 1; Neo4j schema + provenance/confidence/`status` (spec §4.2) → Tasks 1–2; `graph` command + engineer confirmation of edges → Task 3; multi-hop context in `query` (spec §5, §4.2) → Task 4. Not in this phase: the `validate`/`recommend-refs`/`check` commands, LLM answer synthesis, and the audit trail — those are Phase 4.
- **Placeholder scan:** none — every step ships runnable code or an exact command.
- **Type consistency:** `Entity`/`Edge`/`GraphExtraction` (Task 1) are consumed by `GraphStore.upsert_extraction` (Task 2) and `extract_graph` (Task 3 CLI); `GraphStore` method names (`ensure_constraints`/`upsert_extraction`/`neighbors`/`confirm_edge`/`stats`/`reset`) match between definition (Task 2), CLI use (Task 3), and the fake in tests; `_build_graph_store`/`_kg_chat_fn` names match between `copilot.py` and both CLI tests; `_cmd_query`'s new `with_graph` param is additive and defaults to the Phase-2 behavior.
- **Testing strategy note (for the reviewer):** the graph store is unit-tested with a fake `run_fn` that captures Cypher + params and returns canned rows — this verifies our statement-building and provenance/status handling, not Cypher execution semantics. Real Cypher is exercised only in the deferred Task 4 Step 7 e2e (needs a live Neo4j). This mirrors Phase 1's deferred `health` and Phase 2's deferred ingest e2e.
- **Known assumptions:** `neighbors` compares/ō returns `last(r)` status/type for the path's final edge only (adequate for 1-hop; for multi-hop `show` it summarizes the terminal edge). Revision "latest" logic is not re-implemented here — the graph keys nodes by identifier, so re-extraction MERGEs onto the same node and newer props overwrite older (last-writer-wins); if two revisions disagree on a prop, the most recently ingested wins. Noted for Phase 4 hardening.

## Roadmap — remaining phase (its own plan)

- **Phase 4 — Validation, guardrails & synthesis:** `validate`, `recommend-refs`, `check`; LLM answer synthesis grounded in retrieved chunks + graph; citation post-validation, confidence thresholds, advisory-only framing, `data/audit.log.jsonl`.
- **Phase 5 — Dashboard:** Query / Graph / Audit tabs on `dashboard.html` via the module bridge.
