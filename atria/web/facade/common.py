"""Shared helpers for the hackathon API facade routers."""

from __future__ import annotations

import functools
import logging
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def request_id(request: Request | None = None) -> str:
    """Echo the caller's X-Request-Id or mint one."""
    if request is not None:
        rid = request.headers.get("X-Request-Id")
        if rid:
            return rid
    return str(uuid.uuid4())


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> JSONResponse:
    """Documented maps ErrorResponse: {"error": {code, message, details}, "requestId"}."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details or {}},
            "requestId": request_id(request),
        },
    )


def facade_guard(handler: Any) -> Any:
    """Wrap a facade endpoint so backend failures return the documented envelope."""

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except Exception:  # backend down/unregistered must not leak default 500s
            logger.exception("facade backend failure in %s", handler.__name__)
            return error_response(503, "service_unavailable", "Upstream search backend unavailable")

    return wrapper
