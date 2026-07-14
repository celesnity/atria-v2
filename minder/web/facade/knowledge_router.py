"""My Tasco (COP-convention) knowledge-search facade over the documents provider.

Follows the COP conventions from the hackathon API doc: response envelope
{status, message, body, requestId}, example/pageInfo request shape, and the
documented error codes. Identity is per-request via the X-User-Id header —
missing/unknown ids degrade to the most-restrictive anonymous view.

Deliberately no ``from __future__ import annotations`` here (unlike
maps_router.py): ``facade_guard`` (minder/web/facade/common.py) wraps the
handler with ``functools.wraps``, and FastAPI resolves string/forward-ref
annotations using the *wrapper's* ``__globals__`` — which is common.py's
module namespace, not this module's. With postponed evaluation, the
``payload: _KnowledgeSearchRequest`` annotation would be a string FastAPI
can't resolve there (``_KnowledgeSearchRequest`` isn't defined in
common.py), silently degrading it to an unrecognized query param and
breaking the request body (422 on every call). Evaluating annotations
eagerly at class/def time sidesteps the lookup entirely. maps_router.py
never hit this because its facade_guard-wrapped endpoints only take
primitive/already-imported-in-common types (Request, str, float, int,
bool), which resolve fine either way.
"""

import re
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from minder.core.context_engineering.search.registry import discover_module_providers
from minder.core.modules.registry import resolve_modules_root
from minder.core.context_engineering.search.types import SearchContext
from minder.web.facade.common import facade_guard, request_id

knowledge_facade_router = APIRouter(tags=["knowledge-facade"])

_MAX_PAGE_SIZE = 20


class _PageInfo(BaseModel):
    pageSize: int = 10
    currentPage: int = 0


class _KnowledgeSearchRequest(BaseModel):
    example: dict[str, Any] = {}
    pageInfo: _PageInfo = _PageInfo()


@lru_cache(maxsize=1)
def _documents_provider() -> Any:
    registry = discover_module_providers(resolve_modules_root())
    provider = registry.get("documents")
    if provider is None:
        raise RuntimeError("documents provider not registered")
    return provider


def _cop_error(status_code: int, code: str, message: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": code,
            "message": message,
            "requestId": request_id(request),
        },
    )


def _withheld_count(note: str | None) -> int:
    if not note:
        return 0
    match = re.search(r"(\d+) matching document\(s\) were withheld", note)
    return int(match.group(1)) if match else 0


# @facade_guard is placed below the route decorator (closest to the function)
# so unhandled backend failures (e.g. Postgres/Qdrant unreachable) return the
# shared 503 service_unavailable envelope from minder.web.facade.common instead
# of leaking FastAPI's default 500. That envelope follows the MAPS
# ErrorResponse shape ({error: {code, message, details}, requestId}), not the
# COP {status, message, body, requestId} envelope used by this router's
# normal responses — an accepted cross-cutting inconsistency limited to the
# crash path, per Task 5's review.
@knowledge_facade_router.post("/cop/aiwsp/knowledge/search")
@facade_guard
def knowledge_search(payload: _KnowledgeSearchRequest, request: Request) -> Any:
    keyword = str(payload.example.get("keyword") or "").strip()
    if not keyword:
        return _cop_error(400, "invalid_request", "keyword is required", request)

    user_id = request.headers.get("X-User-Id") or None
    page_size = min(max(payload.pageInfo.pageSize, 1), _MAX_PAGE_SIZE)
    department = payload.example.get("department") or None
    filters = {"department": department} if department else {}

    results = _documents_provider().search(
        keyword, filters, page_size, SearchContext(user_id=user_id)
    )
    hits = [
        {
            "documentId": h.metadata["document_id"],
            "title": h.title,
            "snippet": h.snippet,
            "department": h.metadata["department"],
            "classification": h.metadata["classification"],
            "score": round(float(h.score), 4),
        }
        for h in results.hits
    ]
    return {
        "status": "success",
        "message": "SUCCESS",
        "body": {
            "result": hits,
            "note": results.note,
            "withheldCount": _withheld_count(results.note),
            "pageInfo": {
                "pageSize": page_size,
                "currentPage": payload.pageInfo.currentPage,
                "totalRecord": len(hits),
            },
        },
        "requestId": request_id(request),
    }
