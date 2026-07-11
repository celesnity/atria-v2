"""Thin OpenAI-compatible client that dispatches calls by feature role.

One underlying ``openai.OpenAI`` is created per distinct (base_url, api_key)
so hosted OpenAI-compatible endpoints are reused across roles that share them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import sibling  # noqa: E402

from typing import Callable, Dict, List, Optional, Tuple

try:  # Import lazily so unit tests can inject a fake factory without openai.
    from openai import OpenAI as _OpenAI
except ImportError:  # pragma: no cover - openai installed in real env
    _OpenAI = None  # type: ignore[assignment]

budget = sibling("budget")
RoleConfig = sibling("config").RoleConfig

ClientFactory = Callable[[str, str], object]

# GPT-5 and O-series reasoning models take ``max_completion_tokens`` (they 400
# on ``max_tokens``), accept only the default temperature, and support
# ``reasoning_effort``. Everything else (gpt-4o-mini, OpenRouter models) keeps
# the classic ``max_tokens``.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _default_factory(base_url: str, api_key: str) -> object:
    if _OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai package is not installed")
    return _OpenAI(base_url=base_url, api_key=api_key)


class RoleClient:
    """Resolve embed/chat calls to the endpoint configured for a role."""

    def __init__(
        self,
        config: Dict[str, RoleConfig],
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        self._config = config
        self._factory = client_factory or _default_factory
        self._clients: Dict[Tuple[str, str], object] = {}

    def _role(self, role: str) -> RoleConfig:
        if role not in self._config:
            raise ValueError(f"unknown role: {role!r}")
        return self._config[role]

    def _client_for(self, rc: RoleConfig) -> object:
        key = (rc.base_url, rc.api_key)
        if key not in self._clients:
            self._clients[key] = self._factory(rc.base_url, rc.api_key)
        return self._clients[key]

    def embed(self, role: str, texts: List[str]) -> List[List[float]]:
        """Return embedding vectors for *texts* using the endpoint for *role*.

        Args:
            role: Feature role key (e.g. ``"index_embed"``).
            texts: One or more strings to embed.

        Returns:
            A list of float vectors, one per input text, in the same order.
        """
        rc = self._role(role)
        client = self._client_for(rc)
        # Request float arrays explicitly. The openai SDK otherwise defaults to
        # encoding_format="base64" and decodes client-side; OpenAI-compatible
        # providers that return plain float arrays (e.g. OpenRouter/NVIDIA) then
        # yield "No embedding data received". "float" is universally accepted.
        resp = client.embeddings.create(  # type: ignore[attr-defined]
            model=rc.model, input=texts, encoding_format="float"
        )
        return [item.embedding for item in resp.data]

    def chat(self, role: str, messages: List[dict], **kw) -> str:
        """Send a chat-completion request using the endpoint configured for *role*.

        Args:
            role: Feature role key (e.g. ``"synthesis"``).
            messages: OpenAI-format message list (``[{"role": ..., "content": ...}, ...]``).
            **kw: Extra keyword arguments forwarded to ``completions.create``
                (e.g. ``temperature``, ``max_tokens``).

        Returns:
            The text content of the first choice's message.
        """
        rc = self._role(role)
        client = self._client_for(rc)
        # Cap the completion so the server does not reserve a large default
        # output and overflow the model context (input + output must both fit).
        # An explicit caller-supplied budget always wins.
        budget_tokens = kw.pop("max_tokens", None)
        budget_tokens = kw.pop("max_completion_tokens", budget_tokens)
        if budget_tokens is None:
            budget_tokens = budget.output_tokens(role)
        if rc.model.startswith(_REASONING_PREFIXES):
            # Reasoning models: use max_completion_tokens, keep reasoning minimal
            # so the budget funds the grounded answer (not internal reasoning,
            # which can otherwise consume it and yield an empty completion), and
            # omit temperature (only the default is accepted).
            kw["max_completion_tokens"] = budget_tokens
            kw.setdefault("reasoning_effort", "minimal")
            kw.pop("temperature", None)
        else:
            kw["max_tokens"] = budget_tokens
        resp = client.chat.completions.create(  # type: ignore[attr-defined]
            model=rc.model, messages=messages, **kw
        )
        return resp.choices[0].message.content
