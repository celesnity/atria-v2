# data_copilot → data-agent LangGraph Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `data_copilot`'s linear `analyze`/`persona` loops with a faithful port of the data-agent's 10-node LangGraph flow — hosted as a CLI with a durable checkpointer (`run`/`resume` HITL) and a stateful Jupyter kernel — producing the reference's verbatim telecom persona report and semantic gates, with agent-driven Atria integration.

**Architecture:** A LangGraph `StateGraph` (`generate_plan → human_review(interrupt) → classify_review → generate_code → code_critic → execute_code → repair_code → semantic_verify → semantic_fix → generate_report`) is driven by a stateless CLI. State persists in a `SqliteSaver` keyed by `thread_id`; `run` stops at the plan interrupt and returns the plan, `resume` reopens the checkpoint and continues. A `jupyter_client` kernel executes code statefully; on resume a fresh kernel replays `executed_cells`. The report and ~12 gates are ported verbatim from the reference; LLM calls bind to the existing `RoleClient`.

**Tech Stack:** Python 3.10, `langgraph`, `langgraph-checkpoint-sqlite`, `jupyter_client`, `ipykernel`, `instructor`, `pydantic`, `pandas`/`scikit-learn`/`matplotlib` (existing), `pytest`.

**Reference source (copy-from):** `/home/anlnm/duynvt/.reference/data-agent/`
- `langgraph_agent/{graph,nodes,state}.py`
- `triadic_dgm/services/report_generator.py`
- `triadic_dgm/schemas/report_schema.py`
- `triadic_dgm/agent/verifier.py` (gates)
- `triadic_dgm/prompts/prompts.py` (`PLANNER_PROMPT`, `CLASSIFIER_PROMPT`, `CRITIC_PROMPT`, `SEMANTIC_FIX`, `RESULT_PROMPT`, `PROGRAMMER_PROMPT_V2`)
- `triadic_dgm/sandbox/kernel.py`
- `ui/display.py` (`display_suggestions`)

**Design spec:** `docs/superpowers/specs/2026-07-06-data-copilot-dataagent-port-design.md`

## Global Constraints

- Line length 100 (Black + Ruff); type hints on public APIs (mypy strict); Google-style docstrings.
- Module scripts import siblings by bare name after `sys.path.insert(0, <scripts dir>)`; keep the `# type: ignore[import-not-found]` convention and the `importlib.util.spec_from_file_location` test-loader pattern used by existing `tests/test_data_copilot_*.py`.
- Final CLI result is a single JSON object on **stdout**; all progress/logging goes to **stderr** (`_progress`). Every CLI failure returns a clean `{"error": ...}` JSON with exit code 1 — never an uncaught traceback.
- Sandbox/kernel child process env is scrubbed to the allow-list in `sandbox._safe_env` (no `OPENAI_API_KEY`/`ATRIA_*`/`DC_*`); `MPLBACKEND=Agg`.
- Verdict vocab is `{"status": "ACCEPT"|"REVISE", "missing": [...], "feedback": str, "epiplexity_score": float}`.
- Retry budgets: syntax repairs = 4, semantic revisions = 5.
- Persona JSON markers: `[JSON_START_PERSONA]` … `[JSON_END_PERSONA]`.
- Telecom specifics are copied **verbatim** from the reference; do not paraphrase catalog values, gate messages, or section headings.
- Excluded: DGM/evolution, RIMRULE memory bank, Gradio UI, `api_server.py`, web-native graph routes/UI.
- Run tests with `uv run pytest <file>` (target `tests/test_data_copilot_*.py` directly — the broader suite has unrelated collection errors).

---

## Phase 1 — Scaffolding & vocab

### Task 1: Dependencies, `state.py`, and verdict-vocab constants

**Files:**
- Modify: `modules/data_copilot/requirements.txt`
- Create: `modules/data_copilot/scripts/state.py`
- Create: `modules/data_copilot/scripts/verdict.py`
- Test: `tests/test_data_copilot_state.py`

**Interfaces:**
- Produces: `state.AgentState` (TypedDict with the keys listed below). `verdict.ACCEPT = "ACCEPT"`, `verdict.REVISE = "REVISE"`, `verdict.new_verdict(status: str, feedback: str = "", missing: list | None = None, epiplexity_score: float = 0.0) -> dict`.

- [ ] **Step 1: Add dependencies**

Append to `modules/data_copilot/requirements.txt`:

```text
langgraph>=0.2.0
langgraph-checkpoint-sqlite>=1.0.0
jupyter_client>=8.0.0
ipykernel>=6.0.0
instructor>=1.0.0
Pillow>=10.0.0
```

Install into the venv:

Run: `uv pip install "langgraph>=0.2.0" "langgraph-checkpoint-sqlite>=1.0.0" jupyter_client ipykernel instructor Pillow`
Expected: installs without error.

- [ ] **Step 2: Write the failing test**

Create `tests/test_data_copilot_state.py`:

```python
"""Tests for AgentState shape and verdict constructors."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_agentstate_has_required_keys():
    state = _load("state", "dc_state")
    keys = set(state.AgentState.__annotations__)
    for k in (
        "messages", "user_task", "analysis_plan", "review_status", "review_feedback",
        "review_history", "generated_code", "critic_verdict", "exe_result", "exe_sign",
        "syntax_attempts", "semantic_attempts", "verdict", "inspector_hypotheses",
        "final_report", "error_message", "executed_cells",
    ):
        assert k in keys, f"missing state key: {k}"


def test_verdict_constructor_defaults():
    v = _load("verdict", "dc_verdict")
    assert v.ACCEPT == "ACCEPT" and v.REVISE == "REVISE"
    d = v.new_verdict(v.REVISE, feedback="fix X")
    assert d == {"status": "REVISE", "missing": [], "feedback": "fix X", "epiplexity_score": 0.0}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_state.py -v`
Expected: FAIL (`state.py` / `verdict.py` not found).

- [ ] **Step 4: Write `state.py`**

Create `modules/data_copilot/scripts/state.py`:

```python
"""AgentState — shared state passed between LangGraph nodes.

Ported from .reference/data-agent/langgraph_agent/state.py. Adds ``executed_cells``:
the reference keeps its process (and Jupyter kernel) alive across the human-review
interrupt, but this CLI does not — on ``resume`` a fresh kernel replays these cells
to rebuild state before continuing.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Conversation
    messages: list[dict]
    user_task: str
    # Planner & HITL
    analysis_plan: str
    review_status: str          # "APPROVE" | "REJECT" | "CLARIFICATION"
    review_feedback: str
    review_history: list[dict]
    # Code execution
    generated_code: str
    critic_verdict: bool
    exe_result: str
    exe_sign: str               # "text" | "error"
    executed_cells: list[str]   # ordered cells for kernel replay on resume
    # Retry counters
    syntax_attempts: int
    semantic_attempts: int
    # Verifier
    verdict: dict
    inspector_hypotheses: str
    # Output
    final_report: str
    error_message: str
    # Options threaded from the CLI
    domain: str
    k: Any
```

- [ ] **Step 5: Write `verdict.py`**

Create `modules/data_copilot/scripts/verdict.py`:

```python
"""Verdict vocabulary shared by the semantic gates and the graph.

Matches .reference/data-agent's SemanticVerifier: status is ACCEPT/REVISE (not
the old OK), fixes are carried in ``feedback`` (not the old ``hypotheses``).
"""
from __future__ import annotations

from typing import List, Optional

ACCEPT = "ACCEPT"
REVISE = "REVISE"


def new_verdict(
    status: str,
    feedback: str = "",
    missing: Optional[List[str]] = None,
    epiplexity_score: float = 0.0,
) -> dict:
    """Build a verdict dict in the reference shape."""
    return {
        "status": status,
        "missing": list(missing or []),
        "feedback": feedback,
        "epiplexity_score": float(epiplexity_score),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_state.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add modules/data_copilot/requirements.txt modules/data_copilot/scripts/state.py modules/data_copilot/scripts/verdict.py tests/test_data_copilot_state.py
git commit -m "feat(data_copilot): AgentState + verdict vocab + langgraph deps"
```

