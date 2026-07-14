# Enterprise Knowledge Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `modules/enterprise_knowledge/` — a permission-aware Vietnamese enterprise-knowledge RAG (Tasco P1) cloned from `maintenance_copilot`, minus the Neo4j knowledge graph, plus an access-control layer.

**Architecture:** A one-time converter materializes the dataset `.xlsx` into a file corpus (`sample_documents/*.md`) plus access data (`access/users.csv`). Retrieval is permission-aware: the querying user's `(role, department)` compiles into a Qdrant pre-retrieval filter so forbidden documents never enter the candidate set, with an independent second access check before synthesis. Answers are grounded, cited, Vietnamese.

**Tech Stack:** Python 3, `openai` (OpenAI-compatible hosted API), `qdrant-client` (vector store), `chonkie` (chunking), `openpyxl` (converter only). Tests: `pytest` via `uv run --extra dev pytest`, injected fakes, in-memory Qdrant.

## Global Constraints

- Line length 100 (Black + Ruff); Google-style docstrings; type hints on public APIs.
- Module dir: `modules/enterprise_knowledge/`. Scripts under `scripts/`. Tests at repo root `tests/test_enterprise_knowledge_<name>.py`.
- Env prefix `EK_`. Qdrant collection `enterprise_chunks`. Config roles: exactly `index_embed`, `synthesis`.
- Canonical department is the `department_id`: `COMP, HR, FIN, PROD, ENG, OPS, LEGAL, EXEC`. Every department reference (docs + users) is normalized to this before any ACL comparison.
- Access predicate (verified against all 50 labeled Q&A): `Public`/`Internal` → everyone; `Restricted` → `Executive` only; `Confidential` → `Executive` OR `user.department == doc.department`.
- Roles are exactly: `Employee`, `Manager`, `Director`, `Executive`.
- Answers and the synthesis prompt are Vietnamese. Retrieval query text is passed through as-is (corpus is Vietnamese).
- Never leak forbidden documents: zero accessible hits returns a "no accessible documents" message indistinguishable from "does not exist".
- Tests load module files dynamically with `importlib.util.spec_from_file_location` under a unique sentinel name (follow the existing `maintenance_copilot` test pattern). No live network/services in unit tests.
- Every git commit message ends with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- The raw `.xlsx` is an external input (not committed). `modules/enterprise_knowledge/data/` (audit log) is gitignored; `sample_documents/` and `access/` are tracked.

**Reference source (read, do not modify):** `modules/maintenance_copilot/scripts/*.py` — several files below are clones with explicit edits.

---

## File Structure

```
modules/enterprise_knowledge/
├── manifest.json                # module manifest (subagent disabled)
├── requirements.txt             # openai, qdrant-client, chonkie, openpyxl
├── SKILL.md                     # skill contract + Vietnamese runbook
├── .gitignore                   # data/
├── sample_documents/            # 40 materialized *.md (generated; tracked)
├── access/                      # users.csv, roles.csv, permissions.csv (generated; tracked)
├── data/                        # audit.log.jsonl (gitignored)
├── tools/
│   └── build_corpus.py          # one-time xlsx → sample_documents/ + access/*.csv
└── scripts/
    ├── config.py                # roles: index_embed, synthesis; hosted-API defaults
    ├── client.py                # RoleClient (verbatim clone)
    ├── budget.py                # token budgeting (clone; EK_ prefix)
    ├── corpus.py                # front-matter parser → Document
    ├── chunking.py              # Chonkie chunker → citation-anchored records
    ├── identity.py              # NEW: users.csv → User(role, department)
    ├── acl.py                   # NEW: permission predicate + Qdrant filter
    ├── index_store.py           # Qdrant; ACL-filtered query, new payload
    ├── guardrails.py            # cite-or-drop + Vietnamese advisory
    ├── synthesis.py             # Vietnamese grounded answers
    ├── audit.py                 # append-only JSONL trail (clone; EK_ prefix)
    └── knowledge.py             # CLI orchestrator
```

Task order is bottom-up by dependency. Each task ends with a green test and a commit.

---

### Task 1: Module scaffold + config

**Files:**
- Create: `modules/enterprise_knowledge/requirements.txt`
- Create: `modules/enterprise_knowledge/manifest.json`
- Create: `modules/enterprise_knowledge/.gitignore`
- Create: `modules/enterprise_knowledge/scripts/config.py`
- Test: `tests/test_enterprise_knowledge_config.py`

**Interfaces:**
- Produces: `ROLES = ("index_embed", "synthesis")`; `RoleConfig(provider, model, base_url, api_key)`; `load_config(env=None) -> dict[str, RoleConfig]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_config.py
"""Tests for the enterprise_knowledge module-local model-provider config."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "modules" / "enterprise_knowledge" / "scripts" / "config.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ek_config_uut", _CONFIG_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_config_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_config_has_exactly_two_roles():
    mod = _load()
    cfg = mod.load_config(env={})
    assert set(cfg) == {"index_embed", "synthesis"}


def test_defaults_are_hosted_openai():
    mod = _load()
    cfg = mod.load_config(env={})
    assert cfg["index_embed"].base_url.endswith("/v1")
    assert "embedding" in cfg["index_embed"].model
    assert cfg["synthesis"].base_url.endswith("/v1")


def test_api_key_falls_back_to_openai_env():
    mod = _load()
    cfg = mod.load_config(env={"OPENAI_API_KEY": "sk-test-123"})
    assert cfg["index_embed"].api_key == "sk-test-123"


def test_env_overrides_win_per_role():
    mod = _load()
    env = {"EK_SYNTHESIS_BASE_URL": "https://openrouter.ai/api/v1",
           "EK_SYNTHESIS_MODEL": "qwen/qwen-2.5-72b-instruct"}
    cfg = mod.load_config(env=env)
    assert cfg["synthesis"].base_url == "https://openrouter.ai/api/v1"
    assert cfg["synthesis"].model == "qwen/qwen-2.5-72b-instruct"
    assert cfg["index_embed"].base_url != "https://openrouter.ai/api/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_config.py -v`
Expected: FAIL (module file does not exist / import error).

- [ ] **Step 3: Create the scaffold files**

`modules/enterprise_knowledge/requirements.txt`:
```
openai>=1.40
qdrant-client>=1.11
chonkie>=1.0
openpyxl>=3.1
```

`modules/enterprise_knowledge/manifest.json`:
```json
{
  "display_name": "Enterprise Knowledge",
  "tooltip": "Secure enterprise-knowledge RAG · permission-aware AI search (My Tasco)",
  "icon": "icon.svg",
  "dashboard": {
    "title": "Enterprise Knowledge · Secure AI Search",
    "default_height": 820,
    "badge_color": "info"
  },
  "activity": {
    "default": { "running": "Working…", "done": "Done" },
    "actions": {
      "search":   { "running": "Searching knowledge…", "done": "Retrieved" },
      "answer":   { "running": "Composing answer…",    "done": "Answered" },
      "access":   { "running": "Checking access…",     "done": "Checked" }
    }
  },
  "subagent": { "enabled": false, "model": null, "tools": null }
}
```

`modules/enterprise_knowledge/.gitignore`:
```
data/
```

- [ ] **Step 4: Write `scripts/config.py`**

```python
"""Module-local model-provider config for the enterprise_knowledge module.

Maps two feature roles (index_embed, synthesis) to OpenAI-compatible endpoints.
Defaults target a hosted API (OpenAI); every field is overridable per role via
``EK_<ROLE>_<FIELD>``. The api_key default falls back to OPENAI_API_KEY, then
OPENROUTER_API_KEY, so the module runs against your existing keys unchanged.
This layer is self-contained and does not touch Minder's global provider system.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("index_embed", "synthesis")


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for one feature role."""

    provider: str
    model: str
    base_url: str
    api_key: str


# Hosted defaults. Embeddings: OpenAI text-embedding-3-small (1536-dim).
# Synthesis: a multilingual chat model (override to any OpenRouter model).
_DEFAULTS: Dict[str, RoleConfig] = {
    "index_embed": RoleConfig("openai", "text-embedding-3-small",
                              "https://api.openai.com/v1", ""),
    "synthesis": RoleConfig("openai", "gpt-4o-mini",
                            "https://api.openai.com/v1", ""),
}


def _default_api_key(src: Mapping[str, str]) -> str:
    """Fallback API key: OPENAI_API_KEY, then OPENROUTER_API_KEY, else ''."""
    return src.get("OPENAI_API_KEY") or src.get("OPENROUTER_API_KEY") or ""


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles, applying env overrides.

    For each role, ``EK_<ROLE>_PROVIDER|MODEL|BASE_URL|API_KEY`` (role upper-
    cased) overrides the corresponding default field. When no explicit API key
    is set, it falls back to OPENAI_API_KEY / OPENROUTER_API_KEY.
    """
    src = os.environ if env is None else env
    fallback_key = _default_api_key(src)
    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        d = _DEFAULTS[role]
        prefix = f"EK_{role.upper()}_"
        resolved[role] = RoleConfig(
            provider=src.get(f"{prefix}PROVIDER", d.provider),
            model=src.get(f"{prefix}MODEL", d.model),
            base_url=src.get(f"{prefix}BASE_URL", d.base_url),
            api_key=src.get(f"{prefix}API_KEY", fallback_key),
        )
    return resolved
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_config.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add modules/enterprise_knowledge/requirements.txt \
        modules/enterprise_knowledge/manifest.json \
        modules/enterprise_knowledge/.gitignore \
        modules/enterprise_knowledge/scripts/config.py \
        tests/test_enterprise_knowledge_config.py
git commit -m "$(printf 'feat(enterprise_knowledge): module scaffold + role config\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: RoleClient (client.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/client.py`
- Test: `tests/test_enterprise_knowledge_client.py`

