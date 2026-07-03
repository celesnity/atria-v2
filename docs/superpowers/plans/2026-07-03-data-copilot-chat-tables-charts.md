# data_copilot — conversation-scoped storage + live tables & charts in chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move data_copilot's per-run artifacts, ingested data, and audit trail into a per-session folder; let the agent push a result DataFrame to chat as an interactive (chart.js) table + chart; and rebind the editable table's save-back to the session folder.

**Architecture:** A new `paths.py` in the module resolves a session-keyed root from env (`ATRIA_WORKSPACE`/`ATRIA_SESSION_DIR` + `ATRIA_CONVERSATION_ID`), with a module-dir fallback for the bare CLI. `analyze` writes `result.csv` + `result.meta.json` (columns + auto-detected chart suggestions) into the run dir. A new read-only `send_table` tool emits the existing `data_message` payload (columns/rows/suggestions, `editable:false`); atria's already-present-but-orphaned chart.js components (`ChartView`/`EditPanel`/`charts` store) get wired into `DataMessage.tsx` so suggestions render as an interactive chart. The editable table is rebound to the session folder via a new `/api/data-copilot/{read,write}` route. Storage is keyed by `session_id` (available to scripts, tools, and route with no DB lookup).

**Tech Stack:** Python 3 (module scripts), FastAPI (`atria/web`), pytest, React 18 + TypeScript + Zustand + chart.js/react-chartjs-2 (`web-ui`), Vitest.

## Global Constraints

- Line length: 100 chars (Black + Ruff). Type hints on public APIs (mypy strict). Google-style docstrings.
- No table format in any prompt/SKILL text — use prose/bullets.
- Never hard-code if/else branching to drive LLM conversation flow.
- Storage key = `session_id`. Root = `<ATRIA_WORKSPACE or ATRIA_SESSION_DIR>/.artifacts/data_copilot/<ATRIA_CONVERSATION_ID>/`; env `ATRIA_CONVERSATION_ID` carries the session id. Module-dir fallback when env is unset.
- Server-side root mirror: `data_copilot_root(session_id, working_dir)` = `Path(working_dir)/".artifacts"/"data_copilot"/str(session_id)`.
- Data caps reused from `store`: `_MAX_DATA_ROWS=50000`, `_MAX_DATA_COLS=200`, `_MAX_DATA_BYTES=50MB`.
- Testing per CLAUDE.md: unit tests via `uv run pytest` AND a real end-to-end run with `OPENAI_API_KEY` set. Both are required.
- New tools must be added in four places: schema (`web_tools.py`), handler impl, `registry.py` (import + `_handlers` map + normal allow-list), and `ws_tool_broadcaster.py`. Frontend-facing tools also need the `normal_builder.py` allow-list.

---

## File Structure

Module (Python, `modules/data_copilot/scripts/`):
- Create `paths.py` — session-keyed root + `data_dir()`/`runs_dir()`/`new_run_dir()`/`audit_path()`.
- Create `charts.py` — `detect_suggestions(columns, rows)` chart-detection.
- Modify `ingest.py` — resolve `data_dir()` from `paths`.
- Modify `audit.py` — default to `paths.audit_path()`.
- Modify `copilot.py` — `_default_out_dir()` → `paths.new_run_dir()`; `analyze` writes `result.csv`/`result.meta.json`, summary gains `result_table`/`suggestions`.
- Modify `generate.py` — instruct generated code to also write `result.csv` to its cwd.
- Modify `SKILL.md` — runbook update.

Backend (Python, `atria/`):
- Create `atria/core/modules/data_copilot_paths.py` — `data_copilot_root()`, `read_session_csv()`, `write_session_csv()`.
- Create `atria/core/context_engineering/tools/implementations/send_table_tool.py` — `SendTableHandler`.
- Create `atria/web/routes/data_copilot.py` — `/api/data-copilot/{read,write}`.
- Modify `atria/core/agents/components/schemas/builtin/web_tools.py` — `send_table` schema.
- Modify `atria/core/context_engineering/tools/registry.py` — register `send_table`.
- Modify `atria/web/ws_tool_broadcaster.py` — add `send_table` to broadcast set.
- Modify `atria/core/agents/components/schemas/normal_builder.py` — allow `send_table`.
- Modify `atria/core/context_engineering/tools/implementations/send_editable_table_tool.py` — session-scoped source.
- Modify `atria/web/*` route registration to include the new router.

Frontend (`web-ui/src/`):
- Modify `components/Chat/DataMessage/DataMessage.tsx` — render `ChartView`/switcher/`EditPanel` when `data_suggestions` present; route editable save/reload by `source.session`.
- Modify `components/Chat/DataMessage/EditableDataTable.tsx` — session-aware save/reload.
- Modify `api/client.ts` — `readSessionDataset`/`writeSessionDataset`.
- Modify `types/index.ts` — `data_source` gains optional `session`.

---

## Task 1: `paths.py` — session-keyed storage root

**Files:**
- Create: `modules/data_copilot/scripts/paths.py`
- Test: `tests/test_data_copilot_paths.py`

**Interfaces:**
- Produces: `conversation_root() -> Path`, `data_dir() -> Path`, `runs_dir() -> Path`, `new_run_dir(name: str = "latest") -> Path`, `audit_path() -> Path`. All create parent dirs on access except `conversation_root`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_paths.py
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "dc_paths",
    Path(__file__).resolve().parent.parent
    / "modules" / "data_copilot" / "scripts" / "paths.py",
)
paths = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(paths)  # type: ignore[union-attr]


def test_session_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ATRIA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "abcd1234")
    monkeypatch.delenv("ATRIA_SESSION_DIR", raising=False)
    root = paths.conversation_root()
    assert root == tmp_path / ".artifacts" / "data_copilot" / "abcd1234"
    assert paths.data_dir() == root / "data"
    assert paths.runs_dir() == root / "runs"
    assert paths.audit_path() == root / "audit.jsonl"
    # helpers create dirs
    assert paths.data_dir().is_dir()
    run = paths.new_run_dir()
    assert run == root / "runs" / "latest" and run.is_dir()


def test_fallback_to_module_dir_when_env_missing(monkeypatch):
    monkeypatch.delenv("ATRIA_WORKSPACE", raising=False)
    monkeypatch.delenv("ATRIA_SESSION_DIR", raising=False)
    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)
    module_dir = Path(paths.__file__).resolve().parent.parent
    assert paths.conversation_root() == module_dir
    assert paths.data_dir() == module_dir / "data"
    assert paths.audit_path() == module_dir / "audit_log.jsonl"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_paths.py -v`
Expected: FAIL — `paths.py` does not exist (import error).

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/paths.py
"""Resolve where data_copilot writes its artifacts.

Keyed by the atria session id so the bash-invoked scripts, the agent-side
tools, and the save route all resolve the *same* directory with no DB lookup.
Falls back to the module dir for the bare CLI/TUI (no session in env).
"""

from __future__ import annotations

import os
from pathlib import Path


def _module_dir() -> Path:
    """The module root (``modules/data_copilot``) — the standalone fallback."""
    return Path(__file__).resolve().parent.parent


def conversation_root() -> Path:
    """Session-keyed artifact root, or the module dir when no session in env."""
    workspace = os.environ.get("ATRIA_WORKSPACE") or os.environ.get("ATRIA_SESSION_DIR")
    session = os.environ.get("ATRIA_CONVERSATION_ID")
    if workspace and session:
        return Path(workspace) / ".artifacts" / "data_copilot" / session
    return _module_dir()


def _in_module_fallback() -> bool:
    return conversation_root() == _module_dir()


def data_dir() -> Path:
    """Dir for ingested + derived CSVs (created on access)."""
    d = conversation_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runs_dir() -> Path:
    """Dir holding per-run output subdirs (created on access)."""
    d = conversation_root() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_run_dir(name: str = "latest") -> Path:
    """Create and return a run output dir under ``runs/``."""
    d = runs_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def audit_path() -> Path:
    """Audit log path — ``audit.jsonl`` in a session, legacy name in fallback."""
    if _in_module_fallback():
        return _module_dir() / "audit_log.jsonl"
    return conversation_root() / "audit.jsonl"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_paths.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/paths.py tests/test_data_copilot_paths.py
git commit -m "feat(data_copilot): session-keyed artifact paths"
```