---

## Phase 2 — Stateful kernel

### Task 2: `kernel.py` — stateful executor with env-scrub + replay

**Files:**
- Create: `modules/data_copilot/scripts/kernel.py`
- Test: `tests/test_data_copilot_kernel.py`

**Interfaces:**
- Consumes: `sandbox._safe_env` (existing, `modules/data_copilot/scripts/sandbox.py`).
- Produces:
  - `kernel.CodeKernel(workdir: str)` — starts an IPython kernel with cwd=`workdir`, scrubbed env.
  - `CodeKernel.run(code: str) -> dict` → `{"status": "text"|"error", "stdout": str, "figures": list[str]}`.
  - `CodeKernel.replay(cells: list[str]) -> None` — execute cells in order, ignoring their output (state rebuild).
  - `CodeKernel.shutdown() -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_kernel.py`:

```python
"""Tests for the stateful Jupyter kernel executor."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def kernel_mod():
    return _load("kernel", "dc_kernel")


def test_state_persists_across_cells(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r1 = k.run("x = 21")
        assert r1["status"] == "text"
        r2 = k.run("print(x * 2)")
        assert r2["status"] == "text"
        assert "42" in r2["stdout"]
    finally:
        k.shutdown()


def test_error_status_and_message(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run("raise ValueError('boom')")
        assert r["status"] == "error"
        assert "ValueError" in r["stdout"] or "boom" in r["stdout"]
    finally:
        k.shutdown()


def test_secrets_not_inherited(kernel_mod, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run("import os; print('KEY:', os.environ.get('OPENAI_API_KEY'))")
        assert "KEY: None" in r["stdout"]
    finally:
        k.shutdown()


def test_replay_rebuilds_state(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        k.replay(["a = 5", "b = a + 1"])
        r = k.run("print(b)")
        assert "6" in r["stdout"]
    finally:
        k.shutdown()


def test_figures_collected(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run(
            "import matplotlib; matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1,2,3]); plt.savefig('c.png'); print('done')\n"
        )
        assert any(f.endswith("c.png") for f in r["figures"])
    finally:
        k.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_kernel.py -v`
Expected: FAIL (`kernel.py` not found).

- [ ] **Step 3: Write `kernel.py`**

Create `modules/data_copilot/scripts/kernel.py`. This is an adaptation of `.reference/data-agent/triadic_dgm/sandbox/kernel.py` reduced to what we need (stdout + image capture + replay), with the env scrub applied:

```python
"""Stateful IPython kernel executor for generated analysis code.

Adapted from .reference/data-agent/triadic_dgm/sandbox/kernel.py. Unlike the
one-shot subprocess sandbox, this keeps a live kernel so variables persist across
cells (incremental repair). Env is scrubbed exactly like sandbox._safe_env so
LLM-generated code cannot read API keys. Figures written into the workdir are
collected by mtime, mirroring sandbox.run_code.
"""
from __future__ import annotations

import queue
import sys
from pathlib import Path
from typing import Dict, List

import jupyter_client  # type: ignore[import-not-found]

import sandbox  # type: ignore[import-not-found]

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg")
_EXEC_TIMEOUT = 30.0


class CodeKernel:
    """A live IPython kernel scoped to a run directory."""

    def __init__(self, workdir: str) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        env = sandbox._safe_env()
        self._km = jupyter_client.KernelManager(kernel_name="python3", env=env)
        self._km.start_kernel(cwd=str(self.workdir))
        self._kc = self._km.blocking_client()
        self._kc.start_channels()
        self._kc.wait_for_ready(timeout=60)

    def _drain(self, msg_id: str) -> Dict[str, object]:
        """Collect stdout/errors until the kernel returns to idle."""
        chunks: List[str] = []
        status = "text"
        while True:
            try:
                msg = self._kc.get_iopub_msg(timeout=_EXEC_TIMEOUT)
            except queue.Empty:
                self._km.interrupt_kernel()
                return {"status": "error", "stdout": "timeout: execution exceeded "
                        f"{_EXEC_TIMEOUT}s"}
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            mtype = msg["msg_type"]
            content = msg["content"]
            if mtype == "stream":
                chunks.append(content.get("text", ""))
            elif mtype == "execute_result":
                chunks.append(str(content.get("data", {}).get("text/plain", "")))
            elif mtype == "error":
                status = "error"
                chunks.append("\n".join(content.get("traceback", [])))
            elif mtype == "status" and content.get("execution_state") == "idle":
                break
        # Strip ANSI escape codes from tracebacks for a clean stdout.
        import re

        text = re.sub(r"\x1b\[[0-9;]*m", "", "".join(chunks))
        return {"status": status, "stdout": text}

    def run(self, code: str) -> Dict[str, object]:
        """Execute one cell; return {status, stdout, figures}."""
        before = {p.name: p.stat().st_mtime for p in self.workdir.iterdir() if p.is_file()}
        msg_id = self._kc.execute(code)
        out = self._drain(msg_id)
        figures: List[str] = []
        for p in sorted(self.workdir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in _IMAGE_EXTS:
                continue
            prev = before.get(p.name)
            if prev is None or p.stat().st_mtime > prev:
                figures.append(str(p))
        out["figures"] = figures
        return out

    def replay(self, cells: List[str]) -> None:
        """Re-execute prior cells to rebuild kernel state (output ignored)."""
        for cell in cells:
            self._drain(self._kc.execute(cell))

    def shutdown(self) -> None:
        try:
            self._kc.stop_channels()
        finally:
            self._km.shutdown_kernel(now=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_kernel.py -v`
Expected: PASS (5 tests). If `kernel_name="python3"` is unavailable, run `uv run python -m ipykernel install --user --name python3` once.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/kernel.py tests/test_data_copilot_kernel.py
git commit -m "feat(data_copilot): stateful Jupyter kernel executor with env-scrub + replay"
```

---

## Phase 3 — Gates + persona schema

### Task 3: Expand `persona_schema.py` (severity + profile_attributes)

**Files:**
- Modify: `modules/data_copilot/scripts/persona_schema.py`
- Test: `tests/test_data_copilot_persona_schema.py` (extend)

**Interfaces:**
- Consumes: existing `MARKER_START/END`, `extract_personas`, `validate`.
- Produces: `validate` additionally accepts `severity` (lenient: one of `LOW|MEDIUM|HIGH|EXTREME` when present) and richer `profile_attributes`; `ROADMAP_ACTIONS: frozenset[str]` (the 10 valid `recommended_actions[0]` keys, copied from `report_generator.ROADMAP_METADATA`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_copilot_persona_schema.py`:

```python
def test_validate_accepts_severity_and_rejects_bad_severity():
    schema = _load("persona_schema", "dc_schema_sev")  # reuse the file's loader
    good = _minimal_persona()  # helper already present or inline below
    good["severity"] = "EXTREME"
    schema.validate([good])  # no raise
    bad = _minimal_persona()
    bad["severity"] = "SOMETIMES"
    import pytest
    with pytest.raises(ValueError):
        schema.validate([bad])


def test_roadmap_actions_exposed():
    schema = _load("persona_schema", "dc_schema_actions")
    assert "Thu thập thêm dữ liệu hành vi" in schema.ROADMAP_ACTIONS
```

If `_minimal_persona()` / `_load` don't exist in the file, add:

```python
def _minimal_persona() -> dict:
    return {
        "cluster_id": 0, "persona_name": "Nhóm A", "support": 10, "support_pct": 0.5,
        "confidence": "HIGH", "priority_score": 1.0, "is_anomaly": False,
        "segmentation_quality": "NORMAL", "risk_tier": "x", "evidence": {"f": 1.0},
        "profile_attributes": {}, "recommended_actions": ["Thu thập thêm dữ liệu hành vi"],
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_schema.py -k "severity or roadmap" -v`
Expected: FAIL (`_SEVERITY`/`ROADMAP_ACTIONS` not defined).

