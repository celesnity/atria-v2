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