---

## Task 2: Route `ingest`/`resolve_dataset`/`list_datasets` through `paths`

**Files:**
- Modify: `modules/data_copilot/scripts/ingest.py`
- Test: `tests/test_data_copilot_ingest.py` (add cases; keep existing passing)

**Interfaces:**
- Consumes: `paths.data_dir()` (Task 1).
- Produces: unchanged public signatures `ingest`, `resolve_dataset`, `list_datasets`; storage now under `paths.data_dir()` when a session is in env.

The current code writes via `store.write_data_files(modules_root, module_name, pairs)` into `<module>/data/`. When a session root is active we must write into `paths.data_dir()` instead. Simplest correct approach: write CSV bytes directly to `paths.data_dir()` and keep the store path only for the module fallback.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_ingest.py  (append)
import importlib.util
from pathlib import Path

def _load_ingest():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    spec = importlib.util.spec_from_file_location("dc_ingest_env", base / "ingest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

def test_ingest_writes_into_session_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ATRIA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "sess9999")
    src = tmp_path / "sales data.csv"
    src.write_text("region,rev\nNorth,10\nSouth,20\n", encoding="utf-8")
    ing = _load_ingest()
    result = ing.ingest(str(src))
    stored = tmp_path / ".artifacts" / "data_copilot" / "sess9999" / "data" / "sales-data.csv"
    assert stored.is_file()
    assert result["files"][0]["path"] == str(stored)
    assert result["files"][0]["file"] == "sales-data.csv"
    # resolve_dataset finds it by short name
    assert ing.resolve_dataset("sales-data") == str(stored.resolve())
    names = [e["file"] for e in ing.list_datasets()]
    assert "sales-data.csv" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_ingest.py::test_ingest_writes_into_session_data_dir -v`
Expected: FAIL — file written under `<module>/data/`, not the session dir.

- [ ] **Step 3: Write minimal implementation**

Add `import paths` alongside the other module-local imports at the top of `ingest.py` (the module dir is on `sys.path` via `copilot.py`; for direct import in tests it is loaded by path). Add a resolver and switch the write/lookup dirs:

```python
# ingest.py — add near the top, after existing imports
try:
    import paths  # type: ignore[import-not-found]
except ModuleNotFoundError:  # loaded by path (tests) — import the sibling file
    import importlib.util as _ilu

    _p = Path(__file__).resolve().parent / "paths.py"
    _spec = _ilu.spec_from_file_location("dc_paths", _p)
    paths = _ilu.module_from_spec(_spec)  # type: ignore[assignment]
    _spec.loader.exec_module(paths)  # type: ignore[union-attr]


def _target_data_dir() -> Path:
    """The active data dir: session-scoped when in env, else the module's."""
    return paths.data_dir()
```

In `ingest(...)`, replace the store write with a direct write into the active data dir:

```python
    base = _slug(name or src.stem)
    pairs = to_csv_files(src, base)

    data_dir = _target_data_dir()
    files = []
    for filename, content in pairs:
        dest = data_dir / filename
        dest.write_bytes(content)
        files.append({"file": filename, "path": str(dest.resolve())})
    return {"module": module_name, "files": files}
```

In `resolve_dataset(...)`, replace `data_dir` computation:

```python
    data_dir = _target_data_dir()
```

(remove the `modules_root = root or _module_root()` line in that function and the `modules_root` arg use; keep the signature but ignore `root` for lookup).

In `list_datasets(...)`, replace:

```python
    data_dir = _target_data_dir()
    if not data_dir.is_dir():
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_ingest.py -v`
Expected: PASS — new test passes; pre-existing ingest tests still pass (they set no session env, so they hit the module-dir fallback exactly as before).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/ingest.py tests/test_data_copilot_ingest.py
git commit -m "feat(data_copilot): ingest/resolve/list use session data dir"
```

---

## Task 3: Audit trail defaults to the session `audit.jsonl`

**Files:**
- Modify: `modules/data_copilot/scripts/audit.py`
- Test: `tests/test_data_copilot_audit.py`

**Interfaces:**
- Consumes: `paths.audit_path()` (Task 1).
- Produces: `audit_path()` now returns `DC_AUDIT_PATH` override → else `paths.audit_path()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_audit.py
import importlib.util
from pathlib import Path

def _load(name, rel):
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    spec = importlib.util.spec_from_file_location(name, base / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

def test_audit_writes_to_session_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ATRIA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "sessAAAA")
    monkeypatch.delenv("DC_AUDIT_PATH", raising=False)
    audit = _load("dc_audit", "audit.py")
    audit.append_event({"type": "analyze", "verified": True})
    expected = tmp_path / ".artifacts" / "data_copilot" / "sessAAAA" / "audit.jsonl"
    assert expected.is_file()
    events = audit.read_events()
    assert events and events[-1]["type"] == "analyze"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_audit.py -v`
Expected: FAIL — audit written to `<module>/audit_log.jsonl`.

- [ ] **Step 3: Write minimal implementation**

Add the same `paths` import shim as Task 2 to `audit.py`, then change `audit_path()`:

```python
def audit_path() -> Path:
    """Return the audit log path (``DC_AUDIT_PATH`` override or session default)."""
    override = os.environ.get("DC_AUDIT_PATH")
    if override:
        return Path(override)
    return paths.audit_path()
```

Also change `append_event` to `path.parent.mkdir(parents=True, exist_ok=True)` (already present) — no change needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_audit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/audit.py tests/test_data_copilot_audit.py
git commit -m "feat(data_copilot): audit trail defaults to session dir"
```

---

## Task 4: chart-detection — `detect_suggestions`

**Files:**
- Create: `modules/data_copilot/scripts/charts.py`
- Test: `tests/test_data_copilot_charts.py`

**Interfaces:**
- Produces: `detect_suggestions(columns: list[dict], rows: list[dict], max_suggestions: int = 3) -> list[dict]`, each `{"chart_type", "x", "y": [...], "title"}` with `chart_type ∈ {bar,line,area,pie,doughnut,scatter}`. Pure heuristic (no LLM) so it is deterministic and free. `columns` are `[{"name","type"}]` where `type ∈ {number,string,date,bool}`.

Heuristic: pick the first non-number column as `x`; number columns as `y`. If exactly one number column and ≤ 8 rows → also offer `pie`. If `x` looks temporal (name matches date/month/year/time) → prefer `line`. Always offer `bar` first. Cap at `max_suggestions`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_charts.py
import importlib.util
from pathlib import Path

def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    spec = importlib.util.spec_from_file_location("dc_charts", base / "charts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

def test_bar_for_category_plus_number():
    charts = _load()
    cols = [{"name": "region", "type": "string"}, {"name": "revenue", "type": "number"}]
    rows = [{"region": "N", "revenue": 10}, {"region": "S", "revenue": 20}]
    sug = charts.detect_suggestions(cols, rows)
    assert sug[0]["chart_type"] == "bar"
    assert sug[0]["x"] == "region" and sug[0]["y"] == ["revenue"]
    # small single-metric set also offers pie
    assert any(s["chart_type"] == "pie" for s in sug)

def test_line_for_temporal_x():
    charts = _load()
    cols = [{"name": "month", "type": "string"}, {"name": "sales", "type": "number"}]
    rows = [{"month": "Jan", "sales": 1}, {"month": "Feb", "sales": 2}]
    sug = charts.detect_suggestions(cols, rows)
    assert sug[0]["chart_type"] == "line"

def test_empty_when_no_numeric():
    charts = _load()
    cols = [{"name": "a", "type": "string"}, {"name": "b", "type": "string"}]
    assert charts.detect_suggestions(cols, [{"a": "x", "b": "y"}]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_charts.py -v`
