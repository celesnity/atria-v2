# data_copilot Persona Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persona/clustering pipeline to `data_copilot` that persists a validated `persona.json` (plus a narrative report) as the final deliverable, invoked via a new `copilot.py persona` subcommand.

**Architecture:** Mirror the existing `run_analysis` generate→run→repair→verify loop in a new `run_persona` orchestrator that reuses the module's infra (`profile`, `sandbox`, `guardrails`, `client`, `charts`, `audit`, `paths`) through dependency injection. Four new modules add the persona-specific pieces: a code-gen prompt that forces a `[JSON_START_PERSONA]…[JSON_END_PERSONA]` block, a schema validator/extractor, a deterministic anti-hallucination verifier (domain-agnostic core + optional telecom pack), and a narrative report renderer.

**Tech Stack:** Python 3.10+, stdlib (`json`, `re`, `argparse`, `pathlib`), pandas/sklearn (only inside generated code run in the sandbox), OpenAI-compatible chat via the existing `RoleClient`. Tests: `pytest` via `uv run pytest`.

## Global Constraints

- Line length: 100 characters (Black + Ruff).
- Type hints required on public APIs; mypy strict mode.
- Google-style docstrings.
- Never hard-code if/else branching to steer LLM conversation flow (CLAUDE.md); the loop stays dynamic. The `persona` vs `analyze` choice is made by the *main agent*, not by a branch inside `analyze`.
- No system-prompt tables (CLAUDE.md); use prose/bullets.
- New scripts live in `modules/data_copilot/scripts/` and are imported flat (the CLI does `sys.path.insert(0, <scripts dir>)`), matching `import generate`, `import verify`, etc.
- Tests live in `tests/` named `test_data_copilot_persona_*.py`; load module files with the `importlib.util.spec_from_file_location` helper pattern used by existing tests.
- Persona field names match `.reference/data-agent` for compatibility.
- Testing per CLAUDE.md: unit tests (`uv run pytest`) AND real e2e with `OPENAI_API_KEY` are both required before claiming done.

---

### Task 1: Persona schema — extract + validate

**Files:**
- Create: `modules/data_copilot/scripts/persona_schema.py`
- Test: `tests/test_data_copilot_persona_schema.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `MARKER_START: str = "[JSON_START_PERSONA]"`, `MARKER_END: str = "[JSON_END_PERSONA]"`
  - `REQUIRED_FIELDS: tuple[str, ...]`
  - `extract_personas(stdout: str) -> list | None` — returns the parsed persona list from the last marker block, or `None` if absent/malformed.
  - `validate(personas: list) -> None` — raises `ValueError` describing the first violation; returns `None` when valid.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_schema.py
"""Tests for persona_schema.extract_personas + validate."""

import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_schema", base / "persona_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _valid_persona():
    return {
        "cluster_id": 0,
        "persona_name": "High-value loyalists",
        "support": 120,
        "support_pct": 0.4,
        "confidence": "HIGH",
        "priority_score": 0.9,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"tenure": 48.0},
        "profile_attributes": {"region": "North"},
        "recommended_actions": ["Upsell premium plan"],
        "sample_persona_text": "Long-tenure, high spend.",
    }


def test_extract_personas_reads_marker_block():
    mod = _load()
    stdout = (
        "noise\n"
        f"{mod.MARKER_START}\n"
        '[{"cluster_id": 0, "persona_name": "x"}]\n'
        f"{mod.MARKER_END}\n"
        "trailing\n"
    )
    got = mod.extract_personas(stdout)
    assert got == [{"cluster_id": 0, "persona_name": "x"}]


def test_extract_personas_returns_none_when_absent():
    mod = _load()
    assert mod.extract_personas("no markers here") is None


def test_extract_personas_returns_none_on_malformed_json():
    mod = _load()
    stdout = f"{mod.MARKER_START}\nnot json\n{mod.MARKER_END}"
    assert mod.extract_personas(stdout) is None


def test_validate_accepts_valid_personas():
    mod = _load()
    mod.validate([_valid_persona()])  # must not raise


def test_validate_rejects_empty_list():
    mod = _load()
    with pytest.raises(ValueError):
        mod.validate([])


def test_validate_rejects_missing_field():
    mod = _load()
    p = _valid_persona()
    del p["priority_score"]
    with pytest.raises(ValueError):
        mod.validate([p])


def test_validate_rejects_bad_support_pct():
    mod = _load()
    p = _valid_persona()
    p["support_pct"] = 1.5
    with pytest.raises(ValueError):
        mod.validate([p])


def test_validate_rejects_bad_confidence():
    mod = _load()
    p = _valid_persona()
    p["confidence"] = "SORT-OF"
    with pytest.raises(ValueError):
        mod.validate([p])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_schema.py -v`