- [ ] **Step 3: Implement schema additions**

In `modules/data_copilot/scripts/persona_schema.py`, after `_RISK = {...}` add:

```python
_SEVERITY = {"LOW", "MEDIUM", "HIGH", "EXTREME"}
# The 10 valid primary actions — keys of report_generator.ROADMAP_METADATA.
# Duplicated here (not imported) to keep schema validation import-light.
ROADMAP_ACTIONS = frozenset({
    "Outbound CSKH chủ động để xoa dịu khách hàng",
    "Thu thập thêm dữ liệu hành vi",
    "Thu thập thêm App usage logs",
    "Khảo sát mức độ hài lòng qua Zalo/SMS",
    "Phân tích nguyên nhân khiếu nại/liên hệ",
    "Nghiên cứu nguyên nhân kỹ thuật",
    "Tư vấn đổi gói cước phù hợp hành vi sử dụng",
    "Khảo sát cơ hội upsell/cross-sell dịch vụ",
    "Chủ động liên hệ trước nguy cơ hạ cấp dịch vụ",
    "Phân tích nguyên nhân sử dụng dao động",
})
```

In `validate()`, in the per-persona loop where the other lenient checks live, add:

```python
        if "severity" in p and p["severity"] not in _SEVERITY:
            raise ValueError(f"persona[{i}].severity must be one of {sorted(_SEVERITY)}")
        if "profile_attributes" in p and not isinstance(p["profile_attributes"], dict):
            raise ValueError(f"persona[{i}].profile_attributes must be an object")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_persona_schema.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_schema.py tests/test_data_copilot_persona_schema.py
git commit -m "feat(data_copilot): persona schema — severity + roadmap actions + profile_attributes"
```

### Task 4: Update `persona_generate.py` prompt (roadmap actions + severity + profile_attributes)

**Files:**
- Modify: `modules/data_copilot/scripts/persona_generate.py`
- Test: `tests/test_data_copilot_persona_generate.py` (extend)

**Interfaces:**
- Consumes: `persona_schema.ROADMAP_ACTIONS` (Task 3).
- Produces: unchanged public `build_messages`/`generate_code` signatures; the system prompt now instructs the model to emit `severity`, richer `profile_attributes`, and to pick `recommended_actions[0]` from the roadmap list.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_copilot_persona_generate.py`:

```python
def test_prompt_lists_roadmap_actions_and_severity():
    gen = _load("persona_generate", "dc_pg_roadmap")
    msgs = gen.build_messages("segment", {"path": "d.csv", "columns": []})
    system = msgs[0]["content"]
    assert "severity" in system
    assert "Thu thập thêm dữ liệu hành vi" in system  # a roadmap action verbatim
    assert "profile_attributes" in system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_generate.py -k roadmap -v`
Expected: FAIL (severity/action not in prompt).

- [ ] **Step 3: Update the prompt**

In `modules/data_copilot/scripts/persona_generate.py` `_SYSTEM`, in the persona-keys sentence, add `severity ('LOW'|'MEDIUM'|'HIGH'|'EXTREME')` alongside `risk`, and append this block before the `PRINT the formula` sentence:

```python
    "profile_attributes MUST include (when the columns exist) service_composition "
    "and package_composition as {category: fraction} maps, plus any of csat_avg, "
    "ces_avg, avg_fee, high_spender_pct, tier_upgrade_rate, tier_downgrade_rate, "
    "usage_decline_strong_pct, usage_decline_mild_pct, usage_unstable_pct, "
    "status_worsening_pct, loyalty_rank_avg. recommended_actions[0] MUST be EXACTLY "
    "one of these business actions (copy verbatim): "
    "'Outbound CSKH chủ động để xoa dịu khách hàng', 'Thu thập thêm dữ liệu hành vi', "
    "'Thu thập thêm App usage logs', 'Khảo sát mức độ hài lòng qua Zalo/SMS', "
    "'Phân tích nguyên nhân khiếu nại/liên hệ', 'Nghiên cứu nguyên nhân kỹ thuật', "
    "'Tư vấn đổi gói cước phù hợp hành vi sử dụng', "
    "'Khảo sát cơ hội upsell/cross-sell dịch vụ', "
    "'Chủ động liên hệ trước nguy cơ hạ cấp dịch vụ', "
    "'Phân tích nguyên nhân sử dụng dao động'. "
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_persona_generate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_generate.py tests/test_data_copilot_persona_generate.py
git commit -m "feat(data_copilot): persona codegen prompt emits severity/profile_attributes/roadmap action"
```

### Task 5: `gates.py` — deterministic semantic gates + `is_business_task` + `verify_syntax`

**Files:**
- Create: `modules/data_copilot/scripts/gates.py`
- Test: `tests/test_data_copilot_gates.py`

**Interfaces:**
- Consumes: `persona_schema.extract_personas`, `verdict.new_verdict`, a `chat_fn: Callable[[list[dict]], str]` for `verify_syntax`.
- Produces:
  - `gates.is_business_task(user_query: str) -> bool`
  - `gates.verify_syntax(code: str, error_log: str, task: str, chat_fn) -> str`
  - `gates.verify_semantics(task: str, code: str, exec_output: str, *, domain: str | None = None) -> dict` (returns a `verdict` dict; runs the ~12 gates in reference order, first failure wins, `ACCEPT` if all pass or `is_business_task` is False).

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_gates.py`:

```python
"""Tests for the deterministic semantic gates."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _gates():
    _load("verdict", "dc_verdict_g")
    _load("persona_schema", "persona_schema")  # gates imports it by bare name
    return _load("gates", "dc_gates")


def test_non_business_task_short_circuits_accept():
    g = _gates()
    v = g.verify_semantics("print the head of the csv", "df.head()", "ok")
    assert v["status"] == "ACCEPT"


def test_missing_json_block_revises():
    g = _gates()
    v = g.verify_semantics("segment customers into personas", "code", "no markers here")
    assert v["status"] == "REVISE"
    assert "JSON" in v["feedback"]


def test_priority_score_without_formula_revises():
    g = _gates()
    stdout = (
        "[JSON_START_PERSONA]"
        '[{"cluster_id":0,"persona_name":"A","priority_score":9,"evidence":{"f":1}}]'
        "[JSON_END_PERSONA]"
    )
    v = g.verify_semantics("segment customers into personas", "code", stdout)
    assert v["status"] == "REVISE"


def test_causal_hallucination_revises_telecom():
    g = _gates()
    stdout = (
        "priority_score = a*b\n[JSON_START_PERSONA]"
        '[{"cluster_id":0,"persona_name":"A","priority_score":1,"evidence":{"f":1}}]'
        "[JSON_END_PERSONA]\nchurn do khuyến mãi của đối thủ"
    )
    v = g.verify_semantics("segment", "code", stdout, domain="telecom")
    assert v["status"] == "REVISE"
    assert "khuyến mãi" in v["feedback"] or "Causal" in v["feedback"] or "Nhân Quả" in v["feedback"]


def test_is_business_task_keywords():
    g = _gates()
    assert g.is_business_task("segment customers into personas") is True
    assert g.is_business_task("show me df.shape") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_gates.py -v`
Expected: FAIL (`gates.py` not found).

- [ ] **Step 3: Write `gates.py`**

Port the gate bodies **verbatim** from `.reference/data-agent/triadic_dgm/agent/verifier.py` (`is_business_task`, `verify_syntax`, `verify_semantics`), with these adaptations:
- Replace `self.client.chat.completions.create(...)` in `verify_syntax` with the injected `chat_fn(messages)`.
- Remove all `self.memory_bank` / RIMRULE calls (retrieve/add rules) — the memory bank is excluded.
- Return values via `verdict.new_verdict(...)` instead of ad-hoc dicts; keep the exact Vietnamese `feedback` strings verbatim.
- Copy `BUSINESS_KEYWORDS` and `_CAUSAL_TERMS` from the reference verbatim.
- Keep gates ordered exactly as the reference; first failing gate returns `REVISE` immediately.