Expected: FAIL — `charts.py` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/charts.py
"""Heuristic chart-type detection for a result table.

Produces chart ``suggestions`` in the shape the atria web ``data_message``
payload consumes (``ChartSuggestion``: chart_type, x, y[], title). Deterministic
and LLM-free so it is cheap and reproducible.
"""

from __future__ import annotations

import re
from typing import Dict, List

_TEMPORAL = re.compile(r"(date|time|month|year|day|week|quarter|thang|nam)", re.IGNORECASE)


def detect_suggestions(
    columns: List[dict], rows: List[dict], max_suggestions: int = 3
) -> List[Dict[str, object]]:
    """Return up to *max_suggestions* chart specs for the given result table."""
    names = [c["name"] for c in columns]
    numeric = [c["name"] for c in columns if c.get("type") == "number"]
    non_numeric = [n for n in names if n not in numeric]
    if not numeric or not non_numeric:
        return []

    x = non_numeric[0]
    y = numeric
    is_temporal = bool(_TEMPORAL.search(x))
    title = f"{y[0]} by {x}" if len(y) == 1 else f"{', '.join(y)} by {x}"

    suggestions: List[Dict[str, object]] = []
    primary = "line" if is_temporal else "bar"
    suggestions.append({"chart_type": primary, "x": x, "y": list(y), "title": title})
    secondary = "bar" if is_temporal else "line"
    suggestions.append({"chart_type": secondary, "x": x, "y": list(y), "title": title})
    if len(y) == 1 and len(rows) <= 8:
        suggestions.append(
            {"chart_type": "pie", "x": x, "y": [y[0]], "title": title}
        )
    return suggestions[:max_suggestions]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_charts.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/charts.py tests/test_data_copilot_charts.py
git commit -m "feat(data_copilot): heuristic chart-suggestion detection"
```

---

## Task 5: `analyze` writes `result.csv`/`result.meta.json`, summary gains `result_table`/`suggestions`

**Files:**
- Modify: `modules/data_copilot/scripts/copilot.py` (`run_analysis`, `_default_out_dir`)
- Modify: `modules/data_copilot/scripts/generate.py` (instruct code to write `result.csv`)
- Test: `tests/test_data_copilot_analyze_result.py`

**Interfaces:**
- Consumes: `paths.new_run_dir()` (Task 1), `charts.detect_suggestions` (Task 4).
- Produces: `run_analysis(...)` summary dict adds `"result_table": str | None` (absolute path to `result.csv` when present) and `"suggestions": list[dict]`. A new helper `_load_result_table(out_dir) -> tuple[list[dict], list[dict]] | None` returning `(columns, rows)` read from `result.csv` if the generated code wrote one.

The generated code is instructed (Task 5, generate.py) to save its final result frame as `result.csv` in the cwd (which is `out_dir`). After the loop, `run_analysis` reads it, derives columns (typing numbers vs strings), computes suggestions, writes `result.meta.json`, and adds both to the summary.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_analyze_result.py
import importlib.util
import json
from pathlib import Path

def _load_copilot():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    import sys
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_copilot", base / "copilot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

def test_run_analysis_emits_result_table_and_suggestions(tmp_path):
    cop = _load_copilot()
    out = tmp_path / "run"
    out.mkdir()
    # simulate: an exec_fn that writes result.csv into out_dir and returns ok
    def fake_exec(code, out_dir, timeout, max_output):
        (Path(out_dir) / "result.csv").write_text(
            "region,revenue\nNorth,10\nSouth,20\n", encoding="utf-8"
        )
        return {"status": "ok", "stdout": "done", "stderr": "", "figures": [], "returncode": 0}
    summary = cop.run_analysis(
        dataset=str(tmp_path / "in.csv"),
        question="rev by region",
        out_dir=str(out),
        max_repair=0,
        max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "# report",
        profile_fn=lambda ds: {"columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    assert summary["result_table"] == str((out / "result.csv").resolve())
    assert summary["suggestions"] and summary["suggestions"][0]["x"] == "region"
    meta = json.loads((out / "result.meta.json").read_text())
    assert meta["columns"][1]["type"] == "number"
```

(Note: `in.csv` need not exist because `profile_fn` is stubbed and `dataset` is only `Path(...).resolve()`-d, not read.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_analyze_result.py -v`
Expected: FAIL — summary has no `result_table`/`suggestions` keys.

- [ ] **Step 3: Write minimal implementation**

Add imports + helper to `copilot.py`:

```python
import csv as _csv
import importlib.util as _ilu

def _load_sibling(mod_name: str):
    _p = Path(__file__).resolve().parent / f"{mod_name}.py"
    _spec = _ilu.spec_from_file_location(f"dc_{mod_name}", _p)
    _m = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_m)  # type: ignore[union-attr]
    return _m

import paths as _paths_mod  # type: ignore[import-not-found]  (on sys.path via copilot)
_charts_mod = None

def _charts():
    global _charts_mod
    if _charts_mod is None:
        try:
            import charts as _c  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            _c = _load_sibling("charts")
        _charts_mod = _c
    return _charts_mod


def _infer_type(values: list[str]) -> str:
    """number if every non-empty value parses as float, else string."""
    saw = False
    for v in values:
        if v is None or v == "":
            continue
        saw = True
        try:
            float(v)
        except (TypeError, ValueError):
            return "string"
    return "number" if saw else "string"


def _load_result_table(out_dir: str):
    """Read result.csv from *out_dir* → (columns, rows) or None if absent/empty."""
    path = Path(out_dir) / "result.csv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = list(_csv.reader(fh))
    if not reader:
        return None
    header = [h.strip() or f"column_{i+1}" for i, h in enumerate(reader[0])]
    body = reader[1:]
    rows = [
        {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
        for r in body
    ]
    columns = []
    for i, name in enumerate(header):
        col_vals = [r.get(name, "") for r in rows]
        columns.append({"name": name, "type": _infer_type(col_vals)})
    # coerce numeric cells to float so charts render numbers, not strings
    for col in columns:
        if col["type"] == "number":
            for r in rows:
                try:
                    r[col["name"]] = float(r[col["name"]])
                except (TypeError, ValueError):
                    r[col["name"]] = None
    return columns, rows
```

In `run_analysis`, after `report_md = report_fn(...)` and before `audit.append_event(...)`, compute the result table and suggestions:

```python
    result_table_path = None
    suggestions: list = []
    loaded = _load_result_table(out_dir)
    if loaded is not None:
        columns, rows = loaded
        suggestions = _charts().detect_suggestions(columns, rows)
        meta = {"columns": columns, "suggestions": suggestions}
        (Path(out_dir) / "result.meta.json").write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )
        result_table_path = str((Path(out_dir) / "result.csv").resolve())
```

Add both to the returned summary dict:

```python
        "result_table": result_table_path,
        "suggestions": suggestions,
```

Change `_default_out_dir`:

```python
def _default_out_dir() -> str:
    return str(_paths_mod.new_run_dir())
```

(Remove the old `Path(__file__)...parent.parent / "runs" / "latest"` body.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_analyze_result.py -v`
Expected: PASS.

- [ ] **Step 5: Instruct generated code to write `result.csv`**

In `generate.py`, add one instruction to the code-generation prompt (find the prompt string that lists output rules; append this bullet in prose, not a table):

```
- If your analysis produces a final tabular result (a pandas DataFrame that
  answers the question), also save it to 'result.csv' in the current directory
  with df.to_csv('result.csv', index=False). Keep it small (<= 50 rows); if the
  result is large, save the most relevant head/aggregate. This table is shown to
  the user as an interactive chart, so prefer tidy columns (one category column
  plus numeric measures).
```

- [ ] **Step 6: Run the full module test subset + commit**

