"""End-to-end smoke test for knowledge_search through the real ToolRegistry.

Run with live Postgres (localhost:5433), Qdrant (localhost:6333) and
embedding env from .env (SEARCH_EMBED_*), after both ingestion scripts. Queries below are
generic phrasings invented from the corpus sheets — NOT from the eval sheets.

    uv run python scripts/search_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Repo root, so `minder` resolves when this file is run directly (as a script,
# rather than through a test runner that already puts the repo root on
# sys.path). Needed regardless of whether minder is pip-installed editable —
# works around a venv .pth import defect where `minder` is only importable
# under pytest otherwise.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minder.core.context_engineering.tools.registry import ToolRegistry  # noqa: E402

_OPEN_CLASSIFICATIONS = {"Public", "Internal"}


def _run(registry: ToolRegistry, label: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one knowledge_search call and print its top hits.

    Args:
        registry: Live ToolRegistry to dispatch the call through.
        label: Human-readable heading printed above the result.
        arguments: Arguments passed to the knowledge_search tool.

    Returns:
        The decoded JSON payload (hits/facets/top_margin/note) on success.
    """
    print(f"\n=== {label}\n    args: {json.dumps(arguments, ensure_ascii=False)}")
    result = registry.execute_tool("knowledge_search", arguments)
    if not result.get("success"):
        raise SystemExit(f"FAILED: {result.get('error')}")
    payload: dict[str, Any] = json.loads(result["output"])
    for hit in payload["hits"][:3]:
        print(f"    {hit['id']}  {hit['score']:.4f}  {hit['title']}")
    print(f"    facets: {json.dumps(payload.get('facets', {}), ensure_ascii=False)}")
    print(f"    top_margin: {payload.get('top_margin')}  note: {payload.get('note')}")
    return payload


def main() -> None:
    """Drive knowledge_search + get_user_profile through a real ToolRegistry.

    Exercises both discovered providers (documents, places) across an
    authenticated and an anonymous identity, and the maps_search profile
    tool, asserting the ACL and proximity guarantees each provider claims.
    Raises SystemExit (via a failed assert or a tool-level failure) on any
    violation; prints "E2E OK" as the last line on success.
    """
    registry = ToolRegistry()
    assert "knowledge_search" in registry.get_skill_specs(), "hub tool not discovered"
    assert "get_user_profile" in registry.get_skill_specs(), "maps tool not discovered"

    # Documents: employee view vs unknown identity
    os.environ["MINDER_SEARCH_USER_ID"] = "U001"
    employee_payload = _run(
        registry,
        "documents as U001",
        {"query": "quy định làm việc từ xa", "source": "documents"},
    )
    assert employee_payload["hits"], "expected ranked hits for U001"
    os.environ.pop("MINDER_SEARCH_USER_ID", None)
    anon_payload = _run(
        registry,
        "documents anonymous",
        {"query": "báo cáo tài chính", "source": "documents"},
    )
    assert anon_payload["hits"], "expected hits for anonymous documents search"
    for hit in anon_payload["hits"]:
        classification = hit.get("metadata", {}).get("classification")
        assert (
            classification in _OPEN_CLASSIFICATIONS
        ), f"anonymous hit {hit['id']} leaked classification {classification!r}"

    # Places: plain, filtered, and proximity
    _run(registry, "places plain", {"query": "quán cà phê có wifi yên tĩnh", "source": "places"})
    near_payload = _run(
        registry,
        "places near Hoan Kiem",
        {
            "query": "chỗ chơi cho trẻ em",
            "source": "places",
            "filters": {"near": {"lat": 21.0287, "lon": 105.8521}, "radius_m": 8000},
        },
    )
    distances = [
        hit["metadata"]["distance_m"]
        for hit in near_payload["hits"]
        if "distance_m" in hit.get("metadata", {})
    ]
    assert distances, "expected at least one hit with distance_m metadata"
    assert all(d <= 8000 for d in distances), f"distance beyond radius_m: {distances}"

    profile = registry.execute_tool("get_user_profile", {"user_id": "U001"})
    print(f"\n=== get_user_profile U001 -> {profile.get('success')}")
    assert profile.get("success") is True, f"profile lookup failed: {profile.get('error')}"
    print("\nE2E OK")


if __name__ == "__main__":
    main()
