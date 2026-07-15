"""Infer a Pydantic model (hence a JSON schema + validator) from a handler's
signature, so ``@conn.tool`` needs no hand-written ``parameters=``."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Optional, get_args, get_origin, get_type_hints

from pydantic import create_model

MANAGED_PARAMS = frozenset({"principal", "session_id", "autonomy", "dry_run"})


def _is_secret_type(annotation: Any) -> bool:
    """True if annotation is ``Secret`` / ``OAuth2Secret`` (or a parametrization
    of them). Lazily imports ``_secret`` so this module has no import cycle."""
    try:
        from ._secret import OAuth2Secret, Secret, unwrap_annotated
    except Exception:  # noqa: BLE001 — _secret may not be importable
        return False
    annotation = unwrap_annotated(annotation)
    target = getattr(annotation, "__origin__", None) or annotation
    try:
        return isinstance(target, type) and issubclass(target, (Secret, OAuth2Secret))
    except TypeError:
        return False


def _data_params(fn: Callable) -> list[inspect.Parameter]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    out = []
    for p in sig.parameters.values():
        if p.name in MANAGED_PARAMS:
            continue
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        out.append(p)
    return out


def _hints(fn: Callable) -> dict:
    try:
        return get_type_hints(fn, include_extras=True)
    except Exception:  # noqa: BLE001 — unresolved forward refs, etc.
        return {}


def build_params_model(fn: Callable) -> Optional[type]:
    """Build a Pydantic model of ``fn``'s agent-supplied params, or ``None``."""
    hints = _hints(fn)
    fields: dict[str, tuple] = {}
    for p in _data_params(fn):
        annotation = hints.get(p.name, p.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = Any
        if _is_secret_type(annotation):
            continue
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[p.name] = (annotation, default)
    if not fields:
        return None
    name = getattr(fn, "__name__", "handler")
    return create_model(f"{name}_Params", **fields)  # type: ignore[call-overload]


def secret_params(fn: Callable) -> dict[str, Any]:
    """Map of param name → annotation for each Secret/OAuth2Secret param."""
    hints = _hints(fn)
    out: dict[str, Any] = {}
    for p in _data_params(fn):
        annotation = hints.get(p.name, p.annotation)
        if _is_secret_type(annotation):
            out[p.name] = annotation
    return out


def _unwrap_response(ret: Any) -> Any:
    """If ``ret`` is ``Response[T]``, return ``T``; otherwise return ``ret``."""
    try:
        from ._response import Response

        origin = get_origin(ret)
        if origin is not None and isinstance(origin, type) and issubclass(origin, Response):
            args = get_args(ret)
            if args:
                return args[0]
    except Exception:  # noqa: BLE001
        pass
    return ret


def output_annotation_for(fn: Callable) -> Optional[Any]:
    """The (Response-unwrapped) return annotation, for runtime soft-validation."""
    try:
        ret = _hints(fn).get("return", inspect.signature(fn).return_annotation)
    except (TypeError, ValueError):
        return None
    if ret is inspect.Signature.empty or ret is inspect.Parameter.empty or ret is None:
        return None
    return _unwrap_response(ret)


def output_schema_for(fn: Callable) -> Optional[dict]:
    """JSON schema for fn's return annotation, or None if unannotated.
    Unwraps ``Response[T]`` to schema-ize ``T``."""
    from pydantic import TypeAdapter

    ret = output_annotation_for(fn)
    if ret is None:
        return None
    try:
        return TypeAdapter(ret).json_schema()
    except Exception:  # noqa: BLE001 — unschematizable annotation
        return None
