"""Formatting + thin operations for the `minder knowledge` CLI."""

from __future__ import annotations

from typing import Any


def format_documents(docs: list[dict[str, Any]]) -> str:
    if not docs:
        return "(no documents)"
    lines = [f"{d['id']:>4}  {d['status']:<10}  {d['category']:<18}  {d['title']}" for d in docs]
    return "\n".join(lines)


def format_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(no hits)"
    lines = []
    for h in hits:
        citation = h.get("metadata", {}).get("citation", "")
        lines.append(f"- {citation}\n  {h.get('snippet', '')}")
    return "\n".join(lines)
