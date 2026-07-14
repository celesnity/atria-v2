"""Declarative agent-facing context: live state, knowledge, notes.

The backend mirror of the frontend ``Agent.*`` wrapper layer. A module declares
context through ``conn.context.*`` and the connector surfaces it to the agent —
static parts (knowledge, notes) in the manifest, live ``state`` in the context
endpoint.
"""
from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_STATE_CHARS = 32768


@dataclass
class Note:
    """A labeled, agent-facing description of a page/area of the module."""

    name: str
    text: str


@dataclass
class _StateProvider:
    """A registered ``context.state`` provider: a description + the function that
    returns the live value on each context read."""

    description: str
    fn: Callable[..., Any]


def _wants(fn: Callable[..., Any], arg: str) -> bool:
    """True if ``fn`` accepts ``arg`` by name or via ``**kwargs``."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if arg in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def cap_value(value: Any) -> tuple[Any, bool]:
    """Cap a state value at ``MAX_STATE_CHARS`` serialized chars.

    Returns ``(value, truncated)``. JSON-serializable values under the cap pass
    through unchanged; over-cap or non-serializable values become a truncated
    string.
    """
    try:
        serialized = json.dumps(value)
    except (TypeError, ValueError):
        serialized = str(value)
        value = serialized
    if len(serialized) > MAX_STATE_CHARS:
        return serialized[:MAX_STATE_CHARS], True
    return value, False


def build_state_entries(
    providers: dict[str, _StateProvider], principal: Any, session_id: Any
) -> list[dict]:
    """Evaluate every state provider live, fail-closed per entry.

    Each provider may accept ``principal`` / ``session_id`` (injected when its
    signature declares them). A provider that raises is skipped with a warning;
    the rest still return.
    """
    entries: list[dict] = []
    for name, prov in providers.items():
        try:
            kwargs: dict[str, Any] = {}
            if _wants(prov.fn, "principal"):
                kwargs["principal"] = principal
            if _wants(prov.fn, "session_id"):
                kwargs["session_id"] = session_id
            value, truncated = cap_value(prov.fn(**kwargs))
            entry: dict[str, Any] = {"name": name, "description": prov.description, "value": value}
            if truncated:
                entry["truncated"] = True
            entries.append(entry)
        except Exception as exc:  # fail-closed per entry
            logger.warning("context.state %r failed: %s", name, exc)
    return entries


class _ContextRegistrar:
    """The ``conn.context`` accessor. Registers declarative agent context onto an
    owner exposing ``_ctx_state`` / ``_ctx_knowledge`` / ``_ctx_notes``."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def state(self, name: str, description: str = "") -> Callable[[Callable], Callable]:
        """Decorate a function returning live module state the agent reads."""

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._owner._ctx_state:
                logger.warning("context.state %r redefined", name)
            self._owner._ctx_state[name] = _StateProvider(description=description, fn=fn)
            return fn

        return deco

    def knowledge(self, text: str) -> None:
        """Add a static domain-knowledge / guardrail string for the agent."""
        text = (text or "").strip()
        if text:
            self._owner._ctx_knowledge.append(text)

    def note(self, name: str, text: str) -> None:
        """Add a static, labeled area/page description (duplicate name overrides)."""
        name = (name or "").strip()
        text = (text or "").strip()
        if not name or not text:
            return
        self._owner._ctx_notes = [n for n in self._owner._ctx_notes if n.name != name]
        self._owner._ctx_notes.append(Note(name=name, text=text))
