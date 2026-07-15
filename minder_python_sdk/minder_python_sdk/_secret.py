"""Managed credentials — ``Secret`` / ``OAuth2Secret`` params are resolved from
a forwarded header (``x-{name}``) or env (``{NAME_UPPER}``) and injected at call
time, so they never appear in the agent-facing tool schema."""

from __future__ import annotations

import os
from typing import Any, Generic, Mapping, Optional, TypeVar, get_args

P = TypeVar("P")
S = TypeVar("S")


class Secret:
    """An injected credential; ``.value`` is the resolved string."""

    def __init__(self, value: str) -> None:
        self._value = value

    @property
    def value(self) -> str:
        return self._value


class OAuth2Secret(Generic[P, S]):
    """An injected OAuth2 bearer credential. ``provider``/``scopes`` come from
    the declared generic args; ``access_token`` from the forwarded header/env."""

    def __init__(
        self,
        access_token: str,
        provider: str = "",
        scopes: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        self._token = access_token
        self._provider = provider
        self._scopes = scopes or []
        self._metadata = metadata or {}

    @property
    def access_token(self) -> str:
        return self._token

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def scopes(self) -> list[str]:
        return list(self._scopes)

    @property
    def metadata(self) -> dict:
        return dict(self._metadata)


class SecretSpec:
    """``Annotated`` marker tagging a secret as centrally-managed/global."""

    def __init__(self, tag: str = "") -> None:
        self.tag = tag


def _header_key(name: str) -> str:
    """Normalize a header/secret name for comparison: lowercase, and treat
    ``-`` and ``_`` as equivalent (proxies like nginx rewrite/drop underscores)."""
    return name.lower().replace("_", "-")


def resolve_secret_value(name: str, headers: Optional[Mapping[str, str]]) -> Optional[str]:
    """Forwarded header ``x-{name}`` (case-insensitive, ``-``/``_`` equivalent),
    then env ``{NAME_UPPER}``."""
    if headers:
        want = _header_key(f"x-{name}")
        for key, val in headers.items():
            if _header_key(key) == want:
                return val
    return os.environ.get(name.upper())


def _literals(tp: Any) -> list[str]:
    """Flatten ``Literal[...]`` args (used to read OAuth2Secret provider/scopes)."""
    out: list[str] = []
    for arg in get_args(tp):
        inner = get_args(arg)
        if inner:
            out.extend(str(x) for x in inner)
        elif isinstance(arg, str):
            out.append(arg)
    return out


def build_secret(annotation: Any, raw: str) -> Any:
    """Wrap a resolved raw value into its declared Secret/OAuth2Secret type."""
    origin = getattr(annotation, "__origin__", None) or annotation
    if isinstance(origin, type) and issubclass(origin, OAuth2Secret):
        type_args = get_args(annotation)
        provider = ""
        scopes: list[str] = []
        if type_args:
            provider_lits = _literals(type_args[0])
            provider = provider_lits[0] if provider_lits else ""
        if len(type_args) > 1:
            scopes = _literals(type_args[1])
        return OAuth2Secret(access_token=raw, provider=provider, scopes=scopes)
    return Secret(raw)