Skeleton (fill each gate body from the reference):

```python
"""Deterministic semantic gates (Dimension 2) + LLM syntax inspector (Dimension 1).

Ported verbatim (minus the RIMRULE memory bank) from
.reference/data-agent/triadic_dgm/agent/verifier.py. verify_semantics runs the
~12 hard business gates in reference order; the first failure returns REVISE.
Gate feedback strings are copied verbatim (Vietnamese) for output parity.
"""
from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

import persona_schema  # type: ignore[import-not-found]
import verdict as _verdict  # type: ignore[import-not-found]

# Copy verbatim from the reference module-level constants:
BUSINESS_KEYWORDS = (...)   # from verifier.py
_CAUSAL_TERMS = (...)       # from verifier.py


def is_business_task(user_query: str) -> bool:
    q = user_query.lower()
    return any(kw in q for kw in BUSINESS_KEYWORDS)


def verify_syntax(code: str, error_log: str, task: str, chat_fn: Callable[[List[dict]], str]) -> str:
    system_prompt = (
        "You are a strict QA Engineer and Code Reviewer. "
        "Analyze the faulty code and the execution error log based on the original task. "
        "Provide a concise, actionable instruction on how to fix the error. "
        "CRITICAL: Your fix instructions must be generalizable. "
        "Do NOT hardcode variable names or line numbers. "
        "Do NOT write the code yourself, just give the logical steps to avoid the error."
    )
    user_prompt = (
        f"Original Task:\n{task}\n\nCode:\n```python\n{code}\n```\n\n"
        f"Error Log:\n{error_log}\n\nPlease analyze and provide generalized fix instructions."
    )
    try:
        return chat_fn([{"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}])
    except Exception as e:  # noqa: BLE001
        return f"Try using alternative approach or package. Error: {e}"


def verify_semantics(task: str, code: str, exec_output: str, *, domain: Optional[str] = None) -> dict:
    if not is_business_task(task):
        return _verdict.new_verdict(_verdict.ACCEPT)
    personas = persona_schema.extract_personas(exec_output) or []
    # --- Gate 1..N ported verbatim from verifier.verify_semantics ---
    # Each gate, in reference order, on failure:
    #     return _verdict.new_verdict(_verdict.REVISE, feedback="⚠ ...verbatim...")
    # (JSON-present, priority-formula, silhouette, RMDT leakage, geography,
    #  K>=3, name length/dup, ARPU, causal-hallucination, dBm threshold,
    #  fake-persona, increase-K, outlier-naming, business-hallucination,
    #  action-evidence contradiction)
    ...
    return _verdict.new_verdict(_verdict.ACCEPT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_gates.py -v`
Expected: PASS (5 tests). Add more gate-specific tests if a gate body needs coverage.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/gates.py tests/test_data_copilot_gates.py
git commit -m "feat(data_copilot): deterministic semantic gates + syntax inspector (verbatim port)"
```

---

## Phase 4 — Report

### Task 6: `report_schema.py` — `ReportNarrative`

**Files:**
- Create: `modules/data_copilot/scripts/report_schema.py`
- Test: `tests/test_data_copilot_report_schema.py`

**Interfaces:**
- Produces: pydantic models `ExecutiveSummaryNarrative`, `PersonaNarrative`, `ActionNarrative`, `ReportNarrative` — copied **verbatim** from `.reference/data-agent/triadic_dgm/schemas/report_schema.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_report_schema.py`:

```python
import importlib.util, sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod


def test_report_narrative_shape():
    rs = _load("report_schema", "dc_report_schema")
    n = rs.ReportNarrative(
        executive_summary=rs.ExecutiveSummaryNarrative(executive_overview="ov"),
        personas_analysis=[rs.PersonaNarrative(cluster_id=0, business_interpretation="bi", operational_impact="oi")],
        recommendations_analysis=[rs.ActionNarrative(cluster_id=0, expected_outcome="eo")],
        conclusion="c",
    )
    assert n.executive_summary.executive_overview == "ov"
    assert n.personas_analysis[0].cluster_id == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_report_schema.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Copy `report_schema.py` verbatim**

