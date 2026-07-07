"""Uniform result envelope shared by all search providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchHit:
    """One ranked result from a provider, domain-agnostic."""

    id: str
    source: str
    title: str
    snippet: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class SourceResults:
    """Envelope returned by SearchProvider.search().

    top_margin: (s1 - s2) / s1 over hit scores. A small margin across distinct
    entities signals ambiguity — the agent should consider a clarifying
    question instead of picking the top hit.
    """

    source: str
    hits: list[SearchHit]
    facets: dict[str, dict[str, int]] = field(default_factory=dict)
    top_margin: float | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source": self.source,
            "hits": [h.to_dict() for h in self.hits],
        }
        if self.facets:
            d["facets"] = self.facets
        if self.top_margin is not None:
            d["top_margin"] = round(self.top_margin, 4)
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class SearchContext:
    """Per-request context injected by the runtime, never by the model.

    user_id identifies the acting user in the domain dataset (e.g. 'U001').
    Providers resolve their own policy data (role, department, preferences)
    from it. Resolution source: ATRIA_SEARCH_USER_ID env var for CLI/demo
    runs; web-session identity mapping is a future extension.

    Single-user limitation: the ATRIA_SEARCH_USER_ID env mechanism is only
    safe for single-user contexts (CLI/demo). Process environment is shared
    across threads, so per-request writes to it in a shared web process
    would race between concurrent requests and could let one user's search
    run under another user's ACL identity. Web deployments must thread
    identity per-call (e.g. via SkillToolContext) instead of mutating
    process env, never via the env var.
    """

    user_id: str | None = None