**Interfaces:**
- Consumes: `config.RoleConfig`, `budget.output_tokens` (Task 3 — but client only calls it inside `chat()`; the test injects a fake factory and a role whose chat is not exercised for budget, OR Task 3 lands first). **Order note:** implement Task 3 (budget) before running client's `chat` path, or keep the client test to `embed` + factory reuse only. This task tests `embed` + factory reuse (no budget dependency).
- Produces: `RoleClient(config, client_factory=None)` with `.embed(role, texts) -> list[list[float]]` and `.chat(role, messages, **kw) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_client.py
"""Tests for the enterprise_knowledge RoleClient (fake OpenAI factory)."""
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


class _FakeEmbeddings:
    def create(self, model, input):
        class _Item:
            def __init__(self, v): self.embedding = v
        class _Resp:
            data = [_Item([float(len(t))]) for t in input]
        return _Resp()


class _FakeClient:
    instances = 0

    def __init__(self, base_url, api_key):
        _FakeClient.instances += 1
        self.base_url, self.api_key = base_url, api_key
        self.embeddings = _FakeEmbeddings()


def test_embed_dispatches_and_reuses_client_per_endpoint():
    config = _load("config", "ek_cfg_for_client")
    client = _load("client", "ek_client_uut")
    _FakeClient.instances = 0
    rc = client.RoleClient(config.load_config(env={}), client_factory=_FakeClient)
    out = rc.embed("index_embed", ["ab", "abc"])
    assert out == [[2.0], [3.0]]
    # Both roles share the same OpenAI base_url → one underlying client.
    rc.embed("synthesis", ["x"])
    assert _FakeClient.instances == 1


def test_unknown_role_raises():
    config = _load("config", "ek_cfg_for_client2")
    client = _load("client", "ek_client_uut2")
    rc = client.RoleClient(config.load_config(env={}), client_factory=_FakeClient)
    import pytest
    with pytest.raises(ValueError):
        rc.embed("nope", ["x"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_client.py -v`
Expected: FAIL (client.py missing).

- [ ] **Step 3: Create `scripts/client.py`**

Clone `modules/maintenance_copilot/scripts/client.py` **verbatim** into `modules/enterprise_knowledge/scripts/client.py`. Its logic (per-`(base_url, api_key)` client reuse, `embed`, `chat` with `budget.output_tokens` default) is reused unchanged; it imports the sibling `budget` and `config`, which resolve to this module's copies via the `sys.path.insert(0, ...parent)` shim already in the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/client.py tests/test_enterprise_knowledge_client.py
git commit -m "$(printf 'feat(enterprise_knowledge): RoleClient over hosted endpoints\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: Token budgeting (budget.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/budget.py`
- Test: `tests/test_enterprise_knowledge_budget.py`

**Interfaces:**
- Produces: `model_context_limit()`, `output_tokens(role)`, `estimate_tokens(text)`, `input_budget(role, margin=512)`, `fit_text(text, max_tokens)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_budget.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_budget_uut", _MOD / "budget.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_budget_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_estimate_tokens_positive():
    b = _load()
    assert b.estimate_tokens("hello world") >= 1


def test_input_budget_leaves_room_for_output():
    b = _load()
    assert b.input_budget("synthesis") < b.model_context_limit()


def test_fit_text_truncates_when_over_budget():
    b = _load()
    long = "x " * 10000
    fitted = b.fit_text(long, 10)
    assert b.estimate_tokens(fitted) <= 40  # 10 tokens + truncation marker slack
    assert "truncated" in fitted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_budget.py -v`
Expected: FAIL (budget.py missing).

- [ ] **Step 3: Create `scripts/budget.py`**

Clone `modules/maintenance_copilot/scripts/budget.py` and apply exactly these edits:
1. Replace every env-var name `MC_` with `EK_` (i.e. `MC_MODEL_CTX` → `EK_MODEL_CTX`, `MC_<ROLE>_MAX_OUTPUT_TOKENS` → `EK_<ROLE>_MAX_OUTPUT_TOKENS`, and the f-string `f"MC_{role.upper()}_MAX_OUTPUT_TOKENS"` → `f"EK_{role.upper()}_MAX_OUTPUT_TOKENS"`).
2. Change the defaults dict to drop `kg_extract`:
   `_DEFAULT_OUTPUT_TOKENS = {"synthesis": 1024}` (keep `_DEFAULT_OUTPUT_FALLBACK = 1024`).
3. Update the module docstring's env references from `MC_` to `EK_`.
Everything else (the `_CHARS_PER_TOKEN` heuristic, `_SAFETY_MARGIN`, function bodies) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_budget.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/budget.py tests/test_enterprise_knowledge_budget.py
git commit -m "$(printf 'feat(enterprise_knowledge): token budgeting helpers\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: Corpus front-matter parser (corpus.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/corpus.py`
- Test: `tests/test_enterprise_knowledge_corpus.py`

**Interfaces:**
- Produces: `Document(doc_id, title, department, classification, owner, knowledge_space, last_updated, language, path, text)`; `parse_document(path) -> Document`; `load_corpus(root) -> list[Document]`. Required front-matter keys: `doc_id, title, department, classification`. Missing `knowledge_space` is derived from `department`; `owner` defaults to `department`; `last_updated`/`language` default to `""`/`"vi"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_corpus.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_corpus_uut", _MOD / "corpus.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_corpus_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_DOC = """---
doc_id: DOC007
title: Khung lương tham khảo
department: HR
classification: Confidential
owner: HR
knowledge_space: Department Knowledge
last_updated: 2025-08-22
language: vi
---
# Khung lương tham khảo
Nội dung mật của phòng Nhân sự.
"""


def test_parse_document_reads_frontmatter(tmp_path):
    c = _load()
    p = tmp_path / "DOC007.md"
    p.write_text(_DOC, encoding="utf-8")
    doc = c.parse_document(str(p))
    assert doc.doc_id == "DOC007"
    assert doc.department == "HR"
    assert doc.classification == "Confidential"
    assert doc.text.startswith("# Khung lương")


def test_missing_required_key_raises(tmp_path):
    c = _load()
    p = tmp_path / "bad.md"
    p.write_text("---\ntitle: x\n---\nbody\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        c.parse_document(str(p))


def test_knowledge_space_derived_when_absent(tmp_path):
    c = _load()
    body = "---\ndoc_id: DOC001\ntitle: t\ndepartment: COMP\nclassification: Public\n---\nx\n"
    p = tmp_path / "DOC001.md"
    p.write_text(body, encoding="utf-8")
    doc = c.parse_document(str(p))
    assert doc.knowledge_space == "Company Knowledge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_corpus.py -v`
Expected: FAIL (corpus.py missing).

- [ ] **Step 3: Create `scripts/corpus.py`**

```python
"""Parse enterprise documents into structured Document records.

A source file starts with a ``---``-delimited front-matter block declaring
``doc_id``, ``title``, ``department`` (canonical department_id), and
``classification``, optionally ``owner``, ``knowledge_space``, ``last_updated``,
``language`` — followed by the Vietnamese body. Only ``.md``/``.txt`` are handled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REQUIRED = ("doc_id", "title", "department", "classification")

# Canonical department_id -> knowledge space (used to derive when absent).
_KNOWLEDGE_SPACE = {
    "COMP": "Company Knowledge",
    "EXEC": "Executive Knowledge",
}
_DEPARTMENT_KNOWLEDGE = "Department Knowledge"


@dataclass(frozen=True)
class Document:
    """A parsed enterprise document: front-matter metadata plus body text."""

    doc_id: str
    title: str
    department: str
    classification: str
    owner: str
    knowledge_space: str
    last_updated: str
    language: str
    path: str
    text: str


def knowledge_space_for(department: str) -> str:
    """Derive the knowledge space from a canonical department_id."""
    return _KNOWLEDGE_SPACE.get(department, _DEPARTMENT_KNOWLEDGE)


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body). Front-matter is a leading ``---`` ... ``---`` block."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta: dict[str, str] = {}
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

    Raises:
        ValueError: If a required front-matter key is missing.
    """
    raw = Path(path).read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    for key in _REQUIRED:
        if key not in meta:
            raise ValueError(f"{path}: missing front-matter key {key!r}")
    department = str(meta["department"])
    return Document(
        doc_id=meta["doc_id"],
        title=meta["title"],
        department=department,
        classification=meta["classification"],
        owner=meta.get("owner", department),
        knowledge_space=meta.get("knowledge_space") or knowledge_space_for(department),
        last_updated=meta.get("last_updated", ""),
        language=meta.get("language", "vi"),
        path=path,
        text=body,
    )


def load_corpus(root: str) -> list[Document]:
    """Parse every ``.md``/``.txt`` directly under ``root``, sorted by filename."""
    paths = sorted(
        p for p in Path(root).iterdir()
        if p.suffix in (".md", ".txt") and p.is_file()
    )
    return [parse_document(str(p)) for p in paths]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_corpus.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/corpus.py tests/test_enterprise_knowledge_corpus.py
git commit -m "$(printf 'feat(enterprise_knowledge): corpus front-matter parser\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: Chunking (chunking.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/chunking.py`
- Test: `tests/test_enterprise_knowledge_chunking.py`

