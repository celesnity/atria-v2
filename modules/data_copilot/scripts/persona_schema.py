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

# Fields every persona must carry. ``sample_persona_text`` is intentionally NOT
# required: the production clustering output omits it (it was only ever used for
# a narrative snippet the report no longer reads), so requiring it would reject
# otherwise-valid output. Extra fields the generator emits (persona_type,
# severity, risk, feature_means) are validated leniently below when present.
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
)
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
_RISK = {"HIGH", "MEDIUM", "LOW"}
_SEVERITY = {"LOW", "MEDIUM", "HIGH", "EXTREME"}
# The 10 valid primary actions — keys of report_generator.ROADMAP_METADATA.
# Duplicated here (not imported) to keep schema validation import-light.
ROADMAP_ACTIONS = frozenset(
    {
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
    }
)
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
        # Lenient checks on optional fields the generator also emits.
        if "risk" in p and p["risk"] not in _RISK:
            raise ValueError(f"persona[{i}].risk must be one of {sorted(_RISK)}")
        if "feature_means" in p and not isinstance(p["feature_means"], dict):
            raise ValueError(f"persona[{i}].feature_means must be an object")
        if "persona_type" in p and not isinstance(p["persona_type"], str):
            raise ValueError(f"persona[{i}].persona_type must be a string")
        if "severity" in p and p["severity"] not in _SEVERITY:
            raise ValueError(f"persona[{i}].severity must be one of {sorted(_SEVERITY)}")
        if "profile_attributes" in p and not isinstance(p["profile_attributes"], dict):
            raise ValueError(f"persona[{i}].profile_attributes must be an object")