Expected: FAIL with `ModuleNotFoundError`/`No such file` for `persona_schema.py`.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/persona_schema.py
"""Persona-block extraction + schema validation.

The generated clustering code prints its persona array as JSON wrapped in
``[JSON_START_PERSONA] … [JSON_END_PERSONA]`` markers (the contract enforced by
persona_verify). This module reads that block back and validates its shape.
Field names mirror .reference/data-agent for compatibility.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

MARKER_START = "[JSON_START_PERSONA]"
MARKER_END = "[JSON_END_PERSONA]"

REQUIRED_FIELDS = (
    "cluster_id",
    "persona_name",
    "support",
    "support_pct",
    "confidence",
    "priority_score",
    "is_anomaly",
    "segmentation_quality",
    "risk_tier",
    "evidence",
    "profile_attributes",
    "recommended_actions",
    "sample_persona_text",
)
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
_BLOCK_RE = re.compile(
    re.escape(MARKER_START) + r"\s*(.*?)\s*" + re.escape(MARKER_END),
    re.DOTALL,
)


def extract_personas(stdout: str) -> Optional[List[dict]]:
    """Parse the last persona JSON block from *stdout*.

    Args:
        stdout: Captured standard output of the generated code.

    Returns:
        The parsed list of persona dicts, or ``None`` when no well-formed
        marker block is present.
    """
    matches = _BLOCK_RE.findall(stdout or "")
    if not matches:
        return None
    try:
        parsed = json.loads(matches[-1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, list) else None


def validate(personas: List[dict]) -> None:
    """Validate a persona list, raising ``ValueError`` on the first violation.

    Args:
        personas: The parsed persona list.

    Raises:
        ValueError: If the list is empty or any persona is malformed.
    """
    if not isinstance(personas, list) or not personas:
        raise ValueError("persona list is empty or not a list")
    for i, p in enumerate(personas):
        if not isinstance(p, dict):
            raise ValueError(f"persona[{i}] is not an object")
        for field in REQUIRED_FIELDS:
            if field not in p:
                raise ValueError(f"persona[{i}] missing required field {field!r}")
        if not isinstance(p["support"], int) or p["support"] < 0:
            raise ValueError(f"persona[{i}].support must be a non-negative int")
        pct = p["support_pct"]
        if not isinstance(pct, (int, float)) or not 0.0 <= float(pct) <= 1.0:
            raise ValueError(f"persona[{i}].support_pct must be in [0, 1]")
        if p["confidence"] not in _CONFIDENCE:
            raise ValueError(f"persona[{i}].confidence must be one of {sorted(_CONFIDENCE)}")
        if not isinstance(p["priority_score"], (int, float)):
            raise ValueError(f"persona[{i}].priority_score must be numeric")
        if not isinstance(p["evidence"], dict):
            raise ValueError(f"persona[{i}].evidence must be an object")
        if not isinstance(p["recommended_actions"], list):
            raise ValueError(f"persona[{i}].recommended_actions must be a list")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_schema.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_schema.py tests/test_data_copilot_persona_schema.py
git commit -m "feat(data_copilot): persona schema extract + validate"
```

---

### Task 2: Persona verifier — deterministic anti-hallucination rules

**Files:**
- Create: `modules/data_copilot/scripts/persona_verify.py`
- Test: `tests/test_data_copilot_persona_verify.py`

**Interfaces:**
- Consumes: `persona_schema` (not required — operates on already-parsed personas + raw stdout).
- Produces:
  - `verify_personas(question: str, code: str, stdout: str, personas: list | None, *, domain: str | None = None) -> dict` returning `{"status": "OK"|"REVISE", "hypotheses": str, "warnings": list[str]}`.
  - Rule helpers (pure, individually testable): `check_json_present(stdout, personas) -> str | None`, `check_priority_formula(stdout, personas) -> str | None`, `check_evidence_present(personas) -> str | None`, `check_anomaly_gate(personas) -> list[str]`.
  - `load_domain_pack(name: str) -> list` — extra rule callables `(question, code, stdout, personas) -> str | None`; `telecom` supported, unknown name → `[]`.

Rationale: the reference verifier is largely deterministic rule-checks on the exec output, so no LLM call is needed here — this keeps the verify step fast and unit-testable. A `None` hypothesis from a rule means "passed".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_verify.py
"""Tests for persona_verify deterministic rules."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_verify", base / "persona_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _persona(**over):
    base = {
        "cluster_id": 0,
        "persona_name": "x",
        "support": 10,
        "support_pct": 0.5,
        "confidence": "HIGH",
        "priority_score": 0.5,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"tenure": 12.0},
        "profile_attributes": {},
        "recommended_actions": ["a"],
        "sample_persona_text": "t",
    }
    base.update(over)
    return base


def test_revise_when_no_persona_block():
    mod = _load()
    verdict = mod.verify_personas("q", "code", "no markers", None)
    assert verdict["status"] == "REVISE"
    assert "JSON" in verdict["hypotheses"]


def test_revise_when_priority_score_has_no_formula():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]"  # block present, but...
    verdict = mod.verify_personas("q", "code has no formula", stdout, [_persona()])
    assert verdict["status"] == "REVISE"
    assert "formula" in verdict["hypotheses"].lower() or "score" in verdict["hypotheses"].lower()


def test_ok_when_formula_present_and_evidence_ok():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\npriority_score = revenue * churn_rate"
    verdict = mod.verify_personas("q", "priority_score = revenue * churn_rate", stdout,
                                  [_persona()])
    assert verdict["status"] == "OK"


def test_revise_when_evidence_empty():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\nscore = a * b"
    verdict = mod.verify_personas("q", "score = a * b", stdout, [_persona(evidence={})])
    assert verdict["status"] == "REVISE"


def test_anomaly_gate_warns_on_tiny_cluster():
    mod = _load()
    warnings = mod.check_anomaly_gate([_persona(support_pct=0.005, is_anomaly=False)])
    assert warnings and "anomaly" in warnings[0].lower()


def test_load_domain_pack_telecom_returns_rules():
    mod = _load()
    assert len(mod.load_domain_pack("telecom")) >= 1
    assert mod.load_domain_pack("unknown") == []


def test_telecom_pack_flags_causal_hallucination():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\nscore = a*b\nNguyên nhân rời mạng do khuyến mãi"
    verdict = mod.verify_personas("q", "score=a*b", stdout, [_persona()], domain="telecom")
    assert verdict["status"] == "REVISE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_verify.py -v`
