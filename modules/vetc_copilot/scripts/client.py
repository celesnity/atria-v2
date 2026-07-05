"""Thin OpenAI-compatible Brain client; reports availability so callers can fall back."""
from __future__ import annotations

from typing import Callable, List, Optional

try:
    from openai import OpenAI as _OpenAI
except ImportError:  # pragma: no cover
    _OpenAI = None  # type: ignore[assignment]

from config import RoleConfig  # type: ignore[import-not-found]

ClientFactory = Callable[[str, str], object]


def _default_factory(base_url: str, api_key: str) -> object:
    if _OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai package is not installed")
    return _OpenAI(base_url=base_url, api_key=api_key)


class BrainClient:
    """Chat client for the Brain role. ``available`` is False when no key is set."""

    def __init__(self, cfg: RoleConfig, client_factory: Optional[ClientFactory] = None) -> None:
        self._cfg = cfg
        self._factory = client_factory or _default_factory
        self._client: object | None = None

    @property
    def available(self) -> bool:
        """True when an API key is configured (so the LLM path can be used)."""
        return bool(self._cfg.api_key)

    def chat(self, messages: List[dict], **kw) -> str:
        """Send a chat completion and return the first choice's text."""
        if self._client is None:
            self._client = self._factory(self._cfg.base_url, self._cfg.api_key)
        kw.setdefault("temperature", 0)
        kw.setdefault("max_tokens", 500)
        resp = self._client.chat.completions.create(  # type: ignore[attr-defined]
            model=self._cfg.model, messages=messages, **kw)
        return resp.choices[0].message.content