**Interfaces:**
- Consumes: `corpus.Document`.
- Produces: `ChunkRecord(doc_id, chunk_id, text, start_index, end_index, token_count, title, department, classification, knowledge_space, owner, source_path, citation)`; `chunk_document(doc, chunker=None) -> list[ChunkRecord]`. `chunk_id = f"{doc.doc_id}#{i}"`; `citation = f"{title} [{doc_id}] · {chunk_id}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_chunking.py
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


class _FakeChunk:
    def __init__(self, text, start, end):
        self.text, self.start_index, self.end_index = text, start, end
        self.token_count = len(text.split())


class _FakeChunker:
    def chunk(self, text):
        return [_FakeChunk("part one", 0, 8), _FakeChunk("part two", 9, 17)]


def test_chunk_document_builds_citation_anchored_records():
    corpus = _load("corpus", "ek_corpus_for_chunk")
    chunking = _load("chunking", "ek_chunking_uut")
    doc = corpus.Document(
        doc_id="DOC007", title="Khung lương tham khảo", department="HR",
        classification="Confidential", owner="HR",
        knowledge_space="Department Knowledge", last_updated="2025-08-22",
        language="vi", path="/x/DOC007.md", text="part one part two",
    )
    recs = chunking.chunk_document(doc, chunker=_FakeChunker())
    assert [r.chunk_id for r in recs] == ["DOC007#0", "DOC007#1"]
    assert recs[0].classification == "Confidential"
    assert recs[0].department == "HR"
    assert recs[0].citation == "Khung lương tham khảo [DOC007] · DOC007#0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_chunking.py -v`
Expected: FAIL (chunking.py missing).

- [ ] **Step 3: Create `scripts/chunking.py`**

```python
"""Split a Document into chunk records carrying citation anchors.

Uses Chonkie's ``RecursiveChunker`` (structure-aware, no embedding model). Each
chunk keeps its character offsets and its document's metadata so a returned
passage traces back to the exact span and its access classification.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Document  # type: ignore[import-not-found]

_DEFAULT_CHUNK_SIZE = 512


def _chunk_size() -> int:
    """Resolve the chunk size from ``EK_CHUNK_SIZE``, falling back on the default."""
    try:
        value = int(os.environ["EK_CHUNK_SIZE"])
    except (KeyError, TypeError, ValueError):
        return _DEFAULT_CHUNK_SIZE
    return value if value > 0 else _DEFAULT_CHUNK_SIZE


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk plus the metadata needed to cite and access-filter it."""

    doc_id: str
    chunk_id: str
    text: str
    start_index: int
    end_index: int
    token_count: int
    title: str
    department: str
    classification: str
    knowledge_space: str
    owner: str
    source_path: str
    citation: str


def _default_chunker():
    from chonkie import RecursiveChunker  # local import: heavy optional dep

    return RecursiveChunker(chunk_size=_chunk_size())


def chunk_document(doc: Document, chunker: object | None = None) -> list[ChunkRecord]:
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
    records: list[ChunkRecord] = []
    for i, chunk in enumerate(ch.chunk(doc.text)):
        chunk_id = f"{doc.doc_id}#{i}"
        records.append(
            ChunkRecord(
                doc_id=doc.doc_id,
                chunk_id=chunk_id,
                text=chunk.text,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                token_count=chunk.token_count,
                title=doc.title,
                department=doc.department,
                classification=doc.classification,
                knowledge_space=doc.knowledge_space,
                owner=doc.owner,
                source_path=doc.path,
                citation=f"{doc.title} [{doc.doc_id}] · {chunk_id}",
            )
        )
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_chunking.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/chunking.py tests/test_enterprise_knowledge_chunking.py
git commit -m "$(printf 'feat(enterprise_knowledge): metadata-carrying chunking\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 6: Identity (identity.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/identity.py`
- Test: `tests/test_enterprise_knowledge_identity.py`

**Interfaces:**
- Produces: `User(user_id, full_name, role, department, status)`; `UnknownUserError(ValueError)`; `load_users(path) -> dict[str, User]`; `resolve(users, user_id) -> User`; `default_users_path() -> str` (`EK_USERS_CSV` or `<module>/access/users.csv`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_identity.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_identity_uut", _MOD / "identity.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_identity_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_CSV = (
    "user_id,full_name,department,role,email,status\n"
    "U004,Phạm Quốc Dũng,ENG,Employee,user004@synthetic.local,Active\n"
    "U007,Vũ Thị Lan,EXEC,Executive,user007@synthetic.local,Active\n"
)


def test_load_and_resolve(tmp_path):
    ident = _load()
    p = tmp_path / "users.csv"
    p.write_text(_CSV, encoding="utf-8")
    users = ident.load_users(str(p))
    u = ident.resolve(users, "U004")
    assert u.role == "Employee"
    assert u.department == "ENG"


def test_unknown_user_raises(tmp_path):
    ident = _load()
    p = tmp_path / "users.csv"
    p.write_text(_CSV, encoding="utf-8")
    users = ident.load_users(str(p))
    import pytest
    with pytest.raises(ident.UnknownUserError):
        ident.resolve(users, "U999")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_identity.py -v`
Expected: FAIL (identity.py missing).

- [ ] **Step 3: Create `scripts/identity.py`**

```python
"""Load synthetic users and resolve a user_id to an access identity.

Users come from ``access/users.csv`` (materialized from the dataset). The
``department`` column is a canonical department_id (COMP/HR/FIN/PROD/ENG/OPS/
LEGAL/EXEC) so it compares exactly against document departments in the ACL layer.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class UnknownUserError(ValueError):
    """Raised when a user_id is not present in the users table."""


@dataclass(frozen=True)
class User:
    """A resolved access identity."""

    user_id: str
    full_name: str
    role: str          # Employee | Manager | Director | Executive
    department: str    # canonical department_id
    status: str


def default_users_path() -> str:
    """Return EK_USERS_CSV if set, else ``<module>/access/users.csv``."""
    override = os.environ.get("EK_USERS_CSV")
    if override:
        return override
    return str(Path(__file__).resolve().parent.parent / "access" / "users.csv")


def load_users(path: str | None = None) -> Dict[str, User]:
    """Load the users table into a ``{user_id: User}`` map."""
    target = path or default_users_path()
    users: Dict[str, User] = {}
    with open(target, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            user = User(
                user_id=row["user_id"].strip(),
                full_name=row.get("full_name", "").strip(),
                role=row["role"].strip(),
                department=row["department"].strip(),
                status=row.get("status", "Active").strip(),
            )
            users[user.user_id] = user
    return users


def resolve(users: Dict[str, User], user_id: str) -> User:
    """Return the :class:`User` for ``user_id`` or raise :class:`UnknownUserError`."""
    try:
        return users[user_id]
    except KeyError as exc:
        raise UnknownUserError(f"unknown user_id: {user_id!r}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_identity.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/identity.py tests/test_enterprise_knowledge_identity.py
git commit -m "$(printf 'feat(enterprise_knowledge): user identity resolution\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 7: Access control (acl.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/acl.py`
- Test: `tests/test_enterprise_knowledge_acl.py`

**Interfaces:**
- Consumes: `identity.User`.
- Produces: `Decision(allowed: bool, reason: str)`; `can_access(user, doc: dict) -> Decision` (doc carries `classification`, `department`); `accessible_classifications(user) -> set[str]`; `build_filter(user) -> qdrant Filter | None` (None = executive, no restriction); constants `PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, CLASSIFICATIONS, EXECUTIVE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_acl.py
"""ACL predicate tests, seeded with labeled Deny/Allow cases from the dataset."""
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


def _user(role, dept):
    ident = _load("identity", "ek_identity_for_acl")
    return ident.User("U", "n", role, dept, "Active")


# (role, user_dept, doc_classification, doc_dept, expected_allowed) — from Public_Evaluation.
CASES = [
    ("Employee", "ENG", "Confidential", "HR", False),   # P009 Deny
    ("Employee", "HR", "Confidential", "HR", True),      # P010 Allow
    ("Employee", "PROD", "Restricted", "EXEC", False),   # P007 Deny
    ("Executive", "EXEC", "Restricted", "EXEC", True),   # P008 Allow
    ("Manager", "FIN", "Confidential", "OPS", False),    # P035 Deny
    ("Manager", "OPS", "Confidential", "OPS", True),     # P034 Allow
    ("Employee", "ENG", "Internal", "COMP", True),       # internal → all
    ("Employee", "PROD", "Public", "COMP", True),        # public → all
]


@pytest.mark.parametrize("role,udept,cls,ddept,expected", CASES)
def test_can_access_matrix(role, udept, cls, ddept, expected):
    acl = _load("acl", "ek_acl_uut")
    dec = acl.can_access(_user(role, udept), {"classification": cls, "department": ddept})
    assert dec.allowed is expected


def test_build_filter_none_for_executive():
    acl = _load("acl", "ek_acl_uut2")
    assert acl.build_filter(_user("Executive", "EXEC")) is None


def test_build_filter_is_a_qdrant_filter_for_employee():
    acl = _load("acl", "ek_acl_uut3")
    from qdrant_client import models
    f = acl.build_filter(_user("Employee", "ENG"))
    assert isinstance(f, models.Filter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_acl.py -v`
Expected: FAIL (acl.py missing).

- [ ] **Step 3: Create `scripts/acl.py`**

```python
"""Role/classification access control for enterprise documents.

Encodes the classification × role matrix from the dataset's Permissions sheet:
Public/Internal are open to all employees; Restricted is Executive-only;
Confidential is limited to the owning department (Executives see all). The same
predicate powers a Qdrant pre-retrieval filter and a citation-time re-check, so
enforcement is defence-in-depth and unit-tested in isolation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity import User  # type: ignore[import-not-found]

EXECUTIVE = "Executive"
PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED = (
    "Public", "Internal", "Confidential", "Restricted",
)
CLASSIFICATIONS = (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)


@dataclass(frozen=True)
class Decision:
    """An access decision with a human-readable reason."""

    allowed: bool
    reason: str


def can_access(user: User, doc: dict) -> Decision:
    """Decide whether ``user`` may access a document.

    Args:
        user: The resolved identity.
        doc: A mapping carrying ``classification`` and ``department`` (canonical id).

    Returns:
        A :class:`Decision` — advisory-quality reason included for the audit trail.
    """
    classification = str(doc.get("classification", ""))
    doc_department = str(doc.get("department", ""))
    if classification in (PUBLIC, INTERNAL):
        return Decision(True, f"{classification.lower()}: all employees")
    if classification == RESTRICTED:
        if user.role == EXECUTIVE:
            return Decision(True, "restricted: executive")
        return Decision(False, "restricted: executive only")
    if classification == CONFIDENTIAL:
        if user.role == EXECUTIVE:
            return Decision(True, "confidential: executive sees all departments")
        if user.department == doc_department:
            return Decision(True, "confidential: own department")
        return Decision(False, "confidential: other department")
    return Decision(False, f"unknown classification: {classification!r}")


def accessible_classifications(user: User) -> set[str]:
    """Classifications this user can ever access (Confidential still dept-gated)."""
    if user.role == EXECUTIVE:
        return set(CLASSIFICATIONS)
    return {PUBLIC, INTERNAL, CONFIDENTIAL}


def build_filter(user: User):
    """Compile a Qdrant payload filter selecting only retrievable documents.

    Executive → ``None`` (no restriction; sees everything). Everyone else →
    Public OR Internal OR (Confidential AND department == the user's). Restricted
    documents match no clause, so they never enter the candidate set.
    """
    from qdrant_client import models

    if user.role == EXECUTIVE:
        return None
    return models.Filter(
        should=[
            models.FieldCondition(
                key="classification", match=models.MatchValue(value=PUBLIC)
            ),
            models.FieldCondition(
                key="classification", match=models.MatchValue(value=INTERNAL)
            ),
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="classification",
                        match=models.MatchValue(value=CONFIDENTIAL),
                    ),
                    models.FieldCondition(
                        key="department",
                        match=models.MatchValue(value=user.department),
                    ),
                ]
            ),
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_acl.py -v`
Expected: 10 passed (8 parametrized + 2).

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/acl.py tests/test_enterprise_knowledge_acl.py
git commit -m "$(printf 'feat(enterprise_knowledge): role/classification access control\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 8: Index store (index_store.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/index_store.py`
- Test: `tests/test_enterprise_knowledge_index_store.py`

