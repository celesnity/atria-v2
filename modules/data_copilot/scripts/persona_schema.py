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