Run: `uv run pytest tests/test_data_copilot_analyze_result.py tests/test_data_copilot_paths.py -v`
Expected: PASS.

```bash
git add modules/data_copilot/scripts/copilot.py modules/data_copilot/scripts/generate.py tests/test_data_copilot_analyze_result.py
git commit -m "feat(data_copilot): analyze emits result.csv + chart suggestions"
```

---

## Task 6: Server-side session-CSV helpers — `data_copilot_paths.py`

**Files:**
- Create: `atria/core/modules/data_copilot_paths.py`
- Test: `tests/test_data_copilot_server_paths.py`

**Interfaces:**
- Produces:
  - `data_copilot_root(session_id: str, working_dir: str) -> Path`
  - `read_session_csv(session_id: str, working_dir: str, rel_file: str) -> dict` → `{file, columns, rows, warning?}` (same shape as `store.read_dataset`). Accepts a `data/`-relative name OR an absolute path inside the root (for reading `result.csv` from a run dir).
  - `write_session_csv(session_id, working_dir, rel_file, columns, rows) -> dict` → `{written, rows, columns}`, confined to `data_copilot_root(...)/data/`.
- Consumes: reuses the CSV parse/serialize + caps by importing from `atria.core.modules.store` (`_MAX_DATA_ROWS`, `_MAX_DATA_COLS`, `_MAX_DATA_BYTES`, `_coerce_header`, `_decode_csv_bytes`, `_atomic_write_bytes`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_server_paths.py
from pathlib import Path
import pytest
from atria.core.modules import data_copilot_paths as dcp

def test_root_and_write_read_roundtrip(tmp_path):
    root = dcp.data_copilot_root("sess1", str(tmp_path))
    assert root == tmp_path / ".artifacts" / "data_copilot" / "sess1"
    out = dcp.write_session_csv(
        "sess1", str(tmp_path), "edited.csv",
        [{"name": "a"}, {"name": "b"}],
        [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}],
    )
    assert out["rows"] == 2
    read = dcp.read_session_csv("sess1", str(tmp_path), "edited.csv")
    assert [c["name"] for c in read["columns"]] == ["a", "b"]
    assert read["rows"][0]["a"] == "1"

def test_read_absolute_path_inside_root(tmp_path):
    root = dcp.data_copilot_root("sess2", str(tmp_path))
    run = root / "runs" / "latest"
    run.mkdir(parents=True)
    (run / "result.csv").write_text("k,v\nx,1\n", encoding="utf-8")
    read = dcp.read_session_csv("sess2", str(tmp_path), str(run / "result.csv"))
    assert read["rows"][0]["k"] == "x"