**Interfaces:**
- Consumes: `chunking.ChunkRecord`, `acl.build_filter`.
- Produces: `IndexStore(qdrant, embed_fn, collection="enterprise_chunks")` with `ensure_collection(dim)`, `upsert_chunks(records) -> int`, `query(text, k=5, acl_filter=None, department=None) -> list[dict]`, `list_indexed() -> dict`, `reset()`. Hit dict keys: `score, citation, text, doc_id, chunk_id, title, department, classification, knowledge_space`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_index_store.py
"""Index store tests: real in-memory Qdrant, fake embeddings, ACL filtering."""
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


def _rec(chunking, doc_id, i, text, cls, dept):
    cid = f"{doc_id}#{i}"
    return chunking.ChunkRecord(
        doc_id=doc_id, chunk_id=cid, text=text, start_index=0, end_index=len(text),
        token_count=len(text.split()), title=f"T{doc_id}", department=dept,
        classification=cls, knowledge_space="Department Knowledge", owner=dept,
        source_path=f"/x/{doc_id}.md", citation=f"T{doc_id} [{doc_id}] · {cid}",
    )


def _embed_fn(texts):
    out = []
    for t in texts:
        low = t.lower()
        out.append([
            1.0 if "lương" in low else 0.0,
            1.0 if "nghỉ" in low else 0.0,
            1.0 if "sản phẩm" in low else 0.0,
        ])
    return out


@pytest.fixture()
def env():
    from qdrant_client import QdrantClient
    chunking = _load("chunking", "ek_chunk_for_store")
    identity = _load("identity", "ek_ident_for_store")
    acl = _load("acl", "ek_acl_for_store")
    index_store = _load("index_store", "ek_index_store_uut")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    s.upsert_chunks([
        _rec(chunking, "DOC007", 0, "khung lương phòng nhân sự", "Confidential", "HR"),
        _rec(chunking, "DOC002", 0, "chính sách nghỉ phép", "Internal", "COMP"),
        _rec(chunking, "DOC016", 0, "chiến lược sản phẩm", "Confidential", "PROD"),
    ])
    return s, identity, acl


def test_employee_cannot_retrieve_other_dept_confidential(env):
    s, identity, acl = env
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(eng))
    ids = {h["doc_id"] for h in hits}
    assert "DOC007" not in ids  # HR confidential is filtered out


def test_hr_employee_can_retrieve_own_confidential(env):
    s, identity, acl = env
    hr = identity.User("U001", "n", "Employee", "HR", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(hr))
    assert "DOC007" in {h["doc_id"] for h in hits}