Expected: FAIL — `persona_verify.py` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/persona_verify.py
"""Deterministic anti-hallucination verification for persona output.

Ported (domain-agnostic subset) from .reference/data-agent's SemanticVerifier:
the checks run on the parsed personas plus the raw stdout, so the step needs no
LLM call. Each rule returns a hypothesis string when it fails, else ``None``.
An optional domain pack (``telecom``) appends stricter, domain-specific rules.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

import persona_schema  # type: ignore[import-not-found]

Rule = Callable[[str, str, str, Optional[List[dict]]], Optional[str]]

# A priority/opportunity score must be accompanied by an explainable formula.
_FORMULA_RE = re.compile(r"(?i)(công thức|formula|=|\*|score\s*=)")
# Telecom pack: forbidden causal claims (no external-cause hallucination).
_CAUSAL_TERMS = ("khuyến mãi", "promotion", "đối thủ", "cạnh tranh", "marketing")


def check_json_present(stdout: str, personas: Optional[List[dict]]) -> Optional[str]:
    """Fail if the persona marker block / parsed list is missing."""
    if persona_schema.MARKER_START not in (stdout or ""):
        return (
            "No persona JSON block found. You MUST print "
            f"'{persona_schema.MARKER_START}', then json.dumps(personas), then "
            f"'{persona_schema.MARKER_END}'."
        )
    if not personas:
        return "The persona JSON block is present but empty or unparseable."
    return None


def check_priority_formula(stdout: str, personas: Optional[List[dict]]) -> Optional[str]:
    """Fail if any priority_score is emitted without an explainable formula."""
    if not personas:
        return None
    if any("priority_score" in p for p in personas) and not _FORMULA_RE.search(stdout or ""):
        return (
            "priority_score is reported without an explainable formula. Print the "
            "formula used (e.g. priority_score = support_pct * risk_weight)."
        )
    return None


def check_evidence_present(personas: Optional[List[dict]]) -> Optional[str]:
    """Fail if any persona carries no evidence features."""
    if not personas:
        return None
    for p in personas:
        if not p.get("evidence"):
            return (
                f"persona cluster_id={p.get('cluster_id')} has empty evidence; each "
                "persona must list the features that distinguish it."
            )
    return None


def check_anomaly_gate(personas: Optional[List[dict]]) -> List[str]:
    """Warn (non-blocking) about tiny clusters not flagged as anomalies."""
    warnings: List[str] = []
    for p in personas or []:
        pct = p.get("support_pct", 0)
        if isinstance(pct, (int, float)) and pct < 0.01 and not p.get("is_anomaly"):
            warnings.append(
                f"Anomaly gate: cluster_id={p.get('cluster_id')} covers "
                f"{float(pct) * 100:.2f}% of data but is_anomaly is false."
            )
    return warnings


def _telecom_no_causal(
    question: str, code: str, stdout: str, personas: Optional[List[dict]]
) -> Optional[str]:
    hit = [t for t in _CAUSAL_TERMS if t in (stdout or "").lower()]
    if hit:
        return (
            "Causal hallucination: do not attribute churn to "
            f"{', '.join(hit)}. This dataset only has behavioural/technical fields."
        )
    return None


def load_domain_pack(name: str) -> List[Rule]:
    """Return extra rule callables for *name* (``telecom`` supported)."""
    if name == "telecom":
        return [_telecom_no_causal]
    return []


def verify_personas(
    question: str,
    code: str,
    stdout: str,
    personas: Optional[List[dict]],
    *,
    domain: Optional[str] = None,
) -> dict:
    """Run all rules and return a verdict.

    Args:
        question: The user's question.
        code: The generated code that produced *stdout*.
        stdout: Captured standard output.
        personas: The parsed persona list (or ``None`` if extraction failed).
        domain: Optional domain pack name (e.g. ``"telecom"``).

    Returns:
        ``{"status": "OK"|"REVISE", "hypotheses": str, "warnings": list[str]}``.
    """
    core: List[Optional[str]] = [
        check_json_present(stdout, personas),
        check_priority_formula(stdout, personas),
        check_evidence_present(personas),
    ]
    for rule in load_domain_pack(domain or ""):
        core.append(rule(question, code, stdout, personas))
    hypotheses = [h for h in core if h]
    warnings = check_anomaly_gate(personas)
    if hypotheses:
        return {"status": "REVISE", "hypotheses": " ".join(hypotheses), "warnings": warnings}
    return {"status": "OK", "hypotheses": "", "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_verify.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_verify.py tests/test_data_copilot_persona_verify.py
git commit -m "feat(data_copilot): deterministic persona verifier + telecom pack"
```

---

### Task 3: Persona code generation prompt

**Files:**
- Create: `modules/data_copilot/scripts/persona_generate.py`
- Test: `tests/test_data_copilot_persona_generate.py`

**Interfaces:**
- Consumes: `generate.extract_code` (reused for fenced-block parsing — DRY), `persona_schema.MARKER_START`/`MARKER_END`.
- Produces:
  - `build_messages(question, profile, *, k=None, domain=None, prior_error=None, hypotheses=None) -> list[dict]`
  - `generate_code(question, profile, chat_fn, *, k=None, domain=None, prior_error=None, hypotheses=None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_generate.py
"""Tests for persona_generate prompt building + code extraction."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_generate", base / "persona_generate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_build_messages_mentions_markers_and_schema():
    mod = _load()
    msgs = mod.build_messages("segment customers", {"path": "d.csv", "columns": []})
    system = msgs[0]["content"]
    assert "[JSON_START_PERSONA]" in system and "[JSON_END_PERSONA]" in system
    assert "persona_name" in system and "priority_score" in system


def test_build_messages_injects_k_and_repair_context():
    mod = _load()
    msgs = mod.build_messages(
        "seg", {"path": "d.csv", "columns": []}, k=4,
        prior_error="Boom", hypotheses="add evidence",
    )
    user = msgs[1]["content"]
    assert "4" in user and "Boom" in user and "add evidence" in user


def test_build_messages_telecom_domain_adds_guidance():
    mod = _load()
    base = mod.build_messages("seg", {"path": "d.csv", "columns": []})[0]["content"]
    tele = mod.build_messages("seg", {"path": "d.csv", "columns": []}, domain="telecom")[0][
        "content"
    ]
    assert len(tele) > len(base)