def test_rejects_path_outside_root(tmp_path):
    with pytest.raises(ValueError):
        dcp.read_session_csv("sess3", str(tmp_path), "../../etc/passwd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_server_paths.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# atria/core/modules/data_copilot_paths.py
"""Session-scoped CSV read/write for data_copilot, shared by the tools and the
``/api/data-copilot`` route. Path is keyed by the atria session id and confined
to ``<working_dir>/.artifacts/data_copilot/<session_id>/``.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List

from atria.core.modules import store


def data_copilot_root(session_id: str, working_dir: str) -> Path:
    """Absolute root for a session's data_copilot artifacts."""
    return Path(working_dir) / ".artifacts" / "data_copilot" / str(session_id)


def _resolve_confined(session_id: str, working_dir: str, rel_or_abs: str) -> Path:
    """Resolve a data/-relative name or absolute path, confined to the root."""
    root = data_copilot_root(session_id, working_dir).resolve()
    candidate = Path(rel_or_abs)
    if not candidate.is_absolute():
        candidate = root / "data" / rel_or_abs
    resolved = candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("path escapes the session data_copilot root")
    return resolved


def read_session_csv(session_id: str, working_dir: str, rel_file: str) -> Dict[str, Any]:
    """Read a CSV (data/-relative name or absolute in-root path) → {file,columns,rows}."""
    path = _resolve_confined(session_id, working_dir, rel_file)
    raw = path.read_bytes()  # FileNotFoundError propagates
    reader = csv.reader(io.StringIO(store._decode_csv_bytes(raw)))
    all_rows = list(reader)
    if not all_rows:
        return {"file": rel_file, "columns": [], "rows": []}
    header = [str(c).strip() or f"column_{i+1}" for i, c in enumerate(all_rows[0])]
    if len(header) > store._MAX_DATA_COLS:
        header = header[: store._MAX_DATA_COLS]
    body = all_rows[1:]
    warning = None
    if len(body) > store._MAX_DATA_ROWS:
        warning = f"Showing first {store._MAX_DATA_ROWS} of {len(body)} rows"
        body = body[: store._MAX_DATA_ROWS]
    rows: List[dict] = [
        {col: (r[i] if i < len(r) else "") for i, col in enumerate(header)} for r in body
    ]
    out: Dict[str, Any] = {
        "file": rel_file,
        "columns": [{"name": h, "type": "string"} for h in header],
        "rows": rows,
    }
    if warning:
        out["warning"] = warning
    return out


def write_session_csv(
    session_id: str, working_dir: str, rel_file: str, columns: Any, rows: Any
) -> Dict[str, Any]:
    """Write edited rows to ``data/<rel_file>`` (atomic). Reuses store caps."""
    if not rel_file.endswith(".csv"):
        raise ValueError("file must be a .csv")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if len(rows) > store._MAX_DATA_ROWS:
        raise ValueError(f"too many rows (max {store._MAX_DATA_ROWS})")
    header = store._coerce_header(columns)
    if not header and rows and isinstance(rows[0], dict):
        header = store._coerce_header(list(rows[0].keys()))
    if not header:
        raise ValueError("no columns to write")
    if len(header) > store._MAX_DATA_COLS:
        raise ValueError(f"too many columns (max {store._MAX_DATA_COLS})")
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each row must be an object")
        writer.writerow(["" if row.get(c) is None else str(row.get(c)) for c in header])
    data = buf.getvalue().encode("utf-8")
    if len(data) > store._MAX_DATA_BYTES:
        raise ValueError(f"dataset exceeds {store._MAX_DATA_BYTES} bytes")
    target = _resolve_confined(session_id, working_dir, rel_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    store._atomic_write_bytes(target, data)
    return {"written": rel_file, "rows": len(rows), "columns": header}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_server_paths.py -v`
Expected: PASS (3 tests). If `store._decode_csv_bytes`/`_atomic_write_bytes` names differ, grep `atria/core/modules/store.py` and use the actual private names.

- [ ] **Step 5: Commit**

```bash
git add atria/core/modules/data_copilot_paths.py tests/test_data_copilot_server_paths.py
git commit -m "feat(data_copilot): server-side session CSV read/write helpers"
```

---

## Task 7: `send_table` tool (read-only interactive table/chart)

**Files:**
- Create: `atria/core/context_engineering/tools/implementations/send_table_tool.py`
- Modify: `atria/core/agents/components/schemas/builtin/web_tools.py`
- Modify: `atria/core/context_engineering/tools/registry.py`
- Modify: `atria/web/ws_tool_broadcaster.py`
- Modify: `atria/core/agents/components/schemas/normal_builder.py`
- Test: `tests/test_send_table_tool.py`

**Interfaces:**
- Consumes: `data_copilot_paths.read_session_csv` (Task 6); session (`session.id`, `session.working_directory`/`working_dir`) via `session_manager.get_current_session()` — mirror `SendEditableTableHandler`/`artifacts_handler`.
- Produces: `SendTableHandler.send(args, context) -> {success, output, data_payload}`. Args: `file` (required, abs path or data/-relative), `title` (required), `suggestions` (optional list), `max_rows` (optional int). Emits `ui_callback.on_data({title, columns, rows, suggestions, editable: false})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_send_table_tool.py
from types import SimpleNamespace
from pathlib import Path
from atria.core.context_engineering.tools.implementations.send_table_tool import (
    SendTableHandler,
)

class _CB:
    def __init__(self):
        self.payloads = []
    def on_data(self, payload):
        self.payloads.append(payload)

def test_send_table_emits_readonly_payload(tmp_path, monkeypatch):
    # arrange a result.csv inside a session root
    from atria.core.modules import data_copilot_paths as dcp
    root = dcp.data_copilot_root("sessZ", str(tmp_path))
    run = root / "runs" / "latest"; run.mkdir(parents=True)
    (run / "result.csv").write_text("region,rev\nN,10\nS,20\n", encoding="utf-8")

    cb = _CB()
    handler = SendTableHandler()
    # patch session resolution used by the handler
    monkeypatch.setattr(
        handler, "_resolve_session",
        lambda context: ("sessZ", str(tmp_path)),
    )
    ctx = SimpleNamespace(ui_callback=cb)
    res = handler.send(
        {"file": str(run / "result.csv"), "title": "Rev",
         "suggestions": [{"chart_type": "bar", "x": "region", "y": ["rev"], "title": "Rev"}]},
        ctx,
    )
    assert res["success"] is True
    p = cb.payloads[0]
    assert p["editable"] is False
    assert [c["name"] for c in p["columns"]] == ["region", "rev"]
    assert p["rows"][0]["region"] == "N"
    assert p["suggestions"][0]["chart_type"] == "bar"

def test_send_table_requires_file_and_title():
    handler = SendTableHandler()
    ctx = SimpleNamespace(ui_callback=SimpleNamespace(on_data=lambda p: None))
    assert handler.send({"title": "x"}, ctx)["success"] is False
    assert handler.send({"file": "x.csv"}, ctx)["success"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_send_table_tool.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# atria/core/context_engineering/tools/implementations/send_table_tool.py
"""send_table tool — push a READ-ONLY result table (+ chart suggestions) to chat.

Read-only sibling of send_editable_table. Reads a CSV the analysis wrote into the
session's data_copilot folder and emits the existing data_message payload with
``editable: false`` and a ``suggestions`` list, so the web UI renders an
interactive chart + table without any save-back.
"""

from __future__ import annotations

from typing import Any, Tuple


def _err(msg: str) -> dict[str, Any]:
    return {"success": False, "error": msg, "output": None}


class SendTableHandler:
    """Handler for the send_table tool."""

    def _resolve_session(self, context: Any) -> Tuple[str | None, str | None]:
        """Return (session_id, working_dir) from the current session, or (None, None)."""
        try:
            from atria.core.runtime.async_bridge import run_sync  # adjust import if needed
            from atria.core.context_engineering.tools.handlers.artifacts_handler import (
                _get_session_manager,  # if unavailable, resolve via context like siblings
            )
        except Exception:  # noqa: BLE001
            pass
        # Prefer the ui_callback session_id + session working dir.
        cb = getattr(context, "ui_callback", None)
        session_id = getattr(cb, "session_id", None)
        working_dir = getattr(cb, "working_dir", None) or getattr(cb, "working_directory", None)
        if session_id and working_dir:
            return str(session_id), str(working_dir)
        # Fallback: look up the current session record.
        try:
            from atria.core.runtime.async_bridge import run_sync as _run_sync
            deps = getattr(context, "deps", None) or getattr(context, "dependencies", None)
            sm = getattr(deps, "session_manager", None)
            if sm is not None:
                sess = _run_sync(sm.get_current_session())
                if sess is not None:
                    wd = getattr(sess, "working_directory", None) or sess.metadata.get(
                        "working_dir"
                    )
                    return str(sess.id), str(wd) if wd else None
        except Exception:  # noqa: BLE001
            return None, None
        return None, None

    def send(self, args: dict[str, Any], context: Any) -> dict[str, Any]:
        file = (args.get("file") or "").strip()
        title = (args.get("title") or "").strip()
        suggestions = args.get("suggestions") or []
        if not file:
            return _err("'file' is required")
        if not title:
            return _err("'title' is required")

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_data"):
            return _err("UI callback unavailable; send_table only works in the web UI")

        session_id, working_dir = self._resolve_session(context)
        if not session_id or not working_dir:
            return _err("no active session/working_dir to resolve the table path")

        try:
            from atria.core.modules import data_copilot_paths as dcp

            data = dcp.read_session_csv(session_id, working_dir, file)
        except FileNotFoundError:
            return _err(f"table not found: {file!r}")
        except ValueError as exc:
            return _err(str(exc))
        except Exception as exc:  # noqa: BLE001
            return _err(f"failed to read table: {exc}")

        columns = data.get("columns") or []
        rows = data.get("rows") or []
        max_rows = args.get("max_rows")
        if isinstance(max_rows, int) and max_rows > 0:
            rows = rows[:max_rows]

        payload: dict[str, Any] = {
            "title": title,
            "columns": columns,
            "rows": rows,
            "suggestions": suggestions if isinstance(suggestions, list) else [],
            "editable": False,
        }
        if data.get("warning"):
            payload["warning"] = data["warning"]

        ui_callback.on_data(payload)
        return {
            "success": True,
            "output": f"Sent table ({len(rows)} rows × {len(columns)} cols): {title}",
            "data_payload": payload,
        }
```

Note: the `_resolve_session` helper is written defensively; during implementation, mirror exactly how `SendEditableTableHandler.send` / `artifacts_handler` obtain the session (`session_manager.get_current_session()` + `session.metadata`) and the working dir. Keep the `(session_id, working_dir)` return contract so the test's monkeypatch holds.

- [ ] **Step 4: Register the tool**

In `atria/core/agents/components/schemas/builtin/web_tools.py`, add after the `send_editable_table` schema block:

```python
    {
        "type": "function",
        "function": {
            "name": "send_table",
            "description": (
                "Send a READ-ONLY result table to the web UI chat as an interactive "
                "table + chart. Provide `file` (absolute path to a CSV the analysis "
                "wrote — e.g. the `result_table` from data_copilot analyze — or a name "
                "relative to the session's data_copilot data/ dir) and a `title`. "
                "Optionally pass `suggestions` (chart specs: chart_type, x, y[], title) "
                "so the UI renders an interactive chart; forward the `suggestions` "
                "returned by analyze. Use this to show computed results; it is NOT "
                "editable. Only works in the web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute CSV path, or a name under the session data/ dir.",
                    },
                    "title": {"type": "string", "description": "Title shown above the table."},
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Optional chart specs (chart_type, x, y[], title) to render "
                            "an interactive chart above the table."
                        ),
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Optional cap on rows sent to the UI.",
                    },
                },
                "required": ["file", "title"],
            },
        },
    },
```

In `registry.py`: add the import next to `SendEditableTableHandler`:

```python
from atria.core.context_engineering.tools.implementations.send_table_tool import (
    SendTableHandler,
)
```

instantiate near the other handlers (`self._send_editable_table_handler = ...`):

```python
        self._send_table_handler = SendTableHandler()
```

add to the `_handlers` dispatch map (next to `"send_editable_table": ...`):

```python
            "send_table": self._send_table_handler.send,
```

and add `"send_table"` to the normal-mode allow-list array (the block near line 463 that lists `"send_image", "send_editable_table"`).

In `atria/web/ws_tool_broadcaster.py`, extend the set (line ~40):

```python
        {"send_image", "send_editable_table", "send_table"}
```

In `atria/core/agents/components/schemas/normal_builder.py`, add `"send_table"` to the tool-name list next to `"send_editable_table"` (line ~33).

- [ ] **Step 5: Run test + a registry import smoke check**

Run: `uv run pytest tests/test_send_table_tool.py -v`
Expected: PASS.
Run: `uv run python -c "from atria.core.context_engineering.tools.registry import ToolRegistry"` (adjust class name if different) — Expected: no ImportError.

- [ ] **Step 6: Commit**

```bash
git add atria/core/context_engineering/tools/implementations/send_table_tool.py \
        atria/core/agents/components/schemas/builtin/web_tools.py \
        atria/core/context_engineering/tools/registry.py \
        atria/web/ws_tool_broadcaster.py \
        atria/core/agents/components/schemas/normal_builder.py \
        tests/test_send_table_tool.py