def test_executive_sees_all(env):
    s, identity, acl = env
    ex = identity.User("U007", "n", "Executive", "EXEC", "Active")
    hits = s.query("sản phẩm", k=5, acl_filter=acl.build_filter(ex))
    assert "DOC016" in {h["doc_id"] for h in hits}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_index_store.py -v`
Expected: FAIL (index_store.py missing).

- [ ] **Step 3: Create `scripts/index_store.py`**

```python
"""Qdrant-backed vector index for enterprise document chunks.

Embeds chunk text with an injected ``embed_fn`` (production: hosted embeddings
via the ``index_embed`` role) and stores one point per chunk with its full
metadata payload — including ``classification`` and canonical ``department`` —
so retrieval can be constrained by an access-control filter.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Callable

from qdrant_client import QdrantClient, models

if TYPE_CHECKING:
    from chunking import ChunkRecord  # type: ignore[import-not-found]

COLLECTION = "enterprise_chunks"

# Fixed namespace so uuid5(citation) is stable across processes → idempotent re-index.
_POINT_NS = uuid.UUID("b8f1c2d3-4e5a-6b7c-8d9e-0f1a2b3c4d5e")

EmbedFn = Callable[[list[str]], list[list[float]]]


class IndexStore:
    """Create/populate/query the ``enterprise_chunks`` collection."""

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

    def upsert_chunks(self, records: list["ChunkRecord"]) -> int:
        """Embed and upsert one point per record. Returns the number stored.

        Point ids are a stable ``uuid5`` of the citation, so re-indexing the same
        chunk updates in place rather than duplicating.
        """
        if not records:
            return 0
        vectors = self._embed([r.text for r in records])
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(_POINT_NS, rec.citation)),
                vector=vec,
                payload={
                    "doc_id": rec.doc_id,
                    "chunk_id": rec.chunk_id,
                    "text": rec.text,
                    "title": rec.title,
                    "department": rec.department,
                    "classification": rec.classification,
                    "knowledge_space": rec.knowledge_space,
                    "owner": rec.owner,
                    "citation": rec.citation,
                },
            )
            for rec, vec in zip(records, vectors)
        ]
        self._q.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    def query(
        self,
        text: str,
        k: int = 5,
        acl_filter: models.Filter | None = None,
        department: str | None = None,
    ) -> list[dict]:
        """Embed ``text`` and return the top-``k`` access-filtered hits.

        Args:
            text: The query text.
            k: Max hits to return.
            acl_filter: Access-control filter from ``acl.build_filter(user)``;
                ``None`` means no access restriction (executive).
            department: Optional narrowing to a single canonical department_id
                *within* the accessible scope. Never widens access.

        Returns:
            Hit dicts with score, citation, text, and metadata.
        """
        query_filter = self._combine(acl_filter, department)
        vector = self._embed([text])[0]
        result = self._q.query_points(
            collection_name=self._collection,
            query=vector,
            limit=k,
            query_filter=query_filter,
        )
        return [
            {
                "score": point.score,
                "citation": point.payload["citation"],
                "text": point.payload["text"],
                "doc_id": point.payload["doc_id"],
                "chunk_id": point.payload["chunk_id"],
                "title": point.payload["title"],
                "department": point.payload["department"],
                "classification": point.payload["classification"],
                "knowledge_space": point.payload["knowledge_space"],
            }
            for point in result.points
        ]

    @staticmethod
    def _combine(
        acl_filter: models.Filter | None, department: str | None
    ) -> models.Filter | None:
        """Combine the ACL filter with an optional department narrowing."""
        if department is None:
            return acl_filter
        dept_cond = models.FieldCondition(
            key="department", match=models.MatchValue(value=department)
        )
        if acl_filter is None:
            return models.Filter(must=[dept_cond])
        return models.Filter(must=[acl_filter, dept_cond])

    def list_indexed(self) -> dict:
        """Return the point count and a breakdown by classification and department."""
        count = self._q.count(collection_name=self._collection).count
        by_class: dict[str, int] = {}
        by_dept: dict[str, int] = {}
        offset = None
        while True:
            recs, offset = self._q.scroll(
                collection_name=self._collection, with_payload=True, limit=256, offset=offset
            )
            for r in recs:
                by_class[r.payload["classification"]] = by_class.get(
                    r.payload["classification"], 0) + 1
                by_dept[r.payload["department"]] = by_dept.get(
                    r.payload["department"], 0) + 1
            if offset is None:
                break
        return {"count": count, "by_classification": by_class, "by_department": by_dept}

    def reset(self) -> None:
        """Delete the collection if it exists."""
        if self._q.collection_exists(self._collection):
            self._q.delete_collection(self._collection)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_index_store.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/index_store.py tests/test_enterprise_knowledge_index_store.py
git commit -m "$(printf 'feat(enterprise_knowledge): access-filtered Qdrant index\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 9: Guardrails (guardrails.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/guardrails.py`
- Test: `tests/test_enterprise_knowledge_guardrails.py`

**Interfaces:**
- Produces: `ADVISORY_NOTE` (Vietnamese); `split_sentences(text)`; `enforce_citations(answer, allowed) -> {"answer","grounded","dropped"}`; `answer_confidence(hits) -> float`; `needs_manual_review(confidence, grounded_count, min_confidence=None) -> bool`; `default_min_confidence() -> float` (`EK_MIN_CONFIDENCE`, default 0.35).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_guardrails.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_guardrails_uut", _MOD / "guardrails.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_guardrails_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_enforce_citations_drops_uncited_sentences():
    g = _load()
    out = g.enforce_citations(
        "Nhân viên có 15 ngày phép [DOC002#0]. Câu này không có trích dẫn.",
        allowed={"DOC002#0"},
    )
    assert "[DOC002#0]" in out["answer"]
    assert "không có trích dẫn" not in out["answer"]
    assert len(out["dropped"]) == 1


def test_needs_review_when_nothing_grounded():
    g = _load()
    assert g.needs_manual_review(0.9, 0) is True


def test_needs_review_when_low_confidence():
    g = _load()
    assert g.needs_manual_review(0.1, 3) is True
    assert g.needs_manual_review(0.9, 3) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_guardrails.py -v`
Expected: FAIL (guardrails.py missing).

- [ ] **Step 3: Create `scripts/guardrails.py`**

Clone `modules/maintenance_copilot/scripts/guardrails.py` and apply exactly these edits:
1. Replace the `ADVISORY_NOTE` constant body with the Vietnamese advisory:
```python
ADVISORY_NOTE = (
    "Chỉ mang tính hỗ trợ — vui lòng kiểm chứng thông tin với tài liệu gốc "
    "trong phạm vi quyền truy cập của bạn. Kết quả có thể chưa đầy đủ."
)
```
2. Change the env var `MC_MIN_CONFIDENCE` → `EK_MIN_CONFIDENCE` (in `default_min_confidence()`).
3. Update the module docstring to drop the aviation "dispatch" wording; keep it generic ("low-confidence results are routed for manual review; output is always advisory").
Everything else (`split_sentences`, `enforce_citations`, `answer_confidence`, `needs_manual_review`, the regexes, `_DEFAULT_MIN_CONFIDENCE = 0.35`) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_guardrails.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/guardrails.py tests/test_enterprise_knowledge_guardrails.py
git commit -m "$(printf 'feat(enterprise_knowledge): citation + advisory guardrails\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 10: Synthesis (synthesis.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/synthesis.py`
- Test: `tests/test_enterprise_knowledge_synthesis.py`

**Interfaces:**
- Consumes: `budget`, `guardrails`.
- Produces: `synthesize(query, hits, chat_fn) -> dict` with keys `answer, grounded, dropped, confidence, needs_review, disclaimer, citations`; `build_synthesis_messages(query, hits) -> list[dict]`; `fit_hits_to_budget(query, hits) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_synthesis.py
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


def test_synthesize_grounds_and_cites():
    _load("budget", "ek_budget_for_synth")
    _load("guardrails", "ek_guardrails_for_synth")
    synthesis = _load("synthesis", "ek_synthesis_uut")
    hits = [{"chunk_id": "DOC002#0", "text": "Nhân viên có 15 ngày phép năm.", "score": 0.9}]

    def fake_chat(messages):
        return "Nhân viên được 15 ngày nghỉ phép năm [DOC002#0]."

    out = synthesis.synthesize("Bao nhiêu ngày phép?", hits, fake_chat)
    assert "[DOC002#0]" in out["answer"]
    assert out["citations"] == ["DOC002#0"]
    assert out["needs_review"] is False


def test_synthesize_flags_review_when_uncited():
    _load("budget", "ek_budget_for_synth2")
    _load("guardrails", "ek_guardrails_for_synth2")
    synthesis = _load("synthesis", "ek_synthesis_uut2")
    hits = [{"chunk_id": "DOC002#0", "text": "x", "score": 0.9}]
    out = synthesis.synthesize("q", hits, lambda m: "Câu trả lời không trích dẫn.")
    assert out["needs_review"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_synthesis.py -v`
Expected: FAIL (synthesis.py missing).

- [ ] **Step 3: Create `scripts/synthesis.py`**

Clone `modules/maintenance_copilot/scripts/synthesis.py` and apply exactly these edits:
1. Replace `_SYSTEM_PROMPT` with the Vietnamese, access-aware prompt:
```python
_SYSTEM_PROMPT = (
    "Bạn trả lời câu hỏi nội bộ doanh nghiệp CHỈ dựa trên các đoạn trích được "
    "cung cấp. Trả lời bằng tiếng Việt. Trích dẫn mọi khẳng định bằng thẻ đoạn "
    "trong ngoặc vuông, ví dụ [DOC002#0]. Không dùng kiến thức bên ngoài. Nếu "
    "các đoạn trích không trả lời được câu hỏi, hãy nói rõ điều đó."
)
```
2. Replace `_REVIEW_NOTICE` with a Vietnamese equivalent:
```python
_REVIEW_NOTICE = (
    "Chưa đủ căn cứ trong tài liệu — cần con người kiểm tra thủ công. "
    "Xem các đoạn trích và đối chiếu với tài liệu gốc được phép truy cập."
)
```
3. Update the module docstring to drop aviation wording.
Everything else (`fit_hits_to_budget`, `build_synthesis_messages`, `synthesize` body computing `fitted`/`allowed`/`checked`/`confidence`/`review`/`citations`, imports of `budget` and `guardrails`) is unchanged. Note `build_synthesis_messages` already builds passages as `[chunk_id] text`, matching our chunk_ids.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_synthesis.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/synthesis.py tests/test_enterprise_knowledge_synthesis.py
git commit -m "$(printf 'feat(enterprise_knowledge): Vietnamese grounded synthesis\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 11: Audit trail (audit.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/audit.py`
- Test: `tests/test_enterprise_knowledge_audit.py`

**Interfaces:**
- Produces: `default_log_path() -> str` (`EK_AUDIT_LOG` or `<module>/data/audit.log.jsonl`); `append_event(event, path=None, now_fn=None) -> dict` (stamps UTC `ts`); `read_events(path=None) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_audit.py
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_audit_uut", _MOD / "audit.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_audit_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_append_then_read_roundtrip(tmp_path):
    a = _load()
    log = tmp_path / "audit.jsonl"
    a.append_event(
        {"type": "query", "user_id": "U004", "role": "Employee",
         "department": "ENG", "permission_decision": "allow"},
        path=str(log), now_fn=lambda: datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    events = a.read_events(str(log))
    assert events[0]["user_id"] == "U004"
    assert events[0]["ts"].startswith("2026-07-03")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_audit.py -v`
Expected: FAIL (audit.py missing).

- [ ] **Step 3: Create `scripts/audit.py`**

Clone `modules/maintenance_copilot/scripts/audit.py` and apply exactly one edit: change the env override name `MC_AUDIT_LOG` → `EK_AUDIT_LOG` in `default_log_path()`. The default path already resolves to `<module>/data/audit.log.jsonl` relative to the file, which is correct for this module. Everything else is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_audit.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/audit.py tests/test_enterprise_knowledge_audit.py
git commit -m "$(printf 'feat(enterprise_knowledge): append-only audit trail\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 12: CLI orchestrator (knowledge.py)

**Files:**
- Create: `modules/enterprise_knowledge/scripts/knowledge.py`
- Test: `tests/test_enterprise_knowledge_cli.py`

**Interfaces:**
- Consumes: all of `config, client, corpus, chunking, identity, acl, index_store, synthesis, guardrails, audit`.
- Produces: `main(argv=None) -> int`; helpers `guard_accessible(user, hits) -> tuple[list, list]`, `load_doc_meta(samples) -> dict[str, dict]`, `build_parser()`. Subcommands: `health, ingest, query, whoami, can-access, list, reset, audit`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_cli.py
"""CLI wiring tests for whoami / can-access / guard_accessible (no live services)."""
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


def test_guard_accessible_splits_hits():
    k = _load("knowledge", "ek_knowledge_uut")
    identity = _load("identity", "ek_ident_for_cli")
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = [
        {"doc_id": "DOC002", "classification": "Internal", "department": "COMP"},
        {"doc_id": "DOC007", "classification": "Confidential", "department": "HR"},
    ]
    safe, blocked = k.guard_accessible(eng, hits)
    assert [h["doc_id"] for h in safe] == ["DOC002"]
    assert [h["doc_id"] for h in blocked] == ["DOC007"]


def test_can_access_command_denies(capsys, tmp_path):
    k = _load("knowledge", "ek_knowledge_uut2")
    # users.csv
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U004,n,ENG,Employee,e,Active\n", encoding="utf-8")
    # a single sample doc
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "DOC036.md").write_text(
        "---\ndoc_id: DOC036\ntitle: t\ndepartment: EXEC\nclassification: Restricted\n---\nx\n",
        encoding="utf-8")
    rc = k.main(["can-access", "U004", "DOC036",
                 "--users", str(users), "--samples", str(docs)])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"allowed": false' in out.lower() or '"allowed": false' in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_cli.py -v`
Expected: FAIL (knowledge.py missing).

- [ ] **Step 3: Create `scripts/knowledge.py`**

```python
#!/usr/bin/env python
"""enterprise_knowledge CLI — secure, permission-aware knowledge retrieval.

