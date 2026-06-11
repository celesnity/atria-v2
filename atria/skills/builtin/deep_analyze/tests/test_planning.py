"""Planning phase: schema profile -> structured plan JSON."""

from unittest.mock import MagicMock

import pytest

from atria.skills.builtin.deep_analyze.planning import PlanningError, run_planning


_VALID_PLAN = """
{
  "summary": "small sales sample",
  "sub_tables": [
    {"name": "by_region", "sql": "CREATE TABLE t_by_region AS SELECT region, SUM(revenue) r FROM raw GROUP BY region", "why": "regional mix"}
  ],
  "charts": [
    {"name": "regional_revenue", "source_table": "t_by_region", "type": "bar",
     "x": "region", "y": ["r"], "title": "Revenue by region", "why": "compare regions"}
  ]
}
"""


def _fake_chat(responses: list[str]) -> MagicMock:
    m = MagicMock()
    m.side_effect = responses
    return m


def test_valid_plan_parses() -> None:
    plan = run_planning({"file_name": "x.csv", "row_count": 3, "columns": []},
                       chat=_fake_chat([_VALID_PLAN]))
    assert plan["sub_tables"][0]["name"] == "by_region"
    assert plan["charts"][0]["type"] == "bar"


def test_parse_failure_then_success_retries_once() -> None:
    chat = _fake_chat(["not json at all", _VALID_PLAN])
    plan = run_planning({"file_name": "x.csv", "row_count": 3, "columns": []}, chat=chat)
    assert chat.call_count == 2
    assert plan["summary"] == "small sales sample"


def test_two_consecutive_failures_raise() -> None:
    chat = _fake_chat(["nope", "still nope"])
    with pytest.raises(PlanningError):
        run_planning({"file_name": "x.csv", "row_count": 3, "columns": []}, chat=chat)


def test_empty_plan_is_rejected() -> None:
    empty = '{"summary": "x", "sub_tables": [], "charts": []}'
    with pytest.raises(PlanningError, match="no work"):
        run_planning({"file_name": "x.csv", "row_count": 3, "columns": []},
                     chat=_fake_chat([empty]))