git commit -m "feat(tools): add read-only send_table tool for interactive result tables"
```

---

## Task 8: `/api/data-copilot/{read,write}` route

**Files:**
- Create: `atria/web/routes/data_copilot.py`
- Modify: the web app route registration (grep for where `modules` router is `include_router`-ed, e.g. `atria/web/server.py` or `atria/web/routes/__init__.py`)
- Test: `tests/test_data_copilot_route.py`

**Interfaces:**
- Consumes: `data_copilot_paths.read_session_csv`/`write_session_csv` (Task 6); resolves `working_dir` from the session via the existing session lookup used by `atria/web/routes/artifacts.py` (`conv_repo`/`session_manager` → `working_directory`).
- Produces: `GET /api/data-copilot/read?session_id=&file=` → `{file, columns, rows, warning?}`; `PUT /api/data-copilot/write` (body `{session_id, file, columns, rows}`) → `{written, rows, columns}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_route.py
from fastapi.testclient import TestClient
import pytest

# Build a minimal app mounting only the data_copilot router, with the session
# working-dir resolver overridden to a tmp dir.
def _make_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from atria.web.routes import data_copilot as dc_route
    monkeypatch.setattr(dc_route, "_working_dir_for_session", lambda sid: str(tmp_path))
    app = FastAPI()
    app.include_router(dc_route.router)
    return TestClient(app)