Every retrieval is scoped to the querying user's (role, department): an ACL
filter constrains the vector search, and an independent guard re-checks each hit
before synthesis. Answers are grounded, cited, and Vietnamese.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config  # type: ignore[import-not-found]
from client import RoleClient  # type: ignore[import-not-found]
from corpus import load_corpus  # type: ignore[import-not-found]
from chunking import chunk_document  # type: ignore[import-not-found]
from index_store import IndexStore  # type: ignore[import-not-found]
import identity  # type: ignore[import-not-found]
import acl  # type: ignore[import-not-found]
import audit  # type: ignore[import-not-found]

# Output dim of the embedding model. Default matches OpenAI text-embedding-3-small.
EMBED_DIM = 1536


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _samples_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "sample_documents")


def _build_store(embed_fn: Callable | None = None, qdrant: object | None = None) -> IndexStore:
    """Build an IndexStore from EK_QDRANT_URL + a RoleClient index_embed embedder."""
    from qdrant_client import QdrantClient

    if qdrant is None:
        qdrant = QdrantClient(url=_env("EK_QDRANT_URL", "http://localhost:6333"))
    if embed_fn is None:
        rc = RoleClient(load_config())
        embed_fn = lambda texts: rc.embed("index_embed", texts)  # noqa: E731
    store = IndexStore(qdrant, embed_fn)
    store.ensure_collection(dim=int(_env("EK_EMBED_DIM", str(EMBED_DIM))))
    return store


def _synthesis_chat_fn() -> Callable[[list], str]:
    rc = RoleClient(load_config())
    return lambda messages: rc.chat("synthesis", messages)


