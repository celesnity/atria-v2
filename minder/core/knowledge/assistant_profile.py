"""Bridge the async ProfileInjector into the synchronous prompt builder."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def load_profile_block_sync(tenant_id: str | None) -> str:
    """Return the tenant profile block, or '' on any failure/unavailability."""
    if not tenant_id or not os.environ.get("DATABASE_URL"):
        return ""
    try:
        from minder.core.knowledge.profile import ProfileInjector
        from minder.core.knowledge.repository import KnowledgeRepository
        from minder.db.connection import get_sessionmaker

        async def _run() -> str:
            sm = await get_sessionmaker()
            return await ProfileInjector(KnowledgeRepository(sm)).build_profile_block(tenant_id)

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile block load failed: %s", exc)
        return ""


def apply_profile(base_prompt: str, tenant_id: str | None) -> str:
    """Prepend the tenant profile block to the base prompt when present.

    The persona block leads, replacing the default identity framing; the base
    prompt's operational/safety sections stay intact below it.
    """
    block = load_profile_block_sync(tenant_id)
    if not block:
        return base_prompt
    return f"{block}\n\n{base_prompt}"