def test_generate_code_extracts_fenced_block():
    mod = _load()
    chat = lambda messages: "text\n```python\nprint('hi')\n```\n"
    code = mod.generate_code("seg", {"path": "d.csv", "columns": []}, chat)
    assert "print('hi')" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_generate.py -v`
Expected: FAIL — `persona_generate.py` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/persona_generate.py
"""Generate clustering/persona code from a question + dataset profile.

Extends the plain codegen prompt (generate.py) with a strict output contract:
the script must cluster the dataset and print a persona array as JSON wrapped in
``[JSON_START_PERSONA] … [JSON_END_PERSONA]`` using the schema in persona_schema.
Domain-agnostic; the telecom domain appends extra guidance.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from generate import extract_code  # type: ignore[import-not-found]
from persona_schema import MARKER_END, MARKER_START  # type: ignore[import-not-found]

_SYSTEM = (
    "You are a senior data scientist. Write ONE self-contained Python script that "
    "segments the dataset into customer personas (clusters) and reports them. "
    "Rules: use pandas and scikit-learn; load the dataset from the exact path "
    "given; scale numeric features and choose a sensible cluster count "
    "(silhouette-guided) unless a count is specified; for each cluster compute "
    "support (row count) and support_pct (fraction of rows). Build a list "
    "`personas` where each item is a dict with EXACTLY these keys: cluster_id "
    "(int), persona_name (str), support (int), support_pct (float 0..1), "
    "confidence ('HIGH'|'MEDIUM'|'LOW'), priority_score (float), is_anomaly "
    "(bool), segmentation_quality (str), risk_tier (str), evidence (dict of the "
    "distinguishing features -> cluster mean, only features that deviate notably "
    "from the global mean), profile_attributes (dict), recommended_actions (list "
    "of str), sample_persona_text (str). PRINT the formula you use for "
    "priority_score in plain text. Then print the markers and JSON exactly:\n"
    f"print('{MARKER_START}')\n"
    "print(json.dumps(personas, ensure_ascii=False))\n"
    f"print('{MARKER_END}')\n"
    "Also save a flat one-row-per-persona table to 'result.csv' "
    "(df.to_csv('result.csv', index=False), <= 50 rows). Do NOT access the "
    "network, spawn processes, or write outside the current directory. Return the "
    "code in one ```python``` block."
)
_TELECOM = (
    " Domain: telecom churn. Only use behavioural/technical fields already in the "
    "data; NEVER attribute churn to promotions, competitors, or marketing. Do not "
    "label raw metrics (e.g. dBm) as 'good'/'bad' — report the value."
)


def build_messages(
    question: str,
    profile: dict,
    *,
    k: Optional[int] = None,
    domain: Optional[str] = None,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> List[dict]:
    """Build code-generation chat messages for the persona pipeline.

    Args:
        question: The user's natural-language segmentation request.
        profile: Dataset profile from ``profile.profile_dataset``.
        k: Optional fixed cluster count.
        domain: Optional domain pack name (e.g. ``"telecom"``).
        prior_error: Traceback from a failed run, to drive repair.
        hypotheses: Verifier hypotheses, to drive revision.

    Returns:
        OpenAI-format message list.
    """
    system = _SYSTEM + (_TELECOM if domain == "telecom" else "")
    prof_json = json.dumps(
        {key: profile[key] for key in ("path", "n_rows", "n_cols", "columns", "sample")
         if key in profile},
        default=str,
    )
    user = (
        f"Dataset path: {profile.get('path')}\n"
        f"Dataset profile (JSON):\n{prof_json}\n\n"
        f"Request: {question}\n"
    )
    if k is not None:
        user += f"\nUse exactly k={k} clusters.\n"
    if prior_error:
        user += f"\nThe previous code failed with this error — fix it:\n{prior_error}\n"
    if hypotheses:
        user += f"\nA verifier rejected the previous result. Address:\n{hypotheses}\n"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_code(
    question: str,
    profile: dict,
    chat_fn: Callable[[List[dict]], str],
    *,
    k: Optional[int] = None,
    domain: Optional[str] = None,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> str:
    """Generate persona clustering code, returning the extracted Python.

    Args:
        question: The user's request.
        profile: Dataset profile.
        chat_fn: Callable mapping messages -> model text (bound to the codegen role).
        k: Optional fixed cluster count.
        domain: Optional domain pack name.
        prior_error: Optional error from a prior run.
        hypotheses: Optional verifier hypotheses.

    Returns:
        The extracted Python code; if no fenced block is present, the raw text.
    """
    messages = build_messages(
        question, profile, k=k, domain=domain, prior_error=prior_error, hypotheses=hypotheses
    )
    text = chat_fn(messages)
    found, code = extract_code(text)
    return code if found else text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_generate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_generate.py tests/test_data_copilot_persona_generate.py
git commit -m "feat(data_copilot): persona clustering codegen prompt"
```

---

### Task 4: Persona narrative report

**Files:**
- Create: `modules/data_copilot/scripts/persona_report.py`
- Test: `tests/test_data_copilot_persona_report.py`

**Interfaces:**
- Consumes: a report-role `chat_fn` (like `report.generate_report`).
- Produces:
  - `build_messages(personas: list, question: str) -> list[dict]`
  - `render_report(personas: list, question: str, chat_fn, *, verified: bool = True) -> str` — ranks personas by `priority_score` (desc), asks the model for a grounded narrative, and returns markdown; prepends the shared UNVERIFIED banner when `verified` is `False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_report.py
"""Tests for persona_report narrative rendering."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_report", base / "persona_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _p(cid, name, score):
    return {
        "cluster_id": cid, "persona_name": name, "support": 10, "support_pct": 0.5,
        "confidence": "HIGH", "priority_score": score, "is_anomaly": False,
        "segmentation_quality": "NORMAL", "risk_tier": "LOW", "evidence": {"a": 1.0},
        "profile_attributes": {}, "recommended_actions": ["do x"], "sample_persona_text": "t",
    }


def test_build_messages_ranks_by_priority_desc():
    mod = _load()
    msgs = mod.build_messages([_p(0, "low", 0.1), _p(1, "high", 0.9)], "segment")
    user = msgs[1]["content"]
    assert user.index('"high"') < user.index('"low"')


def test_render_report_returns_model_body_when_verified():
    mod = _load()
    out = mod.render_report([_p(0, "x", 0.5)], "q", lambda m: "# Personas\nbody", verified=True)
    assert out == "# Personas\nbody"


def test_render_report_prepends_unverified_banner():
    mod = _load()
    out = mod.render_report([_p(0, "x", 0.5)], "q", lambda m: "body", verified=False)
    assert "UNVERIFIED" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_report.py -v`
