"""Classify exceptions as connectivity failures (sidecar down vs real bug).

Shared by the skill tool (degraded structured response) and the CLI (clean
JSON error line). qdrant-client and the OpenAI SDK wrap httpx/requests errors,
so classification walks the cause chain and falls back to message sniffing
rather than importing optional dependency exception types.
"""

from __future__ import annotations

_CONNECTIVITY_TYPES = (ConnectionError, TimeoutError, OSError)

_CONNECTIVITY_MARKERS = (
    "connect",
    "connection",
    "refused",
    "timed out",
    "timeout",
    "unreachable",
    "name or service not known",
    "getaddrinfo",
)


def is_connectivity(exc: BaseException) -> bool:
    """True when *exc* (or anything in its cause chain) looks like a dead service."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _CONNECTIVITY_TYPES):
            return True
        message = str(current).lower()
        if any(marker in message for marker in _CONNECTIVITY_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False
