"""Shared helpers for the hackathon API facade routers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


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