Expected: FAIL — `persona_report.py` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/persona_report.py
"""Compose a grounded Markdown persona report from validated personas.

Ported (simplified) from .reference/data-agent's report_generator: personas are
ranked by priority_score and the model writes a grounded narrative — no invented
numbers. The report role's chat_fn does the writing (no instructor dependency).
"""

from __future__ import annotations

import json
from typing import Callable, List

from report import _UNVERIFIED  # type: ignore[import-not-found]

_SYSTEM = (
    "You are a data analyst writing a concise Markdown persona report for "
    "executives. Ground every statement in the provided persona JSON — do not "
    "invent numbers. For each persona give a short business interpretation, its "
    "priority, and the recommended actions. End with a one-paragraph conclusion. "
    "No tables."
)


def build_messages(personas: List[dict], question: str) -> List[dict]:
    """Build the report chat messages with personas ranked by priority_score.

    Args:
        personas: The validated persona list.
        question: The user's original request.

    Returns:
        OpenAI-format message list.
    """
    ranked = sorted(personas, key=lambda p: p.get("priority_score", 0), reverse=True)
    user = (
        f"Request: {question}\n\n"
        f"Personas (ranked by priority, JSON):\n{json.dumps(ranked, ensure_ascii=False)}\n"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def render_report(
    personas: List[dict],
    question: str,
    chat_fn: Callable[[List[dict]], str],
    *,
    verified: bool = True,
) -> str:
    """Render the persona narrative markdown.

    Args:
        personas: The validated persona list.
        question: The user's request.
        chat_fn: Callable mapping messages -> model text (bound to the report role).
        verified: When ``False``, prepend the shared UNVERIFIED banner.

    Returns:
        The Markdown report string.
    """
    body = chat_fn(build_messages(personas, question))
    return body if verified else _UNVERIFIED + body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_report.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona_report.py tests/test_data_copilot_persona_report.py
git commit -m "feat(data_copilot): persona narrative report renderer"
```

---

### Task 5: Persona orchestrator — `run_persona`

**Files:**
- Create: `modules/data_copilot/scripts/persona.py`
- Test: `tests/test_data_copilot_persona_orchestrator.py`

**Interfaces:**
- Consumes: `persona_schema.extract_personas`/`validate`, `charts.detect_suggestions`, `audit.append_event`, `sandbox.run_code`, `guardrails.check_code`, `profile.profile_dataset`, and the injected `codegen_fn`/`verify_fn`/`report_fn`.
- Produces:
  - `run_persona(dataset, question, *, out_dir, max_repair, max_verify, codegen_fn, verify_fn, report_fn, profile_fn=profile.profile_dataset, guard_fn=guardrails.check_code, exec_fn=sandbox.run_code, domain=None, k=None, timeout=30.0, max_output=20000) -> dict`
  - `codegen_fn(question, profile, prior_error, hypotheses) -> str`
  - `verify_fn(question, code, stdout, personas) -> {"status","hypotheses","warnings"}`
  - `report_fn(personas, question, verified) -> str`
  - Summary dict keys: `dataset, question, domain, code, status, verified, verdict, personas, persona_json, report, figures, result_table, suggestions, repairs, verify_rounds`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_orchestrator.py
"""Tests for run_persona: artifact writing, verify loop, summary shape."""

import importlib.util
import json
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona", base / "persona.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_PERSONAS = [{
    "cluster_id": 0, "persona_name": "x", "support": 10, "support_pct": 0.5,
    "confidence": "HIGH", "priority_score": 0.5, "is_anomaly": False,
    "segmentation_quality": "NORMAL", "risk_tier": "LOW", "evidence": {"a": 1.0},
    "profile_attributes": {}, "recommended_actions": ["do x"], "sample_persona_text": "t",
}]


def _stdout():
    return "[JSON_START_PERSONA]\n" + json.dumps(_PERSONAS) + "\n[JSON_END_PERSONA]"


def test_run_persona_writes_persona_json_and_summary(tmp_path):
    mod = _load()
    out = tmp_path / "run"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        (Path(out_dir) / "result.csv").write_text("persona_name,support\nx,10\n", encoding="utf-8")
        return {"status": "ok", "stdout": _stdout(), "stderr": "", "figures": [], "returncode": 0}

    summary = mod.run_persona(
        dataset=str(tmp_path / "in.csv"), question="segment", out_dir=str(out),
        max_repair=0, max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o, personas: {"status": "OK", "hypotheses": "", "warnings": []},
        report_fn=lambda personas, q, verified=True: "# report",
        profile_fn=lambda ds: {"path": ds, "columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    persona_json = out / "persona.json"
    assert persona_json.is_file()
    assert json.loads(persona_json.read_text())[0]["persona_name"] == "x"
    assert summary["persona_json"] == str(persona_json.resolve())
    assert summary["personas"] == _PERSONAS
    assert summary["verified"] is True
    assert summary["result_table"] == str((out / "result.csv").resolve())
    assert summary["suggestions"]  # bar chart from persona_name/support


def test_run_persona_unverified_when_block_missing(tmp_path):
    mod = _load()
    out = tmp_path / "run2"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        return {"status": "ok", "stdout": "no personas", "stderr": "", "figures": [],
                "returncode": 0}

    summary = mod.run_persona(
        dataset=str(tmp_path / "in.csv"), question="segment", out_dir=str(out),
        max_repair=0, max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o, personas: {
            "status": "REVISE", "hypotheses": "no block", "warnings": []},
        report_fn=lambda personas, q, verified=True: "# report",
        profile_fn=lambda ds: {"path": ds, "columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    assert summary["verified"] is False
    assert summary["personas"] == []
    assert summary["persona_json"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_orchestrator.py -v`
Expected: FAIL — `persona.py` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# modules/data_copilot/scripts/persona.py
"""Persona pipeline orchestrator.

Mirrors copilot.run_analysis: profile -> generate clustering code -> run in the
sandbox -> repair on execution error -> extract + verify personas -> persist
persona.json + a narrative report. All external steps are injectable so the loop
is unit-testable without an LLM or a subprocess. The loop stays dynamic (no
hard-coded control flow steering the model).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

import audit  # type: ignore[import-not-found]
import charts as charts_mod  # type: ignore[import-not-found]
import guardrails  # type: ignore[import-not-found]
import persona_schema  # type: ignore[import-not-found]
import profile as profile_mod  # type: ignore[import-not-found]
import sandbox  # type: ignore[import-not-found]


def _load_result_table(out_dir: str):
    """Read result.csv from *out_dir* into (columns, rows) or None.

    Delegates to copilot._load_result_table to avoid duplicating the CSV/typing
    logic (DRY).
    """
    import copilot  # type: ignore[import-not-found]

    return copilot._load_result_table(out_dir)


def _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn, exec_fn,
                 prior_error, hypotheses, timeout, max_output):
    """Generate code, screen it, and (if allowed) execute it once."""
    code = codegen_fn(question, prof, prior_error, hypotheses)
    guard = guard_fn(code)
    if not guard["allowed"]:
        return code, {
            "status": "error", "stdout": "", "stderr": "GUARDRAIL: " + "; ".join(guard["reasons"]),
            "figures": [], "returncode": None,
        }
    return code, exec_fn(code, out_dir, timeout, max_output)


def run_persona(
    dataset: str,
    question: str,
    *,
    out_dir: str,
    max_repair: int,
    max_verify: int,
    codegen_fn: Callable,
    verify_fn: Callable,
    report_fn: Callable,
    profile_fn: Callable = profile_mod.profile_dataset,
    guard_fn: Callable = guardrails.check_code,
    exec_fn: Callable = sandbox.run_code,
    domain: Optional[str] = None,
    k: Optional[int] = None,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run the persona clustering loop and append an audit event.

    Args:
        dataset: Path to (or resolved name of) the dataset.
        question: The user's segmentation request.
        out_dir: Per-run output directory (persona.json/result.csv land here).
        max_repair: Max execution-error repair attempts.
        max_verify: Max verifier REVISE rounds.
        codegen_fn: ``(question, profile, prior_error, hypotheses) -> code``.
        verify_fn: ``(question, code, stdout, personas) -> verdict``.
        report_fn: ``(personas, question, verified) -> markdown``.
        profile_fn, guard_fn, exec_fn: injectable deps.
        domain: Optional domain pack name (threaded to audit/summary).
        k: Optional fixed cluster count (unused here; codegen_fn closes over it).
        timeout, max_output: sandbox bounds.

    Returns:
        The persona summary dict (see the plan's Interfaces block).
    """
    dataset = str(Path(dataset).resolve())
    prof = profile_fn(dataset)
    prior_error: Optional[str] = None
    hypotheses: Optional[str] = None
    verify_round = 0
    repairs = 0
    verdict: Dict[str, object] = {"status": "REVISE", "hypotheses": "", "warnings": []}
    code = ""
    result = {"status": "error", "stdout": "", "stderr": "", "figures": [], "returncode": None}
    personas: List[dict] = []
    unverified = True

    while True:
        code, result = _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn, exec_fn,
                                    prior_error, hypotheses, timeout, max_output)
        prior_error = None
        hypotheses = None
        while result["status"] == "error" and repairs < max_repair:
            repairs += 1
            code, result = _gen_and_run(question, prof, out_dir, codegen_fn, guard_fn, exec_fn,
                                        result["stderr"], None, timeout, max_output)
        if result["status"] == "error":
            verdict = {"status": "REVISE",
                       "hypotheses": "code could not be made to run: " + result["stderr"],
                       "warnings": []}
            unverified = True
            break
        personas = persona_schema.extract_personas(result["stdout"]) or []
        verdict = verify_fn(question, code, result["stdout"], personas)
        if verdict["status"] == "OK":
            unverified = False
            break
        verify_round += 1
        if verify_round > max_verify:
            unverified = True
            break
        hypotheses = str(verdict.get("hypotheses", ""))

    persona_json_path: Optional[str] = None
    report_md = ""
    if not unverified and personas:
        try:
            persona_schema.validate(personas)
            path = Path(out_dir) / "persona.json"
            path.write_text(json.dumps(personas, ensure_ascii=False, indent=2), encoding="utf-8")
            persona_json_path = str(path.resolve())
            report_md = report_fn(personas, question, verified=True)
        except ValueError as exc:
            unverified = True
            verdict = {"status": "REVISE", "hypotheses": f"schema invalid: {exc}",
                       "warnings": verdict.get("warnings", [])}
    if unverified:
        report_md = report_fn(personas, question, verified=False) if personas else (
            "> ⚠️ **UNVERIFIED** — no valid persona output was produced.")

    result_table_path: Optional[str] = None
    suggestions: List[dict] = []
    loaded = _load_result_table(out_dir)
    if loaded is not None:
        columns, rows = loaded
        suggestions = charts_mod.detect_suggestions(columns, rows)
        (Path(out_dir) / "result.meta.json").write_text(
            json.dumps({"columns": columns, "suggestions": suggestions}, default=str),
            encoding="utf-8")
        result_table_path = str((Path(out_dir) / "result.csv").resolve())

    audit.append_event({
        "type": "persona", "dataset": dataset, "question": question, "domain": domain,
        "verified": not unverified, "status": result["status"], "repairs": repairs,
        "verify_rounds": verify_round, "n_personas": len(personas), "verdict": verdict,
        "figures": result["figures"],
    })
    return {
        "dataset": dataset, "question": question, "domain": domain, "code": code,
        "status": result["status"], "verified": not unverified, "verdict": verdict,
        "personas": personas, "persona_json": persona_json_path, "report": report_md,
        "figures": result["figures"], "result_table": result_table_path,
        "suggestions": suggestions, "repairs": repairs, "verify_rounds": verify_round,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_orchestrator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/data_copilot/scripts/persona.py tests/test_data_copilot_persona_orchestrator.py
git commit -m "feat(data_copilot): persona pipeline orchestrator (run_persona)"
```

---

### Task 6: Wire the `persona` CLI subcommand

**Files:**
- Modify: `modules/data_copilot/scripts/copilot.py` (imports near line 27-38; add `_cmd_persona`; add parser near line 379-388; add dispatch near line 413-422)
- Test: `tests/test_data_copilot_persona_cli.py`

**Interfaces:**
- Consumes: `persona.run_persona`, `persona_generate.generate_code`, `persona_verify.verify_personas`, `persona_report.render_report`, `RoleClient`, `load_config`, `ingest_mod.resolve_dataset`.
- Produces: `_cmd_persona(dataset, question, out_dir, max_repair, max_verify, domain, k) -> int` and a `persona` subparser.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_copilot_persona_cli.py
"""Tests the `persona` subcommand parses and dispatches to run_persona."""

import importlib.util
import json
import sys
from pathlib import Path


def _load_copilot():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_copilot", base / "copilot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_parser_has_persona_subcommand():
    cop = _load_copilot()
    args = cop.build_parser().parse_args(
        ["persona", "data.csv", "segment customers", "--domain", "telecom", "--k", "4"])
    assert args.command == "persona"
    assert args.dataset == "data.csv"
    assert args.question == "segment customers"
    assert args.domain == "telecom"
    assert args.k == 4


def test_persona_requires_question(capsys):
    cop = _load_copilot()
    rc = cop._cmd_persona("data.csv", None, "out", 0, 0, None, None)
    assert rc == 1
    assert "question is required" in json.loads(capsys.readouterr().out)["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_copilot_persona_cli.py -v`
Expected: FAIL — no `persona` subcommand / no `_cmd_persona`.

- [ ] **Step 3: Write minimal implementation**

Add to the imports block (after `import verify as verify_mod` ~line 36):

```python
import persona as persona_mod  # type: ignore[import-not-found]
import persona_generate  # type: ignore[import-not-found]
import persona_report  # type: ignore[import-not-found]
import persona_verify  # type: ignore[import-not-found]
```

Add `_cmd_persona` after `_cmd_analyze` (~line 353):

```python
def _cmd_persona(
    dataset: str,
    question: Optional[str],
    out_dir: str,
    max_repair: int,
    max_verify: int,
    domain: Optional[str],
    k: Optional[int],
) -> int:
    if not question or not question.strip():
        print(json.dumps({"error": "a question is required: "
                          'persona "<dataset path or name>" "<your question>"'}, indent=2))
        return 1
    try:
        dataset = ingest_mod.resolve_dataset(dataset)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    rc = RoleClient(load_config())
    summary = persona_mod.run_persona(
        dataset,
        question,
        out_dir=out_dir,
        max_repair=max_repair,
        max_verify=max_verify,
        domain=domain,
        k=k,
        codegen_fn=lambda q, p, pe=None, hy=None: persona_generate.generate_code(
            q, p, _role_chat(rc, "codegen"), k=k, domain=domain, prior_error=pe, hypotheses=hy),
        verify_fn=lambda q, c, o, personas: persona_verify.verify_personas(
            q, c, o, personas, domain=domain),
        report_fn=lambda personas, q, verified=True: persona_report.render_report(
            personas, q, _role_chat(rc, "report"), verified=verified),
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0
```

Add the subparser after the `analyze` block (~line 386):

```python
    p_per = sub.add_parser("persona", help="Cluster the dataset into personas (writes persona.json).")
    p_per.add_argument("dataset")
    p_per.add_argument("question", nargs="?", default=None)
    p_per.add_argument("--out", default=None, help="Run output dir (default: runs/latest).")
    p_per.add_argument("--max-repair", type=int, default=3)
    p_per.add_argument("--max-verify", type=int, default=2)
    p_per.add_argument("--domain", default=None, help="Optional domain pack (e.g. telecom).")
    p_per.add_argument("--k", type=int, default=None, help="Optional fixed cluster count.")
```

Add dispatch after the `analyze` branch in `main` (~line 420):

```python
    if args.command == "persona":
        return _cmd_persona(
            args.dataset, args.question, args.out or _default_out_dir(),
            args.max_repair, args.max_verify, args.domain, args.k,
        )
```

Also update the module docstring subcommand list (line 4-14) to mention `persona`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_copilot_persona_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full data_copilot suite to catch regressions**

Run: `uv run pytest tests/ -k data_copilot -q`
Expected: PASS (all existing + new persona tests).

- [ ] **Step 6: Commit**

```bash
git add modules/data_copilot/scripts/copilot.py tests/test_data_copilot_persona_cli.py
git commit -m "feat(data_copilot): wire persona subcommand into CLI"
```

---

### Task 7: SKILL.md guidance for the persona pipeline

**Files:**
- Modify: `modules/data_copilot/SKILL.md` (add a "Persona / clustering" subsection after the Runbook; extend the Commands reference)

**Interfaces:**
- Consumes: nothing (docs).
- Produces: agent-facing guidance so the main agent picks `persona` for segmentation questions and presents `persona.json`.

- [ ] **Step 1: Add the guidance section**

Insert after the Runbook section (before "## Commands (reference)"):

```markdown
## Persona / customer segmentation

When the user asks to **cluster / segment customers or build personas**
("phân cụm", "persona", "segment", "customer groups"), use `persona` instead of
`analyze`:

`python <modules>/data_copilot/scripts/copilot.py persona "<absolute path>" "<the request>" [--domain telecom] [--k N]`

It runs the same generate → run → repair loop, but forces the generated code to
emit a persona array (schema below) which is validated and **written to
`persona.json`** in the run dir, plus a narrative report. Present the `report`
field; if `summary.result_table` is non-null call `send_table` with
`file=<result_table>` and `suggestions=<summary.suggestions>`; mention that
`persona.json` (path in `summary.persona_json`) holds the structured personas.
If `verified` is `false`, say so and do not present the personas as settled.
Add `--domain telecom` only for FTEL/telecom-churn datasets (stricter
anti-hallucination rules). `--k` pins the cluster count when the user asks for a
specific number of segments.

Each persona in `persona.json` has: `cluster_id`, `persona_name`, `support`,
`support_pct`, `confidence`, `priority_score`, `is_anomaly`,
`segmentation_quality`, `risk_tier`, `evidence`, `profile_attributes`,
`recommended_actions`, `sample_persona_text`.
```

Add to the "## Commands (reference)" list:

```markdown
- Persona clustering (writes persona.json + narrative report):
  `python <modules>/data_copilot/scripts/copilot.py persona path/to/data.csv "Segment customers into personas" [--domain telecom] [--k N]`
  Flags: `--max-repair` (default 3), `--max-verify` (default 2), `--out <dir>`.
```

- [ ] **Step 2: Verify the module still loads (SKILL.md is parsed at discovery)**

Run: `uv run pytest tests/test_data_copilot_module_loads.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add modules/data_copilot/SKILL.md
git commit -m "docs(data_copilot): SKILL guidance for persona subcommand"
```

---

### Task 8: End-to-end verification with a real LLM

**Files:**
- None (verification only). Uses `modules/data_copilot/sample_data/`.

**Interfaces:**
- Consumes: the whole pipeline via the CLI.
- Produces: evidence that a real run writes a valid `persona.json`.

- [ ] **Step 1: Confirm a sample dataset exists**

Run: `ls modules/data_copilot/sample_data/`
Expected: at least one `.csv` (note its name, referred to below as `<sample.csv>`).

- [ ] **Step 2: Health check the LLM endpoint**

Run:
```bash
export OPENAI_API_KEY="$OPENAI_API_KEY"
uv run python modules/data_copilot/scripts/copilot.py health
```
Expected: `{"codegen": "ok"}`.

- [ ] **Step 3: Run the persona pipeline end-to-end**

Run:
```bash
uv run python modules/data_copilot/scripts/copilot.py persona \
  "modules/data_copilot/sample_data/<sample.csv>" \
  "Segment these customers into personas" --out /tmp/persona_e2e
```
Expected: a JSON object on stdout with `"verified": true`, a non-null
`"persona_json"`, and a non-empty `"personas"` array.

- [ ] **Step 4: Validate the written artifact**

Run:
```bash
uv run python -c "import json,sys; d=json.load(open('/tmp/persona_e2e/persona.json')); print(len(d),'personas'); print(sorted(d[0]))"
```
Expected: prints the persona count and the schema keys (matching `REQUIRED_FIELDS`).

- [ ] **Step 5: Final regression run**

Run: `uv run pytest tests/ -k data_copilot -q`
Expected: PASS.

- [ ] **Step 6: No commit** (verification only). Report the observed `persona.json` contents as evidence of completion.

---

## Self-Review

**Spec coverage:**
- §2 scope "port whole pipeline" → Tasks 1-5. ✓
- §2 entry point "both subcommand + SKILL guidance" → Tasks 6 (subcommand) + 7 (SKILL). ✓
- §2 domain "agnostic core + optional telecom pack" → Task 2 (`load_domain_pack`), Task 3 (`_TELECOM`), threaded through Tasks 5/6. ✓
- §2 output location "run dir per-session" → Task 5 writes `persona.json` to `out_dir`; CLI uses `_default_out_dir()` (Task 6). ✓
- §2 schema fidelity "data-agent field names" → Task 1 `REQUIRED_FIELDS`. ✓
- §3 reuse infra via DI → Tasks 3 (reuse `extract_code`), 4 (reuse `_UNVERIFIED`), 5 (reuse `charts`, `audit`, `sandbox`, `guardrails`, `copilot._load_result_table`). ✓
- §4 persona JSON schema → Task 1. ✓
- §5 output contract (summary keys) → Task 5 return dict + Task 5 test asserts keys. ✓
- §6 CLI + Skill + audit type `persona` → Tasks 6, 7, and Task 5 audit event. ✓
- §7 testing both unit + e2e → Tasks 1-7 unit, Task 8 e2e. ✓
- §8 non-goals respected (no RIMRULE, single LLM, no streaming tags). ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `verify_fn` is `(question, code, stdout, personas)` in Tasks 5 and 6; `verify_personas` signature matches (Task 2). `report_fn` is `(personas, question, verified)` in Tasks 5 and 6; `render_report(personas, question, chat_fn, *, verified)` matches (Task 4). `codegen_fn` is `(question, profile, prior_error, hypotheses)` in Tasks 5/6; `generate_code` wraps it with `k`/`domain` closed over (Task 6). `extract_personas`/`validate`/`MARKER_*`/`REQUIRED_FIELDS` names consistent across Tasks 1, 2, 5. Summary keys consistent between Task 5 impl/test and §5. ✓
