"""HTTP endpoints for the knowledge base: rescan + document listing."""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from fastapi import APIRouter, Request


def build_router(
    service_factory: Callable[[], Awaitable[Any]],
    tenant_factory: Callable[[Request], str | None],
    seed_scan: Callable[[], Awaitable[int]],
) -> APIRouter:
    """Build the knowledge router.

    Args:
        service_factory: Async callable returning a KnowledgeService.
        tenant_factory: Resolves tenant_id from the request principal.
        seed_scan: Async callable that runs the seed scan and returns the count
            of newly enqueued docs.
    """
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.get("/documents")
    async def list_documents(request: Request) -> list[dict[str, Any]]:
        service = await service_factory()
        return await service.list_documents(tenant_factory(request))

    @router.post("/rescan")
    async def rescan() -> dict[str, int]:
        enqueued = await seed_scan()
        processed = await (await service_factory()).drain_queue()
        return {"enqueued": enqueued, "processed": processed}

    return router
