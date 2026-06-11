"""Planning LLM call: dataset schema -> sub_tables + charts plan."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from .prompts import PLANNING_SYSTEM

logger = logging.getLogger(__name__)


class PlanningError(RuntimeError):
    pass


def _strip_fences(raw: str) -> str:
    if "```" not in raw:
        return raw.strip()
    for fence in ("```json", "```"):
        if fence in raw:
            return raw.split(fence, 1)[-1].split("```")[0].strip()
    return raw.strip()


def _strip_t_prefix(name: str) -> str:
    """Planner LLMs sometimes return names with the ``t_`` prefix already
    applied. The pipeline always re-applies ``t_`` when materializing, so
    drop a leading ``t_`` here to avoid ``t_t_<name>`` table lookups."""
    return name[2:] if isinstance(name, str) and name.startswith("t_") else name


def _parse_plan(raw: str) -> Dict[str, Any]:
    plan = json.loads(_strip_fences(raw))
    for key in ("sub_tables", "charts"):
        if key not in plan or not isinstance(plan[key], list):
            raise ValueError(f"plan missing list `{key}`")
    # Normalize sub-table names and chart source_table references so the
    # pipeline can rely on bare names (without the ``t_`` prefix).
    for spec in plan["sub_tables"]:
        if isinstance(spec, dict) and "name" in spec:
            spec["name"] = _strip_t_prefix(spec["name"])
    for chart in plan["charts"]:
        if isinstance(chart, dict) and "source_table" in chart:
            # source_table is expected WITH the ``t_`` prefix (it's the real
            # table name in SQLite). Only fix the case where the planner
            # doubled it.
            st = chart["source_table"]
            if isinstance(st, str) and st.startswith("t_t_"):
                chart["source_table"] = st[2:]
    return plan


def run_planning(profile: Dict[str, Any], chat: Callable[[str, str], str]) -> Dict[str, Any]:
    user = json.dumps(profile, ensure_ascii=False)
    last_err: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            raw = chat(PLANNING_SYSTEM, user)
            plan = _parse_plan(raw)
            if not plan["sub_tables"] or not plan["charts"]:
                raise PlanningError("planner produced no work")
            return plan
        except PlanningError:
            raise
        except Exception as e:
            last_err = e
            logger.warning("planning parse failure (attempt %s): %s", attempt, e)
    raise PlanningError(f"planning failed after 2 attempts: {last_err}")