def guard_accessible(user: "identity.User", hits: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split hits into (accessible, blocked) by re-running the ACL predicate.

    Defence in depth: retrieval is already ACL-filtered, so ``blocked`` should be
    empty; anything here indicates a filter/index mismatch worth auditing.
    """
    safe: list[dict] = []
    blocked: list[dict] = []
    for hit in hits:
        decision = acl.can_access(
            user, {"classification": hit["classification"], "department": hit["department"]}
        )
        (safe if decision.allowed else blocked).append(hit)
    return safe, blocked


def load_doc_meta(samples: str) -> dict[str, dict]:
    """Map doc_id -> {classification, department, title} from the corpus files."""
    meta: dict[str, dict] = {}
    for doc in load_corpus(samples):
        meta[doc.doc_id] = {
            "classification": doc.classification,
            "department": doc.department,
            "title": doc.title,
        }
    return meta


# --- commands ---------------------------------------------------------------

def _cmd_health() -> int:
    cfg = load_config()
    rc = RoleClient(cfg)
    out: dict[str, str] = {}

    def probe(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            out[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - health must never raise
            out[name] = f"error: {exc}"

    probe("index_embed", lambda: rc.embed("index_embed", ["ping"]))
    probe("synthesis", lambda: rc.chat("synthesis", [{"role": "user", "content": "ping"}],
                                       max_tokens=1))

    def qdrant_probe() -> None:
        from qdrant_client import QdrantClient

        QdrantClient(url=_env("EK_QDRANT_URL", "http://localhost:6333")).get_collections()

    probe("qdrant", qdrant_probe)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if all(v == "ok" for v in out.values()) else 1


def _cmd_ingest(samples: str) -> int:
    store = _build_store()
    docs = load_corpus(samples)
    total = 0
    for doc in docs:
        total += store.upsert_chunks(chunk_document(doc))
    print(json.dumps({"documents": len(docs), "chunks": total}, indent=2))
    return 0


def _resolve_user(user_id: str, users_path: str | None) -> "identity.User":
    users = identity.load_users(users_path or identity.default_users_path())
    return identity.resolve(users, user_id)


def _cmd_query(text: str, user_id: str, k: int, department: str | None,
               synthesize: bool, users_path: str | None) -> int:
    user = _resolve_user(user_id, users_path)
    store = _build_store()
    hits = store.query(text, k=k, acl_filter=acl.build_filter(user), department=department)
    hits, blocked = guard_accessible(user, hits)
    payload: dict[str, object] = {
        "query": text,
        "user": {"user_id": user.user_id, "role": user.role, "department": user.department},
        "hits": hits,
    }
    if not hits:
        payload["message"] = (
            "Không tìm thấy tài liệu phù hợp trong phạm vi truy cập của bạn."
        )
    if synthesize and hits:
        from synthesis import synthesize as _synth  # local import

        answer = _synth(text, hits, _synthesis_chat_fn())
        payload["answer"] = answer
    audit.append_event({
        "type": "query", "user_id": user.user_id, "role": user.role,
        "department": user.department, "query": text,
        "returned_doc_ids": sorted({h["doc_id"] for h in hits}),
        "blocked_doc_ids": sorted({h["doc_id"] for h in blocked}),
    })
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_whoami(user_id: str, users_path: str | None) -> int:
    user = _resolve_user(user_id, users_path)
    print(json.dumps({
        "user_id": user.user_id, "full_name": user.full_name, "role": user.role,
        "department": user.department,
        "accessible_classifications": sorted(acl.accessible_classifications(user)),
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_can_access(user_id: str, doc_id: str, users_path: str | None, samples: str) -> int:
    user = _resolve_user(user_id, users_path)
    meta = load_doc_meta(samples)
    if doc_id not in meta:
        print(json.dumps({"error": f"unknown doc_id: {doc_id}"}, indent=2))
        return 1
    decision = acl.can_access(user, meta[doc_id])
    print(json.dumps({
        "user_id": user.user_id, "role": user.role, "department": user.department,
        "doc_id": doc_id, "classification": meta[doc_id]["classification"],
        "department_of_doc": meta[doc_id]["department"],
        "allowed": decision.allowed, "reason": decision.reason,
    }, indent=2, ensure_ascii=False))
    audit.append_event({
        "type": "can_access", "user_id": user.user_id, "doc_id": doc_id,
        "permission_decision": "allow" if decision.allowed else "deny",
    })
    return 0


def _cmd_list() -> int:
    print(json.dumps(_build_store().list_indexed(), indent=2, ensure_ascii=False))
    return 0


def _cmd_reset() -> int:
    _build_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0


def _cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="knowledge", description="Enterprise Knowledge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check embeddings + synthesis + Qdrant reachability.")

    p_ingest = sub.add_parser("ingest", help="Parse + chunk + index sample_documents/.")
    p_ingest.add_argument("--samples", default=None)

    p_query = sub.add_parser("query", help="Permission-aware retrieval for a question.")
    p_query.add_argument("text")
    p_query.add_argument("--user", required=True, help="Querying user_id (RBAC scope).")
    p_query.add_argument("--k", type=int, default=5)
    p_query.add_argument("--department", default=None,
                         help="Narrow within accessible scope (canonical id).")
    p_query.add_argument("--synthesize", action="store_true")
    p_query.add_argument("--users", default=None, help="Path to users.csv override.")

    p_who = sub.add_parser("whoami", help="Show a user's resolved access identity.")
    p_who.add_argument("user_id")
    p_who.add_argument("--users", default=None)

    p_can = sub.add_parser("can-access", help="Allow/Deny + reason for a user × document.")
    p_can.add_argument("user_id")
    p_can.add_argument("doc_id")
    p_can.add_argument("--users", default=None)
    p_can.add_argument("--samples", default=None)

    sub.add_parser("list", help="Show index stats.")
    sub.add_parser("reset", help="Delete the index collection.")
    p_audit = sub.add_parser("audit", help="Show recent audit events.")
    p_audit.add_argument("--limit", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    if args.command == "health":
        return _cmd_health()
    if args.command == "ingest":
        return _cmd_ingest(args.samples or _samples_dir())
    if args.command == "query":
        return _cmd_query(args.text, args.user, args.k, args.department,
                          args.synthesize, args.users)
    if args.command == "whoami":
        return _cmd_whoami(args.user_id, args.users)
    if args.command == "can-access":
        return _cmd_can_access(args.user_id, args.doc_id, args.users,
                               args.samples or _samples_dir())
    if args.command == "list":
        return _cmd_list()
    if args.command == "reset":
        return _cmd_reset()
    if args.command == "audit":
        return _cmd_audit(args.limit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/scripts/knowledge.py tests/test_enterprise_knowledge_cli.py
git commit -m "$(printf 'feat(enterprise_knowledge): permission-aware CLI orchestrator\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 13: Corpus converter (tools/build_corpus.py)

**Files:**
- Create: `modules/enterprise_knowledge/tools/build_corpus.py`
- Test: `tests/test_enterprise_knowledge_build_corpus.py`

**Interfaces:**
- Produces: `build_department_map(dept_rows) -> dict[str, str]` (label → canonical id, keyed by department_en, department_id, department_vi); `canonical_department(label, dept_map) -> str`; `convert(xlsx_path, out_dir) -> dict` (writes `sample_documents/*.md` + `access/{users,roles,permissions}.csv`, returns counts). CLI: `python build_corpus.py --xlsx PATH [--out DIR]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enterprise_knowledge_build_corpus.py
"""Converter tests: build a tiny in-memory workbook and assert materialized files."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOL = (
    Path(__file__).resolve().parent.parent
    / "modules" / "enterprise_knowledge" / "tools" / "build_corpus.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ek_build_corpus_uut", _TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_build_corpus_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_workbook(path):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dep = wb.create_sheet("Departments")
    dep.append(["Departments"])
    dep.append(["department_id", "department_en", "department_vi", "knowledge_space"])
    dep.append(["HR", "Human Resources", "Nhân sự", "Department Knowledge"])
    dep.append(["COMP", "Company", "Công ty", "Company Knowledge"])
    docs = wb.create_sheet("Documents")
    docs.append(["Enterprise Documents"])
    docs.append([])
    docs.append(["document_id", "title", "department", "classification", "content_vi"])
    docs.append(["DOC007", "Khung lương", "HR", "Confidential", "# Khung lương\nNội dung."])
    meta = wb.create_sheet("Document_Metadata")
    meta.append(["Document Metadata"])
    meta.append([])
    meta.append(["document_id", "title", "department", "classification", "owner",
                 "allowed_access", "last_updated", "tags", "language", "word_count"])
    meta.append(["DOC007", "Khung lương", "HR", "Confidential", "HR",
                 "Own Department", "2025-08-22", "khung, hr", "vi", 100])
    users = wb.create_sheet("Users")
    users.append(["Synthetic Users"])
    users.append([])
    users.append(["user_id", "full_name", "department", "role", "email", "status"])
    users.append(["U001", "Nguyễn Văn An", "Human Resources", "Employee",
                  "u1@synthetic.local", "Active"])
    for name in ("Roles", "Permissions"):
        s = wb.create_sheet(name)
        s.append([name])
        s.append(["col"])
    wb.save(path)


def test_convert_materializes_and_canonicalizes(tmp_path):
    mod = _load()
    xlsx = tmp_path / "ds.xlsx"
    _make_workbook(str(xlsx))
    out = tmp_path / "module"
    counts = mod.convert(str(xlsx), str(out))
    assert counts["documents"] == 1
    # Document front-matter uses canonical department_id HR (already canonical).
    doc_md = (out / "sample_documents" / "DOC007.md").read_text(encoding="utf-8")
    assert "department: HR" in doc_md
    assert "classification: Confidential" in doc_md
    # Users' "Human Resources" is canonicalized to HR.
    users_csv = (out / "access" / "users.csv").read_text(encoding="utf-8")
    assert "U001,Nguyễn Văn An,HR,Employee" in users_csv


def test_canonical_department_maps_hr_alias():
    mod = _load()
    dmap = mod.build_department_map([
        {"department_id": "HR", "department_en": "Human Resources", "department_vi": "Nhân sự"},
    ])
    assert mod.canonical_department("Human Resources", dmap) == "HR"
    assert mod.canonical_department("HR", dmap) == "HR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_build_corpus.py -v`
Expected: FAIL (build_corpus.py missing).

- [ ] **Step 3: Create `tools/build_corpus.py`**

```python
#!/usr/bin/env python
"""One-time converter: dataset .xlsx → module file corpus + access data.

Reads the AI Workspace dataset workbook and writes:
  - ``sample_documents/<doc_id>.md`` — front-matter (canonical department_id +
    classification + owner + knowledge_space) followed by the Vietnamese body.
  - ``access/users.csv`` — users with department normalized to department_id.
  - ``access/roles.csv`` and ``access/permissions.csv`` — reference copies.

Department labels differ across sheets (e.g. Documents "HR" vs Users
"Human Resources"); everything is canonicalized to the ``department_id`` from
the Departments sheet so ACL comparisons are exact.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _header_index(rows: list[list], first_col: str) -> int:
    for i, r in enumerate(rows):
        if r and str(r[0]).strip() == first_col:
            return i
    raise ValueError(f"header row starting with {first_col!r} not found")


def _dicts(rows: list[list], header_i: int) -> list[dict]:
    header = [str(c).strip() if c is not None else "" for c in rows[header_i]]
    out: list[dict] = []
    for r in rows[header_i + 1:]:
        if not r or all(c is None for c in r):
            continue
        out.append({header[j]: (r[j] if j < len(r) else None) for j in range(len(header))})
    return out


def build_department_map(dept_rows: list[dict]) -> dict[str, str]:
    """Map every known department label (en/id/vi) to its canonical department_id."""
    dmap: dict[str, str] = {}
    for row in dept_rows:
        dept_id = str(row["department_id"]).strip()
        for key in ("department_id", "department_en", "department_vi"):
            val = row.get(key)
            if val:
                dmap[str(val).strip()] = dept_id
    return dmap


def canonical_department(label: str, dept_map: dict[str, str]) -> str:
    """Return the canonical department_id for a raw label, or the label itself."""
    return dept_map.get(str(label).strip(), str(label).strip())


_KNOWLEDGE_SPACE = {"COMP": "Company Knowledge", "EXEC": "Executive Knowledge"}


def _knowledge_space(dept_id: str) -> str:
    return _KNOWLEDGE_SPACE.get(dept_id, "Department Knowledge")


def _write_document(out_docs: Path, doc: dict, meta: dict, dept_map: dict[str, str]) -> None:
    dept_id = canonical_department(doc["department"], dept_map)
    front = {
        "doc_id": doc["document_id"],
        "title": doc["title"],
        "department": dept_id,
        "classification": doc["classification"],
        "owner": canonical_department(meta.get("owner", doc["department"]), dept_map),
        "knowledge_space": _knowledge_space(dept_id),
        "last_updated": str(meta.get("last_updated", "")),
        "language": str(meta.get("language", "vi")),
    }
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in front.items()]
    lines += ["---", str(doc["content_vi"] or "").strip(), ""]
    (out_docs / f"{doc['document_id']}.md").write_text("\n".join(lines), encoding="utf-8")


def convert(xlsx_path: str, out_dir: str) -> dict:
    """Materialize the workbook into ``out_dir``. Returns counts."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    dept_rows = _dicts((r := _rows(wb["Departments"])), _header_index(r, "department_id"))
    dept_map = build_department_map(dept_rows)

    doc_rows = _dicts((r := _rows(wb["Documents"])), _header_index(r, "document_id"))
    meta_rows = _dicts((r := _rows(wb["Document_Metadata"])), _header_index(r, "document_id"))
    meta_by_id = {m["document_id"]: m for m in meta_rows}

    out = Path(out_dir)
    out_docs = out / "sample_documents"
    out_access = out / "access"
    out_docs.mkdir(parents=True, exist_ok=True)
    out_access.mkdir(parents=True, exist_ok=True)

    for doc in doc_rows:
        _write_document(out_docs, doc, meta_by_id.get(doc["document_id"], {}), dept_map)

    user_rows = _dicts((r := _rows(wb["Users"])), _header_index(r, "user_id"))
    with open(out_access / "users.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "full_name", "department", "role", "email", "status"])
        for u in user_rows:
            w.writerow([
                u["user_id"], u.get("full_name", ""),
                canonical_department(u["department"], dept_map),
                u["role"], u.get("email", ""), u.get("status", "Active"),
            ])

    _dump_reference(wb, "Roles", out_access / "roles.csv")
    _dump_reference(wb, "Permissions", out_access / "permissions.csv")

    return {"documents": len(doc_rows), "users": len(user_rows)}


def _dump_reference(wb, sheet: str, path: Path) -> None:
    """Write a sheet's non-empty rows verbatim as a reference CSV."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for r in wb[sheet].iter_rows(values_only=True):
            cells = [c for c in r if c is not None]
            if cells:
                w.writerow(list(r))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_corpus", description="xlsx → module corpus")
    parser.add_argument("--xlsx", required=True, help="Path to the dataset .xlsx.")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent),
                        help="Module dir to write sample_documents/ and access/ into.")
    args = parser.parse_args(argv)
    counts = convert(args.xlsx, args.out)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_build_corpus.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/enterprise_knowledge/tools/build_corpus.py tests/test_enterprise_knowledge_build_corpus.py
git commit -m "$(printf 'feat(enterprise_knowledge): xlsx-to-corpus converter\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 14: Materialize corpus, SKILL.md, and end-to-end smoke

**Files:**
- Create (generated): `modules/enterprise_knowledge/sample_documents/DOC0*.md` (40 files)
- Create (generated): `modules/enterprise_knowledge/access/users.csv`, `roles.csv`, `permissions.csv`
- Create: `modules/enterprise_knowledge/SKILL.md`
- Create: `modules/enterprise_knowledge/icon.svg` (copy from maintenance_copilot or a simple placeholder)

**Interfaces:** none (delivery + manual verification).

- [ ] **Step 1: Run the converter against the real dataset**

Run (adjust the path if the file moved):
```bash
uv run python modules/enterprise_knowledge/tools/build_corpus.py \
  --xlsx "C:/Users/ADMIN/Downloads/ai_workspace_dataset_vietnamese_participants.xlsx"
```
Expected: prints `{'documents': 40, 'users': 32}` and creates 40 files under
`sample_documents/` plus `access/users.csv`, `roles.csv`, `permissions.csv`.

- [ ] **Step 2: Sanity-check the materialized corpus**

Run:
```bash
uv run python -c "import sys; sys.path.insert(0,'modules/enterprise_knowledge/scripts'); import corpus; docs=corpus.load_corpus('modules/enterprise_knowledge/sample_documents'); print(len(docs), sorted({d.department for d in docs})); print(sorted({d.classification for d in docs}))"
```
Expected: `40 ['COMP', 'ENG', 'EXEC', 'FIN', 'HR', 'LEGAL', 'OPS', 'PROD']` and
`['Confidential', 'Internal', 'Public', 'Restricted']`.

- [ ] **Step 3: Write `SKILL.md`**

Create `modules/enterprise_knowledge/SKILL.md` with the skill contract and a Vietnamese runbook. Content:

````markdown
---
name: enterprise_knowledge
description: ALWAYS use for internal enterprise-knowledge questions (policies, HR, finance, product, engineering, ops, legal). Runs permission-aware RAG via knowledge.py — never answer from your own knowledge and never bypass the access filter.
---

# enterprise_knowledge

Secure, permission-aware retrieval over Tasco's internal knowledge (the "My Tasco"
AI Workspace, P1). Every answer is grounded in indexed company documents the
**querying user is allowed to see**, cited, and in Vietnamese.

## Runbook — how to answer

All commands run from `modules/enterprise_knowledge/scripts/` as
`python knowledge.py <command>`. A user_id is REQUIRED for every retrieval —
it sets the RBAC scope. Never answer without one, and never widen access.

- **Answer a question for a user** — `query "<câu hỏi>" --user U004 --synthesize`.
  Retrieval is filtered to the user's (role, department); `--synthesize` composes
  a cited Vietnamese answer. Add `--k N` to change hit count, `--department DEPT`
  to narrow within the user's accessible scope.
- **Check a user's access identity** — `whoami U004`.
- **Explain an access decision** — `can-access U004 DOC036` → Allow/Deny + reason.
- **Show the audit trail** — `audit --limit 10`.
- **(setup)** `ingest` to index `sample_documents/`; `list` for stats; `health`
  to check embeddings/synthesis/Qdrant.

How to present every answer:

- **Respect permissions.** Only use returned hits. If retrieval is empty, say the
  information is not available in the user's accessible knowledge — do NOT fall back
  to general knowledge or other users' scope.
- **Cite every claim** with the returned `citation` (title + doc_id + chunk).
- **Surface uncertainty.** If `needs_review` is set or confidence is low, say so and
  recommend checking the source document.
- Answer in Vietnamese; keep the advisory note from the tool output.

## Access model

Public/Internal → all employees. Confidential → the owning department only
(Executives see all). Restricted → Executives only. Enforcement is a
pre-retrieval Qdrant filter plus a citation-time re-check.

## Status

Core module — ingest, permission-aware search, grounded Vietnamese answers, and
audit trail. Evaluation harness, README, and demo are later phases.
````

- [ ] **Step 4: Provide an icon**

Copy the maintenance_copilot icon as a placeholder:
```bash
cp modules/maintenance_copilot/icon.svg modules/enterprise_knowledge/icon.svg
```

- [ ] **Step 5: Full unit-test sweep**

Run: `uv run --extra dev pytest tests/test_enterprise_knowledge_*.py -v`
Expected: all green (config, client, budget, corpus, chunking, identity, acl, index_store, guardrails, synthesis, audit, cli, build_corpus).

- [ ] **Step 6: Real end-to-end simulation (per CLAUDE.md testing rule)**

Requires `OPENAI_API_KEY` set and a Qdrant reachable at `EK_QDRANT_URL`
(reuse the compose sidecar: `docker compose up -d qdrant`).
```bash
export OPENAI_API_KEY="<your key>"
cd modules/enterprise_knowledge/scripts
uv run python knowledge.py health
uv run python knowledge.py ingest
# Deny case (Engineering employee → HR salary bands):
uv run python knowledge.py query "Khung lương Product Manager là bao nhiêu?" --user U004 --synthesize
# Allow case (HR employee → same doc):
uv run python knowledge.py query "Khung lương Product Manager là bao nhiêu?" --user U001 --synthesize
# Explicit permission check:
uv run python knowledge.py can-access U004 DOC036
uv run python knowledge.py whoami U007
```
Expected: `health` all ok; `ingest` reports 40 documents; the U004 salary query
returns no HR-confidential hit (permission-respecting message or unrelated allowed
hits), the U001 query returns DOC007 with a cited Vietnamese answer; `can-access
U004 DOC036` → `"allowed": false`; `whoami U007` shows all four classifications.

- [ ] **Step 7: Commit**

```bash
git add -f modules/enterprise_knowledge/sample_documents modules/enterprise_knowledge/access
git add modules/enterprise_knowledge/SKILL.md modules/enterprise_knowledge/icon.svg
git commit -m "$(printf 'feat(enterprise_knowledge): materialized VN corpus + skill contract\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

*(Note: `sample_documents/` and `access/` are under the module dir; only `data/`
is gitignored, so a plain `git add` should work — `-f` is a harmless safeguard.)*

---

## Self-Review

**Spec coverage:**
- Materialize to files → Task 13 (converter) + Task 14 (run it). ✓
- Drop Neo4j KG → no extraction/graph tasks; `health` probes only embed/synth/qdrant. ✓
- Access-control layer (identity + acl) → Tasks 6, 7. ✓
- Pre-retrieval filter + synthesis guard → Task 8 (filter) + Task 12 (`guard_accessible`). ✓
- Department canonicalization (HR ↔ Human Resources) → Task 13 (`canonical_department`, tested). ✓
- Vietnamese grounded answers + guardrails → Tasks 9, 10. ✓
- Hosted-API backend defaults → Task 1 (config). ✓
- Audit trail with user + decision → Task 11 (store) + Task 12 (callers add user fields). ✓
- CLI: health/ingest/query/whoami/can-access/list/reset/audit → Task 12. ✓
- Unit tests incl. dataset Deny/Allow cases → Task 7 (parametrized) + Task 8. ✓
- Deferred (eval harness, README, demo, compose changes) → intentionally absent. ✓

**Placeholder scan:** No "TBD"/"add error handling"/"similar to". Clone tasks (2, 3, 9, 10, 11) name the exact source file and list every edit. ✓

**Type consistency:** `User(user_id, full_name, role, department, status)` used identically in identity/acl/index_store/cli tests. `ChunkRecord` fields match between chunking (Task 5) and index_store test (Task 8). Hit dict keys (`doc_id, chunk_id, text, classification, department, citation, ...`) consistent across index_store, synthesis, guard_accessible. `build_filter`/`can_access`/`accessible_classifications` signatures match between acl (Task 7) and knowledge.py (Task 12). ✓
```
