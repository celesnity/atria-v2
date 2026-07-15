"""Typed handler return + simple handled error. ``Response[T]`` normalizes into
the same envelope raw-dict returns produce; ``ActionError`` is the simple
handled-failure (``ToolError`` in envelope.py stays for code/retryable/details)."""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """A typed handler result. Set ``result`` on success or ``error`` on a
    handled failure."""

    result: Optional[T] = None
    error: Optional[str] = None


class ActionError(RuntimeError):
    """Raise from a handler for an expected/handled failure; the message becomes
    the failure envelope's ``output``."""