def test_write_then_read(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    w = client.put("/api/data-copilot/write", json={
        "session_id": "s1", "file": "edited.csv",
        "columns": [{"name": "a"}, {"name": "b"}],
        "rows": [{"a": "1", "b": "x"}],
    })
    assert w.status_code == 200 and w.json()["rows"] == 1
    r = client.get("/api/data-copilot/read", params={"session_id": "s1", "file": "edited.csv"})
    assert r.status_code == 200
    assert r.json()["rows"][0]["a"] == "1"

def test_read_missing_is_404(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/data-copilot/read", params={"session_id": "s1", "file": "nope.csv"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_route.py -v`
Expected: FAIL — route module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# atria/web/routes/data_copilot.py
"""Read/write session-scoped data_copilot CSVs for the editable chat table."""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from atria.core.modules import data_copilot_paths as dcp

router = APIRouter(prefix="/api/data-copilot", tags=["data-copilot"])


def _working_dir_for_session(session_id: str) -> str:
    """Resolve a session's working directory. Overridden in tests.

    Mirror the resolution used in atria/web/routes/artifacts.py (session_manager
    / conversation repo). Raise HTTPException(404) if the session is unknown.
    """
    from atria.web.state import get_state  # adjust to the real accessor

    state = get_state()
    sess = state.session_manager.get_session_by_id_sync(session_id)  # adjust to real API
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    wd = getattr(sess, "working_directory", None)
    if not wd:
        raise HTTPException(status_code=404, detail="session has no working_dir")
    return str(wd)


class WriteBody(BaseModel):
    session_id: str
    file: str
    columns: List[Any] = []
    rows: List[Any] = []


@router.get("/read")
def read_endpoint(session_id: str = Query(...), file: str = Query(...)) -> dict:
    working_dir = _working_dir_for_session(session_id)
    try:
        return dcp.read_session_csv(session_id, working_dir, file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/write")
def write_endpoint(body: WriteBody) -> dict:
    working_dir = _working_dir_for_session(body.session_id)
    try:
        return dcp.write_session_csv(
            body.session_id, working_dir, body.file, body.columns, body.rows
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

- [ ] **Step 4: Register the router**

Grep for the existing router registration (e.g. `include_router(modules` ) and add:

```python
from atria.web.routes import data_copilot as data_copilot_routes
app.include_router(data_copilot_routes.router)
```

Adjust `_working_dir_for_session`'s real body to match `artifacts.py`'s session/working-dir resolution (that file already resolves `working_dir` for a conversation — reuse the same manager/repo calls). The test overrides this function, so the route logic is verified independently of the exact resolver.

- [ ] **Step 5: Run test + commit**

Run: `uv run pytest tests/test_data_copilot_route.py -v`
Expected: PASS.

```bash
git add atria/web/routes/data_copilot.py tests/test_data_copilot_route.py <registration-file>
git commit -m "feat(web): /api/data-copilot read/write route for session CSVs"
```

---

## Task 9: Rebind `send_editable_table` to session files

**Files:**
- Modify: `atria/core/context_engineering/tools/implementations/send_editable_table_tool.py`
- Test: `tests/test_send_editable_table_session.py`

**Interfaces:**
- Consumes: `data_copilot_paths.read_session_csv` (Task 6); `SendTableHandler._resolve_session` pattern (Task 7) — factor the session resolver into a shared helper `_resolve_session(context)` (put it in `send_table_tool.py` and import it here, DRY).
- Produces: when called with `file` and NO `module` (or `module == "data_copilot"` with a session active), read via session root and set `source = {"session": <session_id>, "file": <rel>}`. Existing `module`+`file` path unchanged (back-compat).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_send_editable_table_session.py
from types import SimpleNamespace
from atria.core.context_engineering.tools.implementations.send_editable_table_tool import (
    SendEditableTableHandler,
)

class _CB:
    def __init__(self): self.payloads = []
    def on_data(self, p): self.payloads.append(p)

def test_editable_session_source(tmp_path, monkeypatch):
    from atria.core.modules import data_copilot_paths as dcp
    dcp.write_session_csv("sEdit", str(tmp_path), "grid.csv",
                          [{"name": "a"}], [{"a": "1"}])
    h = SendEditableTableHandler()
    monkeypatch.setattr(h, "_resolve_session", lambda ctx: ("sEdit", str(tmp_path)), raising=False)
    cb = _CB()
    res = h.send({"file": "grid.csv", "title": "Grid"},
                 SimpleNamespace(ui_callback=cb))
    assert res["success"] is True
    p = cb.payloads[0]
    assert p["editable"] is True
    assert p["source"] == {"session": "sEdit", "file": "grid.csv"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_send_editable_table_session.py -v`
Expected: FAIL — current handler requires `module` and sets `source={module,file}`.

- [ ] **Step 3: Write minimal implementation**

Refactor the session resolver into `send_table_tool.py` as a module-level function `resolve_session(context) -> tuple[str|None, str|None]` and have both handlers use it (`SendTableHandler._resolve_session` becomes a thin wrapper, and `SendEditableTableHandler` gets a `_resolve_session` method delegating to it so the test's monkeypatch works).

In `send_editable_table_tool.py`, at the top of `send`, branch on whether a module was supplied:

```python
        module = (args.get("module") or "").strip()
        file = (args.get("file") or "").strip()
        title = (args.get("title") or "").strip()
        editable_columns = args.get("editable_columns")
        if not file:
            return _err("'file' is required")
        if not title:
            return _err("'title' is required")

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_data"):
            return _err("UI callback unavailable; send_editable_table only works in the web UI")

        if not module or module == "data_copilot":
            session_id, working_dir = self._resolve_session(context)
            if session_id and working_dir:
                return self._send_session(
                    session_id, working_dir, file, title, editable_columns, ui_callback
                )
        # else: fall through to the existing module-store path (unchanged)
```

Add the method:

```python
    def _resolve_session(self, context):
        from atria.core.context_engineering.tools.implementations.send_table_tool import (
            resolve_session,
        )
        return resolve_session(context)

    def _send_session(self, session_id, working_dir, file, title, editable_columns, ui_callback):
        from atria.core.modules import data_copilot_paths as dcp

        try:
            data = dcp.read_session_csv(session_id, working_dir, file)
        except FileNotFoundError:
            return _err(f"dataset not found: {file!r}")
        except Exception as exc:  # noqa: BLE001
            return _err(f"failed to read dataset: {exc}")

        columns = data.get("columns") or []
        rows = data.get("rows") or []
        rel_file = file
        allow = None
        if isinstance(editable_columns, list) and editable_columns:
            allow = {str(c) for c in editable_columns}
        for col in columns:
            if isinstance(col, dict):
                col["editable"] = True if allow is None else (col.get("name") in allow)
        payload = {
            "title": title,
            "columns": columns,
            "rows": rows,
            "suggestions": [],
            "editable": True,
            "source": {"session": session_id, "file": rel_file},
        }
        if data.get("warning"):
            payload["warning"] = data["warning"]
        ui_callback.on_data(payload)
        return {
            "success": True,
            "output": f"Sent editable table ({len(rows)} rows × {len(columns)} cols) for {rel_file}",
            "data_payload": payload,
        }
```

Keep the existing module-store block below as the fallback (when a non-data_copilot `module` is supplied, or no session is active). Move the current `if not module:` early-return so it only fires in the fallback branch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_send_editable_table_session.py -v`
Expected: PASS. Also run the existing editable-table test to confirm back-compat: `uv run pytest tests/test_module_dataset_rw.py -v` (if it exercises the module path) — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/core/context_engineering/tools/implementations/send_editable_table_tool.py \
        atria/core/context_engineering/tools/implementations/send_table_tool.py \
        tests/test_send_editable_table_session.py
git commit -m "feat(tools): send_editable_table binds to session data_copilot files"
```

---

## Task 10: Wire the chart.js renderer into `DataMessage.tsx`

**Files:**
- Modify: `web-ui/src/components/Chat/DataMessage/DataMessage.tsx`
- Test: `web-ui/src/components/Chat/DataMessage/chartProcessor.test.ts` (extend — confirms suggestion→config); manual/e2e for the render.

**Interfaces:**
- Consumes: `data_suggestions?: ChartSuggestion[]`, `data_columns`, `data_rows` on `Message`; `useChartsStore` (`initFromSuggestion`, `update`, `states[messageId]`); `processChart(rows, columns, state)`; `<ChartView chart chartType title axisLabels legend grid numberFormat />`; `<EditPanel messageId columns chartRef onClose />`.
- Produces: read-only DataMessage renders a Chart/Table toggle when `data_suggestions?.length`.

- [ ] **Step 1: Write/extend the failing test**

Extend `chartProcessor.test.ts` with a case that mirrors what DataMessage will feed the store, asserting a suggestion produces a valid chart config (this locks the store→processor contract the wiring relies on):

```ts
// chartProcessor.test.ts (append)
import { describe, it, expect } from 'vitest';
import { processChart } from './chartProcessor';
import type { ChartEditState } from '../../../stores/charts';

describe('processChart from a suggestion-derived state', () => {
  it('builds datasets for bar chart', () => {
    const state: ChartEditState = {
      activeSuggestionIdx: 0, chartType: 'bar', xField: 'region', yFields: ['rev'],
      title: 'Rev', axisLabels: {}, seriesLabels: { rev: 'rev' },
      seriesColors: { rev: '#3b82f6' }, legend: true, grid: true, numberFormat: 'plain',
    };
    const res = processChart(
      [{ region: 'N', rev: 10 }, { region: 'S', rev: 20 }],
      [{ name: 'region', type: 'string' }, { name: 'rev', type: 'number' }],
      state,
    );
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.chart.labels).toEqual(['N', 'S']);
      expect(res.chart.datasets[0].data).toEqual([10, 20]);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it passes already (contract check)**

Run: `cd web-ui && yarn vitest run src/components/Chat/DataMessage/chartProcessor.test.ts`
Expected: PASS (processChart already exists). This confirms the contract before wiring the view.

- [ ] **Step 3: Wire ChartView + switcher + EditPanel into DataMessage**

In `DataMessage.tsx`, add imports:

```tsx
import { useRef } from 'react';
import { ChartView } from './ChartView';
import { EditPanel } from './EditPanel';
import { processChart } from './chartProcessor';
import { useChartsStore } from '../../../stores/charts';
```

In the read-only render path (after `const messageId = ...`), add chart state derivation:

```tsx
  const suggestions = message.data_suggestions ?? [];
  const hasCharts = suggestions.length > 0;
  const chartRef = useRef<any>(null);
  const chartState = useChartsStore((s) => s.states[messageId]);
  const initFromSuggestion = useChartsStore((s) => s.initFromSuggestion);
  const [showEdit, setShowEdit] = useState(false);

  useEffect(() => {
    if (hasCharts && !chartState) {
      initFromSuggestion(messageId, suggestions, columns, 0);
    }
  }, [hasCharts, chartState, messageId, columns.length, suggestions.length]);
```

Extend the view state type to include `'chart'` and default to it when charts exist:

```tsx
  const [view, setView] = useState<'preview' | 'table' | 'chart'>(
    hasCharts ? 'chart' : imageSrc ? 'preview' : 'table'
  );
```

Add a Chart toggle button in the header button group (next to the existing Chart/Table buttons), shown when `hasCharts`:

```tsx
              {hasCharts && (
                <button
                  onClick={() => setView('chart')}
                  className={`px-2 py-1 ${view === 'chart' ? 'bg-accent-main-100/15 text-accent-main-100' : 'text-text-300 hover:bg-bg-200'}`}
                >
                  Chart
                </button>
              )}
```

Add the chart body branch before the existing `view === 'preview'` branch:

```tsx
        {view === 'chart' && hasCharts && chartState ? (
          (() => {
            const res = processChart(rows, columns, chartState);
            return (
              <div>
                {/* suggestion switcher */}
                {suggestions.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto px-3 pt-3">
                    {suggestions.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => initFromSuggestion(messageId, suggestions, columns, i)}
                        className={`px-2 py-1 text-xs rounded border ${chartState.activeSuggestionIdx === i ? 'border-accent-main-100 text-accent-main-100' : 'border-border-300/15 text-text-300'}`}
                      >
                        {s.title ?? s.chart_type}
                      </button>
                    ))}
                  </div>
                )}
                <div className="p-3" style={{ height: 320 }}>
                  {res.ok ? (
                    <ChartView
                      ref={chartRef}
                      chart={res.chart}
                      chartType={chartState.chartType}
                      title={chartState.title}
                      axisLabels={chartState.axisLabels}
                      legend={chartState.legend}
                      grid={chartState.grid}
                      numberFormat={chartState.numberFormat}
                    />
                  ) : (
                    <div className="text-sm text-text-300">{res.error}</div>
                  )}
                </div>
                <div className="px-3 pb-2">
                  <button
                    onClick={() => setShowEdit((v) => !v)}
                    className="text-xs text-text-300 hover:text-text-000"
                  >
                    {showEdit ? 'Hide' : 'Edit chart'}
                  </button>
                </div>
                {showEdit && (
                  <EditPanel
                    messageId={messageId}
                    columns={columns}
                    chartRef={chartRef}
                    onClose={() => setShowEdit(false)}
                  />
                )}
              </div>
            );
          })()
        ) : view === 'preview' && imageSrc ? (
          // ... existing preview branch unchanged ...
```

Ensure the trailing branches (`preview`, table) remain intact — this inserts a new leading branch in the existing ternary chain.

- [ ] **Step 4: Typecheck + build the UI**

Run: `cd web-ui && yarn tsc --noEmit`
Expected: no type errors (verify `EditPanel`'s `chartRef`/`onClose` prop names against its definition; adjust if they differ).
Run: `make build-ui`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web-ui/src/components/Chat/DataMessage/DataMessage.tsx \
        web-ui/src/components/Chat/DataMessage/chartProcessor.test.ts
git commit -m "feat(web-ui): render interactive chart from data_suggestions in chat"
```

---

## Task 11: Session-aware editable save/reload in the frontend

**Files:**
- Modify: `web-ui/src/types/index.ts` (`data_source` gains `session?`)
- Modify: `web-ui/src/api/client.ts` (`readSessionDataset`/`writeSessionDataset`)
- Modify: `web-ui/src/components/Chat/DataMessage/EditableDataTable.tsx`
- Modify: `web-ui/src/components/Chat/DataMessage/DataMessage.tsx` (editable-variant guard accepts `session`)
- Test: none new (network I/O) — covered by typecheck + e2e in Task 12.

**Interfaces:**
- Consumes: `/api/data-copilot/{read,write}` (Task 8).
- Produces: `apiClient.readSessionDataset(sessionId, file)` and `writeSessionDataset(sessionId, file, columns, rows)`; `EditableDataTable` accepts `source: { module?: string; file: string; session?: string }` and picks the route by which field is present.

- [ ] **Step 1: Extend the type**

In `types/index.ts`:

```ts
  data_source?: { module?: string; file: string; session?: string };
```

- [ ] **Step 2: Add api client methods**

In `api/client.ts`, next to `readDataset`/`writeDataset`:

```ts
  readSessionDataset(sessionId: string, file: string) {
    return request<{ file: string; columns: DataColumn[]; rows: Record<string, any>[]; warning?: string }>(
      `/data-copilot/read?session_id=${encodeURIComponent(sessionId)}&file=${encodeURIComponent(file)}`
    );
  },
  writeSessionDataset(
    sessionId: string, file: string, columns: any[], rows: Record<string, any>[]
  ) {
    return request<{ written: string; rows: number; columns: string[] }>(
      `/data-copilot/write`,
      { method: 'PUT', body: JSON.stringify({ session_id: sessionId, file, columns, rows }) }
    );
  },
```

(Match the exact `request` signature/base-path already used by `readDataset`/`writeDataset` — mirror their call style.)

- [ ] **Step 3: Make EditableDataTable route-aware**

In `EditableDataTable.tsx`, change the `source` prop type and the save/reload calls:

```tsx
  source: { module?: string; file: string; session?: string };
```

Save handler — replace the `apiClient.writeDataset(source.module, ...)` call:

```tsx
      const res = source.session
        ? await apiClient.writeSessionDataset(source.session, source.file, cols, editRows)
        : await apiClient.writeDataset(source.module as string, source.file, cols, editRows);
```

Reload handler — replace `apiClient.readDataset(source.module, source.file)`:

```tsx
      const data = source.session
        ? await apiClient.readSessionDataset(source.session, source.file)
        : await apiClient.readDataset(source.module as string, source.file);
```

Update the footer label that renders `{source.module}/{source.file}`:

```tsx
            {(source.session ? `session:${source.session}` : source.module)}/{source.file}
```

Update the deps arrays that reference `source.module` to also include `source.session`.

- [ ] **Step 4: Accept session in the editable guard**

In `DataMessage.tsx`, broaden the editable-variant guard:

```tsx
  if (message.data_editable && src && src.file && (src.module || src.session)) {
```

- [ ] **Step 5: Typecheck + build + commit**

Run: `cd web-ui && yarn tsc --noEmit && cd .. && make build-ui`
Expected: no errors; build succeeds.

```bash
git add web-ui/src/types/index.ts web-ui/src/api/client.ts \
        web-ui/src/components/Chat/DataMessage/EditableDataTable.tsx \
        web-ui/src/components/Chat/DataMessage/DataMessage.tsx
git commit -m "feat(web-ui): editable table round-trips via /api/data-copilot"
```

---

## Task 12: SKILL.md runbook update + end-to-end verification

**Files:**
- Modify: `modules/data_copilot/SKILL.md`

**Interfaces:** none (docs + verification).

- [ ] **Step 1: Update the runbook prose**

Update `modules/data_copilot/SKILL.md`:
- In step 3 ("Present the result"), add: after presenting the report, if the
  summary has a `result_table`, call the `send_table` tool with
  `file=<result_table>`, a short `title`, and `suggestions=<summary.suggestions>`
  to show an interactive table + chart in chat. For any file in `figures`, you
  may also call `send_image` with its absolute path and a caption.
- Note that ingested datasets, run outputs, and the audit trail now live in the
  per-session data_copilot folder (not the module folder), resolved
  automatically — no path changes needed by the user.
- In the "Review / fix the source data" section, note that `send_editable_table`
  now binds to the session's copy and saves back there via `/api/data-copilot`.
- Keep prose/bullets — no tables (per repo rule).

- [ ] **Step 2: Run the full unit suite**

Run: `export OPENAI_API_KEY="<key>"; make test`
Expected: all tests pass (new + existing).

- [ ] **Step 3: Real end-to-end (required by CLAUDE.md)**

```bash
export OPENAI_API_KEY="<key>"
make run   # start the web UI
```

Drive the real flow in the web UI:
1. Upload/point at a CSV; `ingest` it — confirm the copy lands under
   `<workspace>/.artifacts/data_copilot/<session_id>/data/`.
2. Ask an analytical question so the agent runs `analyze` — confirm the run dir,
   `result.csv`, `result.meta.json`, and any `figures/*.png` are under
   `.artifacts/data_copilot/<session_id>/runs/…` and that `audit.jsonl` is in
   the session root (module folder untouched).
3. Confirm the agent calls `send_table` and the chat shows an interactive
   chart + table with a working type switcher and Edit panel.
4. Confirm `send_editable_table` renders an editable grid; edit a cell, Save,
   and verify the session CSV is rewritten (reload shows the edit) via the
   `/api/data-copilot/write` route.
5. Confirm `send_image` still shows a PNG chart bubble when used.

- [ ] **Step 4: Commit**

```bash
git add modules/data_copilot/SKILL.md
git commit -m "docs(data_copilot): runbook for session storage + send_table + charts"
```

---

## Self-Review

**Spec coverage:**
- §1 conversation-folder storage → Tasks 1, 2, 3, 5 (`_default_out_dir`).
- §2 analyze result table + suggestions → Tasks 4, 5.
- §3 `send_table` tool → Task 7.
- §4 wire chart.js renderer → Task 10.
- §5 editable rebind (helper, route, tool, frontend) → Tasks 6, 8, 9, 11.
- §6 charts-as-PNG + SKILL.md → Task 12.
- Reference audit "out of scope" items → not implemented (documented in spec).

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". The two
defensively-written spots (`send_table_tool._resolve_session`,
`data_copilot.py:_working_dir_for_session`) carry explicit instructions to
mirror the existing `artifacts_handler`/`artifacts.py` resolution and are
verified by tests that override them, so the route/tool logic is proven
independently of the exact session-lookup API.

**Type consistency:** `ChartSuggestion` shape `{chart_type,x,y[],title}` is used
consistently across `charts.detect_suggestions`, the `send_table` payload,
`data_suggestions`, and the store. `source` is `{module?,file,session?}` in the
type, `EditableDataTable`, the guard, and the tool payloads. `read_session_csv`/
`write_session_csv` signatures match their call sites in the tool and route.
`data_copilot_root(session_id, working_dir)` is identical in `paths.py`
(env-derived) and `data_copilot_paths.py` (arg-derived).

## Notes for the implementer

- Private `store._*` names (`_decode_csv_bytes`, `_atomic_write_bytes`,
  `_coerce_header`, `_MAX_*`) are reused in Task 6 — if any name differs, grep
  `atria/core/modules/store.py` and use the real one (do not duplicate the
  logic).
- The exact session-lookup API (`get_session_by_id_sync`, `working_directory`)
  in Tasks 7–8 must be matched to `atria/web/routes/artifacts.py` and
  `send_editable_table_tool.py` — those files already resolve conversation_id +
  working_dir; copy their approach rather than inventing one.
- Run `make check` (format + lint + typecheck) before each commit on Python
  changes; `yarn tsc --noEmit` for frontend changes.
