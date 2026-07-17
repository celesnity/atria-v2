"""Build the per-tenant persona/background block injected into the prompt."""

from __future__ import annotations

from typing import Any


class ProfileInjector:
    """Assembles tenant persona + company background into a prompt section."""

    def __init__(self, repo: Any, max_chars: int = 8000) -> None:
        self._repo = repo
        self._max_chars = max_chars

    async def build_profile_block(self, tenant_id: str | None) -> str:
        if not tenant_id:
            return ""
        docs = await self._repo.summaries_for_inject(
            tenant_id, ["company_background", "persona"]
        )
        background = [
            d["summary"]
            for d in docs
            if d["category"] == "company_background"
        ]
        persona = [d["summary"] for d in docs if d["category"] == "persona"]
        parts: list[str] = []
        if background:
            parts.append("## Bối cảnh tổ chức\n" + "\n\n".join(background))
        if persona:
            parts.append("## Vai trò của bạn\n" + "\n\n".join(persona))
        block = "\n\n".join(parts)
        if len(block) > self._max_chars:
            block = block[: self._max_chars] + "…"
        return block

    async def has_persona(self, tenant_id: str | None) -> bool:
        if not tenant_id:
            return False
        docs = await self._repo.summaries_for_inject(tenant_id, ["persona"])
        return any(d["category"] == "persona" for d in docs)