Copy `.reference/data-agent/triadic_dgm/schemas/report_schema.py` into `modules/data_copilot/scripts/report_schema.py` unchanged (it only depends on `pydantic`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_report_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/report_schema.py tests/test_data_copilot_report_schema.py
git commit -m "feat(data_copilot): ReportNarrative schema (verbatim port)"
```

### Task 7: `report_generator.py` — verbatim composer + RoleClient binding + generic fallback

**Files:**
- Create: `modules/data_copilot/scripts/report_generator.py`
- Test: `tests/test_data_copilot_report_generator.py`

**Interfaces:**
- Consumes: `report_schema.ReportNarrative`, an `instructor`-wrapped client built from `config.RoleConfig` for the `report` role; `report.generate_report` (existing grounded-markdown) for the fallback.
- Produces:
  - `report_generator.ROADMAP_METADATA`, `RETENTION_SCRIPT_CATALOG`, `FEATURE_SEMANTIC_MAP` (verbatim).
  - `report_generator.ReportGenerator(api_key, base_url, model_name)` with `.render_markdown(raw_python_output) -> str` and `.generate_markdown_report(raw_python_output) -> str` (verbatim).
  - `report_generator.compose(raw_python_output: str, *, rc, question: str) -> str` — new thin wrapper: if `[JSON_START_PERSONA]` present → `ReportGenerator(...).generate_markdown_report(...)`; else → grounded fallback via `report.generate_report(question, raw_python_output, [], chat_fn, verified=True)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_report_generator.py`:

```python
import importlib.util, sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod


def _rg():
    _load("report_schema", "report_schema")
    _load("report", "report")
    return _load("report_generator", "dc_rg")


def test_catalogs_present_verbatim():
    rg = _rg()
    assert "Thu thập thêm dữ liệu hành vi" in rg.ROADMAP_METADATA
    assert rg.ROADMAP_METADATA["Thu thập thêm dữ liệu hành vi"]["owner"] == "Data Team"


def test_compose_falls_back_when_no_persona_json():
    rg = _rg()
    calls = {}
    class RC:
        def chat(self, role, messages, **kw):
            calls["role"] = role
            return "# Generic report\nGrounded."
    out = rg.compose("total revenue: 100", rc=RC(), question="total revenue?")
    assert "Generic report" in out
    assert calls["role"] == "report"


def test_compose_uses_persona_composer_when_json_present(monkeypatch):
    rg = _rg()
    monkeypatch.setattr(rg.ReportGenerator, "generate_markdown_report",
                        lambda self, raw: "# BÁO CÁO\n(6-section)")
    class RC:
        def chat(self, role, messages, **kw):
            return "unused"
    out = rg.compose("[JSON_START_PERSONA][]" "[JSON_END_PERSONA]", rc=RC(), question="segment")
    assert "BÁO CÁO" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_report_generator.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Copy the composer verbatim, then add the wrapper**

Copy `.reference/data-agent/triadic_dgm/services/report_generator.py` into `modules/data_copilot/scripts/report_generator.py` **verbatim** (all catalogs, `ReportValidator`, `ReportGenerator`, helpers). Change only the import of the schema to the bare-name form:

```python
from report_schema import ReportNarrative  # type: ignore[import-not-found]
```

Append the wrapper at the end:

```python
def compose(raw_python_output: str, *, rc, question: str) -> str:
    """Persona 6-section report when persona JSON is present, else grounded fallback.

    rc is a RoleClient; the persona path uses instructor via ReportGenerator, the
    fallback reuses report.generate_report bound to the 'report' role.
    """
    from config import load_config  # type: ignore[import-not-found]

    if "[JSON_START_PERSONA]" in (raw_python_output or ""):
        cfg = load_config()["report"]
        gen = ReportGenerator(api_key=cfg.api_key, base_url=cfg.base_url, model_name=cfg.model)
        return gen.generate_markdown_report(raw_python_output)

    import report as _report  # type: ignore[import-not-found]

    return _report.generate_report(
        question, raw_python_output, [], lambda m: rc.chat("report", m), verified=True
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_report_generator.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/report_generator.py tests/test_data_copilot_report_generator.py
git commit -m "feat(data_copilot): verbatim telecom report composer + generic fallback wrapper"
```

---

## Phase 5 — Graph

### Task 8: `prompts.py` — planner/classifier/critic/programmer/fix prompts

**Files:**
- Create: `modules/data_copilot/scripts/prompts.py`
- Test: `tests/test_data_copilot_prompts.py`

**Interfaces:**
- Produces: `PLANNER_PROMPT`, `CLASSIFIER_PROMPT`, `CRITIC_PROMPT`, `SEMANTIC_FIX`, `RESULT_PROMPT`, `PROGRAMMER_PROMPT` (all copied verbatim from `.reference/data-agent/triadic_dgm/prompts/prompts.py`; `PROGRAMMER_PROMPT = PROGRAMMER_PROMPT_V2`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_prompts.py`:

```python
import importlib.util, sys
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[s] = m; spec.loader.exec_module(m); return m


def test_prompts_present():
    p = _load("prompts", "dc_prompts")
    for name in ("PLANNER_PROMPT", "CLASSIFIER_PROMPT", "CRITIC_PROMPT", "SEMANTIC_FIX", "PROGRAMMER_PROMPT"):
        assert isinstance(getattr(p, name), str) and getattr(p, name).strip()
    assert "{feedback}" in p.CLASSIFIER_PROMPT
    assert "{code}" in p.CRITIC_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_prompts.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Copy prompts verbatim**

Create `modules/data_copilot/scripts/prompts.py` with `PLANNER_PROMPT`, `CLASSIFIER_PROMPT`, `CRITIC_PROMPT`, `SEMANTIC_FIX`, `RESULT_PROMPT`, and `PROGRAMMER_PROMPT_V2` copied verbatim from the reference; add `PROGRAMMER_PROMPT = PROGRAMMER_PROMPT_V2`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/prompts.py tests/test_data_copilot_prompts.py
git commit -m "feat(data_copilot): port planner/classifier/critic/programmer prompts (verbatim)"
```

### Task 9: `nodes.py` — the 10 graph nodes bound to `RoleClient`

**Files:**
- Create: `modules/data_copilot/scripts/nodes.py`
- Test: `tests/test_data_copilot_nodes.py`

**Interfaces:**
- Consumes: `state.AgentState`, `prompts`, `generate.extract_code`, `guardrails.check_code`, `kernel.CodeKernel`, `gates`, `report_generator.compose`, `verdict`, `profile.profile_dataset`, a shared context object.
- Produces: node functions with signature `node(state: AgentState, ctx) -> dict` where `ctx` carries `rc` (RoleClient), `kernel` (CodeKernel), `profile` (dict), `dataset` (str), `domain`, `k`. Node names: `generate_plan`, `human_review`, `classify_review`, `generate_code`, `code_critic`, `execute_code`, `repair_code`, `semantic_verify`, `semantic_fix`, `generate_report`.
- `human_review` calls `langgraph.types.interrupt({"type": "plan_review", "plan": ...})`.

Each node is a pure `(state, ctx) -> partial-state dict` adapted from `.reference/data-agent/langgraph_agent/nodes.py`, with the reference's `agent.programmer._call_chat_model_streaming()` replaced by `ctx.rc.chat("codegen", messages)` (non-streaming) and `agent.run_code(code)` replaced by `ctx.kernel.run(code)` (append the executed code to `state["executed_cells"]`). `semantic_verify` calls `gates.verify_semantics`; `generate_report` calls `report_generator.compose`.

- [ ] **Step 1: Write the failing test (routing-relevant node behavior)**

Create `tests/test_data_copilot_nodes.py`:

```python
import importlib.util, sys, types
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[s] = m; spec.loader.exec_module(m); return m


def _ctx(**kw):
    return types.SimpleNamespace(**kw)


def test_code_critic_pass_sets_verdict_true():
    for dep in ("verdict", "prompts", "generate", "guardrails", "gates", "report_schema",
                "report", "report_generator", "persona_schema"):
        _load(dep, dep)
    nodes = _load("nodes", "dc_nodes")
    class RC:
        def chat(self, role, messages, **kw): return "PASS"
    out = nodes.code_critic({"generated_code": "print(1)"}, _ctx(rc=RC()))
    assert out["critic_verdict"] is True


def test_code_critic_fail_sets_verdict_false():
    nodes = _load("nodes", "dc_nodes2")
    class RC:
        def chat(self, role, messages, **kw): return "FAIL missing plot"
    out = nodes.code_critic({"generated_code": "x=1"}, _ctx(rc=RC()))
    assert out["critic_verdict"] is False


def test_execute_code_records_cell_and_status():
    nodes = _load("nodes", "dc_nodes3")
    class K:
        def run(self, code): return {"status": "text", "stdout": "42", "figures": []}
    out = nodes.execute_code({"generated_code": "print(42)", "executed_cells": []}, _ctx(kernel=K()))
    assert out["exe_sign"] == "text"
    assert out["executed_cells"] == ["print(42)"]


def test_semantic_verify_accepts_non_business():
    for dep in ("verdict", "gates", "persona_schema"):
        _load(dep, dep)
    nodes = _load("nodes", "dc_nodes4")
    out = nodes.semantic_verify({"user_task": "df.head()", "generated_code": "c", "exe_result": "ok"}, _ctx(domain=None))
    assert out["verdict"]["status"] == "ACCEPT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_nodes.py -v`
Expected: FAIL (`nodes.py` not found).

- [ ] **Step 3: Write `nodes.py`**

Implement each node adapting the reference. Key bodies (fill the rest from `.reference/data-agent/langgraph_agent/nodes.py`, dropping `chat_history_display` streaming):

```python
"""LangGraph nodes for data_copilot. Adapted from
.reference/data-agent/langgraph_agent/nodes.py: pure (state, ctx) -> partial-state
functions. LLM calls bind to ctx.rc (RoleClient, non-streaming); code runs on
ctx.kernel (stateful). No chat_history_display — progress is emitted by the graph
driver to stderr.
"""
from __future__ import annotations

from typing import Any, Dict

from langgraph.types import interrupt  # type: ignore[import-not-found]

import gates  # type: ignore[import-not-found]
import prompts  # type: ignore[import-not-found]
import report_generator  # type: ignore[import-not-found]
import verdict as _verdict  # type: ignore[import-not-found]
from generate import extract_code  # type: ignore[import-not-found]
from guardrails import check_code  # type: ignore[import-not-found]


def generate_plan(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    prompt = prompts.PLANNER_PROMPT + f"\n\nUser Task: {state.get('user_task','')}"
    if state.get("review_feedback"):
        prompt += f"\n\nHuman Review Feedback: {state['review_feedback']}\nRevise the plan accordingly."
    plan = ctx.rc.chat("codegen", [{"role": "user", "content": prompt}])
    return {"analysis_plan": plan}


def human_review(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    decision = interrupt({"type": "plan_review", "plan": state.get("analysis_plan", "")})
    return {"review_feedback": decision}


def classify_review(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    prompt = prompts.CLASSIFIER_PROMPT.format(feedback=state.get("review_feedback", ""))
    resp = ctx.rc.chat("codegen", [{"role": "user", "content": prompt}]).upper()
    status = "APPROVE" if "APPROVE" in resp else ("CLARIFICATION" if "CLARIFICATION" in resp else "REJECT")
    history = state.get("review_history", [])
    history.append({"version": len(history) + 1, "feedback": state.get("review_feedback", ""), "status": status})
    return {"review_status": status, "review_history": history}


def generate_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    if state.get("critic_verdict") is False:
        msg = (f"The Code Critic rejected your code. Reason: {state.get('error_message','')}\n"
               "Write a corrected Python script based on the analysis plan.")
    else:
        msg = f"Generate the complete Python code to implement this plan:\n\n{state.get('analysis_plan','')}"
    text = ctx.rc.chat("codegen", [
        {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
        {"role": "user", "content": msg},
    ])
    _, code = extract_code(text)
    return {"generated_code": code or text}


def code_critic(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    resp = ctx.rc.chat("codegen", [{"role": "user",
        "content": prompts.CRITIC_PROMPT.format(code=state.get("generated_code", ""))}])
    if "FAIL" in resp.upper():
        return {"critic_verdict": False, "error_message": resp.replace("FAIL", "").strip()}
    return {"critic_verdict": True, "error_message": ""}


def execute_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    code = state.get("generated_code", "")
    if not code:
        return {"exe_sign": "error", "exe_result": "No code to execute.", "error_message": "Empty code block."}
    guard = check_code(code)
    if not guard["allowed"]:
        return {"exe_sign": "error", "exe_result": "GUARDRAIL: " + "; ".join(guard["reasons"])}
    res = ctx.kernel.run(code)
    cells = state.get("executed_cells", [])
    if res["status"] != "error":
        cells = cells + [code]
    return {"exe_sign": res["status"], "exe_result": res["stdout"],
            "executed_cells": cells, "figures": res.get("figures", [])}


def repair_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    attempts = state.get("syntax_attempts", 0)
    hyp = (gates.verify_syntax(state.get("generated_code", ""), state.get("exe_result", ""),
                               state.get("user_task", ""), lambda m: ctx.rc.chat("verify", m))
           if attempts < 3 else "Try other packages or methods.")
    fix_msg = (f"Fix this bug:\n{state.get('exe_result','')}\n\nSuggestion: {hyp}\n\n"
               "INCREMENTAL FIX: change only the lines needed; the kernel is stateful.")
    text = ctx.rc.chat("codegen", [
        {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
        {"role": "user", "content": fix_msg},
    ])
    _, new_code = extract_code(text)
    return {"generated_code": new_code or state.get("generated_code", ""),
            "syntax_attempts": attempts + 1, "inspector_hypotheses": hyp}


def semantic_verify(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    v = gates.verify_semantics(state.get("user_task", ""), state.get("generated_code", ""),
                               state.get("exe_result", ""), domain=getattr(ctx, "domain", None))
    return {"verdict": v, "semantic_attempts": state.get("semantic_attempts", 0)}


def semantic_fix(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    fb = state.get("verdict", {}).get("feedback", "")
    text = ctx.rc.chat("codegen", [
        {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
        {"role": "user", "content": prompts.SEMANTIC_FIX.format(feedback=fb)},
    ])
    _, new_code = extract_code(text)
    return {"generated_code": new_code or state.get("generated_code", ""),
            "semantic_attempts": state.get("semantic_attempts", 0) + 1}


def generate_report(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    out = state.get("exe_result", "")
    if state.get("exe_sign") == "error":
        out = (out + "\n\n[execution error]\n" + state.get("error_message", "")).strip()
    report = report_generator.compose(out, rc=ctx.rc, question=state.get("user_task", ""))
    return {"final_report": report}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_nodes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/nodes.py tests/test_data_copilot_nodes.py
git commit -m "feat(data_copilot): 10 graph nodes bound to RoleClient + stateful kernel"
```

### Task 10: `graph.py` — StateGraph + conditional edges + checkpointer

**Files:**
- Create: `modules/data_copilot/scripts/graph.py`
- Test: `tests/test_data_copilot_graph.py`

**Interfaces:**
- Consumes: `state.AgentState`, `nodes`, `langgraph.graph.StateGraph`, `langgraph.checkpoint.sqlite.SqliteSaver`.
- Produces:
  - Routing fns `_after_classify`, `_after_critic`, `_after_execute` (budget 4), `_after_verify` (budget 5) — verbatim logic from `.reference/data-agent/langgraph_agent/graph.py`.
  - `graph.build_graph(ctx, checkpointer) -> CompiledGraph` binding nodes via a closure over `ctx`.
  - `graph.SYNTAX_MAX = 4`, `graph.SEMANTIC_MAX = 5`.

- [ ] **Step 1: Write the failing test (routing only, no LLM)**

Create `tests/test_data_copilot_graph.py`:

```python
import importlib.util, sys
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[s] = m; spec.loader.exec_module(m); return m


def _graph():
    for dep in ("state", "verdict", "prompts", "generate", "guardrails", "gates",
                "report_schema", "report", "report_generator", "persona_schema", "nodes"):
        _load(dep, dep)
    return _load("graph", "dc_graph")


def test_after_execute_routes():
    g = _graph()
    assert g._after_execute({"exe_sign": "text"}) == "semantic_verify"
    assert g._after_execute({"exe_sign": "error", "syntax_attempts": 0}) == "repair_code"
    assert g._after_execute({"exe_sign": "error", "syntax_attempts": 4}) == "generate_report"


def test_after_verify_routes():
    g = _graph()
    assert g._after_verify({"verdict": {"status": "ACCEPT"}, "semantic_attempts": 0}) == "generate_report"
    assert g._after_verify({"verdict": {"status": "REVISE"}, "semantic_attempts": 0}) == "semantic_fix"
    assert g._after_verify({"verdict": {"status": "REVISE"}, "semantic_attempts": 5}) == "generate_report"


def test_after_classify_routes():
    g = _graph()
    assert g._after_classify({"review_status": "APPROVE"}) == "generate_code"
    assert g._after_classify({"review_status": "REJECT"}) == "generate_plan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_graph.py -v`
Expected: FAIL (`graph.py` not found).

- [ ] **Step 3: Write `graph.py`**

```python
"""LangGraph assembly for data_copilot. Mirrors
.reference/data-agent/langgraph_agent/graph.py: same nodes, same conditional
edges, same retry budgets (syntax 4, semantic 5). Nodes are bound to a ctx via
functools.partial so they stay pure.
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]

import nodes  # type: ignore[import-not-found]
from state import AgentState  # type: ignore[import-not-found]

SYNTAX_MAX = 4
SEMANTIC_MAX = 5


def _after_classify(state) -> str:
    return "generate_code" if state.get("review_status") == "APPROVE" else "generate_plan"


def _after_critic(state) -> str:
    return "execute_code" if state.get("critic_verdict") else "generate_code"


def _after_execute(state) -> str:
    sign = state.get("exe_sign", "")
    if sign and "error" not in sign:
        return "semantic_verify"
    if state.get("syntax_attempts", 0) >= SYNTAX_MAX:
        return "generate_report"
    return "repair_code"


def _after_verify(state) -> str:
    v = state.get("verdict", {})
    if v.get("status") == "ACCEPT" or state.get("semantic_attempts", 0) >= SEMANTIC_MAX:
        return "generate_report"
    return "semantic_fix"


def build_graph(ctx, checkpointer):
    """Compile the graph with nodes bound to ctx and the given checkpointer."""
    g = StateGraph(AgentState)
    for name in ("generate_plan", "human_review", "classify_review", "generate_code",
                 "code_critic", "execute_code", "repair_code", "semantic_verify",
                 "semantic_fix", "generate_report"):
        g.add_node(name, partial(getattr(nodes, name), ctx=ctx))
    g.set_entry_point("generate_plan")
    g.add_edge("generate_plan", "human_review")
    g.add_edge("human_review", "classify_review")
    g.add_conditional_edges("classify_review", _after_classify,
                            {"generate_code": "generate_code", "generate_plan": "generate_plan"})
    g.add_edge("generate_code", "code_critic")
    g.add_conditional_edges("code_critic", _after_critic,
                            {"execute_code": "execute_code", "generate_code": "generate_code"})
    g.add_conditional_edges("execute_code", _after_execute,
                            {"repair_code": "repair_code", "semantic_verify": "semantic_verify",
                             "generate_report": "generate_report"})
    g.add_edge("repair_code", "execute_code")
    g.add_conditional_edges("semantic_verify", _after_verify,
                            {"generate_report": "generate_report", "semantic_fix": "semantic_fix"})
    g.add_edge("semantic_fix", "execute_code")
    g.add_edge("generate_report", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_graph.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/graph.py tests/test_data_copilot_graph.py
git commit -m "feat(data_copilot): LangGraph StateGraph + conditional edges + budgets 4/5"
```

---

## Phase 6 — CLI + Atria

### Task 11: `copilot.py` — `run`/`resume` subcommands; retire `analyze`/`persona`

**Files:**
- Modify: `modules/data_copilot/scripts/copilot.py`
- Modify: `modules/data_copilot/scripts/paths.py` (add `checkpoint_db()`)
- Test: `tests/test_data_copilot_cli.py` (extend), `tests/test_data_copilot_run_resume.py` (new)

**Interfaces:**
- Consumes: `graph.build_graph`, `kernel.CodeKernel`, `profile.profile_dataset`, `ingest.resolve_dataset`, `SqliteSaver`, `RoleClient`, `load_config`.
- Produces:
  - `copilot.run_graph(dataset, question, *, out_dir, domain, k, thread_id, resume_feedback=None) -> dict` — starts or resumes the graph; returns `{"status":"awaiting_review","thread_id","plan"}` at the interrupt, or the final summary.
  - CLI: `run <dataset> <question> [--domain] [--k] [--out] [--thread]`; `resume --thread <id> --feedback <text>`.
  - Removes `analyze` and `persona` subcommands and `run_analysis`/`run_persona` dispatch.

- [ ] **Step 1: Add `paths.checkpoint_db`**

In `modules/data_copilot/scripts/paths.py` add:

```python
def checkpoint_db() -> Path:
    """SQLite path for the LangGraph checkpointer (session-scoped)."""
    return conversation_root() / "graph_checkpoints.sqlite"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_data_copilot_run_resume.py`:

```python
import importlib.util, json, sys
from pathlib import Path
_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[s] = m; spec.loader.exec_module(m); return m


def test_run_missing_dataset_is_clean_json(capsys):
    cop = _load("copilot", "dc_cli_run_err")
    rc = cop.main(["run", "/tmp/nope.csv", "segment"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and "error" in out


def test_resume_requires_thread(capsys):
    cop = _load("copilot", "dc_cli_resume_err")
    rc = cop.main(["resume", "--feedback", "approve"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and "error" in out
```

Add to `tests/test_data_copilot_cli.py`:

```python
def test_analyze_and_persona_removed():
    copilot = _load("copilot", "dc_cli_removed")
    parser = copilot.build_parser()
    subs = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert "run" in subs and "resume" in subs
    assert "analyze" not in subs and "persona" not in subs
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_run_resume.py tests/test_data_copilot_cli.py::test_analyze_and_persona_removed -v`
Expected: FAIL.

- [ ] **Step 4: Implement `run_graph` + CLI wiring**

In `copilot.py`, remove the `analyze`/`persona` subparsers, `run_analysis`, `run_persona`, `_cmd_analyze`, `_cmd_persona`, and their imports (`generate` stays — used by nodes indirectly? no; nodes import it themselves — remove unused). Add:

```python
def _new_thread_id(out_dir: str) -> str:
    """Stable thread id derived from the run dir name (unique per run)."""
    return Path(out_dir).name


def run_graph(dataset, question, *, out_dir, domain, k, thread_id, resume_feedback=None):
    import types
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
    from langgraph.types import Command  # type: ignore[import-not-found]

    import graph as graph_mod  # type: ignore[import-not-found]
    import kernel as kernel_mod  # type: ignore[import-not-found]

    dataset = str(Path(dataset).resolve())
    prof = profile_mod.profile_dataset(dataset)
    rc = RoleClient(load_config())
    krn = kernel_mod.CodeKernel(out_dir)
    ctx = types.SimpleNamespace(rc=rc, kernel=krn, profile=prof, dataset=dataset,
                                domain=domain, k=k)
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        with SqliteSaver.from_conn_string(str(paths_mod.checkpoint_db())) as saver:
            compiled = graph_mod.build_graph(ctx, saver)
            if resume_feedback is None:
                init = {"user_task": question, "executed_cells": [], "review_history": [],
                        "syntax_attempts": 0, "semantic_attempts": 0}
                stream = compiled.stream(init, config=cfg)
            else:
                krn.replay(compiled.get_state(cfg).values.get("executed_cells", []))
                stream = compiled.stream(Command(resume=resume_feedback), config=cfg)
            interrupted = None
            for step in stream:
                if "__interrupt__" in step:
                    interrupted = step["__interrupt__"][0].value
            snap = compiled.get_state(cfg)
            if interrupted:
                return {"status": "awaiting_review", "thread_id": thread_id,
                        "plan": interrupted.get("plan", "")}
            vals = snap.values
            return {"status": "done", "thread_id": thread_id, "dataset": dataset,
                    "question": question, "report": vals.get("final_report", ""),
                    "verdict": vals.get("verdict", {}), "figures": vals.get("figures", [])}
    finally:
        krn.shutdown()
```

Add `_cmd_run` / `_cmd_resume` (mirroring the existing `_cmd_*` clean-JSON-error pattern), wire subparsers `run` and `resume`, and dispatch in `main`. `run` computes `out_dir = args.out or _default_out_dir()` and `thread_id = _new_thread_id(out_dir)`; `resume` loads the run dir from the checkpoint's stored state (store `out_dir` in initial state as `run_dir`, resolve on resume). Wrap `run_graph` in try/except emitting `{"error": ...}`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_run_resume.py tests/test_data_copilot_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/data_copilot/scripts/copilot.py modules/data_copilot/scripts/paths.py tests/test_data_copilot_run_resume.py tests/test_data_copilot_cli.py
git commit -m "feat(data_copilot): run/resume graph CLI; retire analyze/persona"
```

### Task 12: SKILL.md — run/resume runbook

**Files:**
- Modify: `modules/data_copilot/SKILL.md`

- [ ] **Step 1: Replace the analyze/persona sections**

Rewrite the runbook so the agent-driven HITL is explicit. Replace the `analyze`/`persona` command lines with:

```markdown
### Analysis (graph flow with plan review)

1. `python <modules>/data_copilot/scripts/copilot.py run "<dataset path>" "<question>" [--domain telecom] [--k N]`
   → prints `{"status":"awaiting_review","thread_id":"...","plan":"..."}`.
2. Show the `plan` to the user verbatim and ask them to approve or request changes.
3. On the user's reply:
   `python <modules>/data_copilot/scripts/copilot.py resume --thread <thread_id> --feedback "<their reply>"`
   → if they approved, prints the final `{"status":"done","report":...,"figures":...,...}`;
     if they asked for changes, prints a new `{"status":"awaiting_review","plan":...}` — repeat step 2.
4. Surface the returned `report` (and any `figures`) to the user.
```

Keep `ingest`/`datasets`/`profile`/`audit` sections. Remove references to the retired `analyze`/`persona` commands.

- [ ] **Step 2: Verify no stale command references remain**

Run: `grep -n "analyze\|persona " modules/data_copilot/SKILL.md`
Expected: no lines invoking `copilot.py analyze` / `copilot.py persona`.

- [ ] **Step 3: Commit**

```bash
git add modules/data_copilot/SKILL.md
git commit -m "docs(data_copilot): SKILL runbook for run/resume plan-review flow"
```

### Task 13: `data_copilot_paths.py` — artifact resolvers

**Files:**
- Modify: `atria/core/modules/data_copilot_paths.py`
- Test: `tests/test_data_copilot_server_paths.py` (extend)

**Interfaces:**
- Produces: `report_path(session_id, working_dir, run_dir) -> Path`, `persona_json_path(session_id, working_dir, run_dir) -> Path`, `read_report(session_id, working_dir, run_dir) -> dict` (`{"report": str}` or raises `FileNotFoundError`) — all confined to the session root via the existing `_resolve_confined`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_copilot_server_paths.py`:

```python
def test_read_report_reads_markdown(tmp_path):
    from atria.core.modules import data_copilot_paths as dcp
    root = dcp.data_copilot_root("1", str(tmp_path))
    run = root / "runs" / "run-x"
    run.mkdir(parents=True)
    (run / "report.md").write_text("# R\nbody", encoding="utf-8")
    out = dcp.read_report("1", str(tmp_path), "runs/run-x")
    assert out["report"].startswith("# R")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_server_paths.py -k report -v`
Expected: FAIL (`read_report` not defined).

- [ ] **Step 3: Implement resolvers**

In `atria/core/modules/data_copilot_paths.py` add:

```python
def report_path(session_id: str, working_dir: str, run_dir: str) -> Path:
    """Absolute path to a run's report.md, confined to the session root."""
    return _resolve_confined(session_id, working_dir, f"{run_dir.rstrip('/')}/report.md")


def persona_json_path(session_id: str, working_dir: str, run_dir: str) -> Path:
    """Absolute path to a run's persona.json, confined to the session root."""
    return _resolve_confined(session_id, working_dir, f"{run_dir.rstrip('/')}/persona.json")


def read_report(session_id: str, working_dir: str, run_dir: str) -> Dict[str, Any]:
    """Read a run's report.md → {"report": str}. Raises FileNotFoundError if absent."""
    return {"report": report_path(session_id, working_dir, run_dir).read_text(encoding="utf-8")}
```

Note: `_resolve_confined` currently routes relative names under `data/`. Add a small branch so a `runs/...` relative path resolves under the root directly (not under `data/`): if `rel.startswith("runs/")`, resolve under `root` instead of `root/"data"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_server_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/core/modules/data_copilot_paths.py tests/test_data_copilot_server_paths.py
git commit -m "feat(atria): data_copilot artifact resolvers (report/persona) for run dirs"
```

### Task 14: `send_report` surfacing tool + enable it

**Files:**
- Create: `atria/core/context_engineering/tools/implementations/send_report_tool.py`
- Modify: `atria/core/agents/components/schemas/builtin/web_tools.py` (register schema)
- Modify: `atria/core/agents/components/schemas/disabled_tools.py` (ensure NOT disabled)
- Test: `tests/test_data_copilot_send_report.py`

**Interfaces:**
- Consumes: `data_copilot_paths.read_report`.
- Produces: a tool `send_report(session_id, run_dir)` that reads `report.md` and emits a chat `data_message`-style payload `{"type":"report","report": str, "run_dir": str}`. Follow the existing `send_table_tool.py` structure exactly (same handler signature, same broadcast mechanism).

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_copilot_send_report.py` mirroring `tests/` patterns for `send_table` (inspect that file first). Assert the handler returns a payload containing the report markdown given a stubbed `read_report`.

```python
def test_send_report_payload(monkeypatch, tmp_path):
    from atria.core.context_engineering.tools.implementations import send_report_tool as t
    monkeypatch.setattr(t.dcp, "read_report", lambda s, w, r: {"report": "# R"})
    # Build the tool's args/ctx the same way test_send_table does; assert payload.
    payload = t._build_payload(session_id="1", working_dir=str(tmp_path), run_dir="runs/run-x")
    assert payload["type"] == "report" and payload["report"] == "# R"
```

(Adjust to the real `send_table_tool` handler shape when implementing.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_send_report.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the tool**

Read `atria/core/context_engineering/tools/implementations/send_table_tool.py` and mirror its structure: a `_build_payload(...)` helper returning `{"type":"report","report":..., "run_dir":...}` and the registered async handler that resolves the working dir and broadcasts the payload. Register its schema in `web_tools.py` next to `send_table`.

- [ ] **Step 4: Ensure it is enabled**

Confirm `send_report` is not added to `disabled_tools.py`. (No change unless a default-disable rule would catch it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_send_report.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add atria/core/context_engineering/tools/implementations/send_report_tool.py atria/core/agents/components/schemas/builtin/web_tools.py atria/core/agents/components/schemas/disabled_tools.py tests/test_data_copilot_send_report.py
git commit -m "feat(atria): send_report tool to surface data_copilot report to chat"
```

### Task 15: report read endpoint

**Files:**
- Modify: `atria/web/routes/data_copilot.py`
- Test: `tests/test_data_copilot_route.py` (extend)

**Interfaces:**
- Consumes: `data_copilot_paths.read_report`, existing `_working_dir_for_session`.
- Produces: `GET /api/data-copilot/report?session_id=..&run_dir=..` → `{"report": str}`; 404 when absent.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_copilot_route.py` a test that overrides `_working_dir_for_session`, writes a `report.md` under the run dir, and asserts the endpoint returns the markdown (mirror the existing `test_write_then_read` setup). Note: this file currently fails to import due to an unrelated `lsp/ls_types.py` `NotRequired` bug on Python 3.10 — if that blocks collection, first apply the one-line fix `from typing_extensions import NotRequired` in `atria/core/context_engineering/tools/lsp/ls_types.py` and note it in the commit.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_route.py -k report -v`
Expected: FAIL.

- [ ] **Step 3: Implement the endpoint**

In `atria/web/routes/data_copilot.py` add:

```python
@router.get("/report")
async def report_endpoint(session_id: str = Query(...), run_dir: str = Query(...)) -> dict:
    working_dir = await _working_dir_for_session(session_id)
    try:
        return dcp.read_report(session_id, working_dir, run_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="report not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_copilot_route.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/web/routes/data_copilot.py tests/test_data_copilot_route.py
git commit -m "feat(atria): GET /api/data-copilot/report endpoint"
```

---

## Final verification

- [ ] **Full module suite**

Run: `uv run pytest tests/test_data_copilot_*.py -v`
Expected: all pass (pre-existing unrelated failures already addressed in Task 15 if the `ls_types` fix was applied).

- [ ] **Lint + format**

Run: `uv run ruff check modules/data_copilot/scripts/ atria/core/modules/data_copilot_paths.py atria/web/routes/data_copilot.py && uv run black --check modules/data_copilot/scripts/`
Expected: clean (apply `uv run black modules/data_copilot/scripts/` if needed).

- [ ] **E2E (requires `OPENAI_API_KEY`)** — per `CLAUDE.md`, run a real cycle:

```bash
export OPENAI_API_KEY=...
python modules/data_copilot/scripts/copilot.py ingest "<a churn csv>" --name churn
python modules/data_copilot/scripts/copilot.py run churn "segment customers into personas" --domain telecom
# capture thread_id from output, then:
python modules/data_copilot/scripts/copilot.py resume --thread <id> --feedback "approve"
```
Expected: `run` returns a plan; `resume` returns a 6-section telecom report.

---

## Self-review notes (author)

- **Spec coverage:** §3 files → Tasks 1–15; §4 flow → Tasks 9–10; §5 state → Task 1; §6 outputs → Tasks 3,4,6,7,11; §7 telecom verbatim → Tasks 5,7,8; §8 execution → Tasks 2,11; §9 Atria → Tasks 12–15; §11 testing → each task; §12 phasing → Phase headings.
- **Deferred (§10 web-native):** intentionally no tasks.
- **Type consistency:** verdict shape (`status`/`missing`/`feedback`/`epiplexity_score`) consistent across Tasks 1,5,9,10; node ctx attributes (`rc`,`kernel`,`domain`) consistent Tasks 9–11; `executed_cells` produced in Task 1, written in Task 9, replayed in Tasks 2,11.
- **Known verbatim gap:** Task 5 `gates.py` and Task 7 `report_generator.py` require copying the reference bodies exactly; the implementer must open the cited reference files and transcribe the gate/section logic (the plan shows structure + adaptations, not the full ~740 verbatim lines, to avoid divergence from the source of truth).
