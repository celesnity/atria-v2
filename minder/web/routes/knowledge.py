"""HTTP endpoints for the knowledge base: rescan + document listing."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Request


def build_router(
    service_factory: Callable[[], Any],
    tenant_factory: Callable[[Request], str | None],
    seed_scan: Callable[[], int],
) -> APIRouter:
    """Build the knowledge router.

    Args:
        service_factory: Returns a KnowledgeService (async methods).
        tenant_factory: Resolves tenant_id from the request principal.
        seed_scan: Runs the seed scan and returns the count of newly enqueued docs.
    """
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.get("/documents")
    async def list_documents(request: Request) -> list[dict[str, Any]]:
        service = service_factory()
        return await service.list_documents(tenant_factory(request))

    @router.post("/rescan")
    async def rescan() -> dict[str, int]:
        enqueued = seed_scan()
        processed = await service_factory().drain_queue()
        return {"enqueued": enqueued, "processed": processed}

    return router
