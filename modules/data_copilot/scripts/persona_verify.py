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
