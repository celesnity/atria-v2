"""Atria-side client for a module's out-of-process connector service.

Registration is deterministic from the committed manifest (Task 2.3); this
client is only touched at *call time*. A dead connector fails closed with a
structured card, never a crash and never freelancing over the corpus.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ConnectorUnreachable(RuntimeError):
    """The connector service could not be reached over the network."""

    service = "connector"


# Connector-down directive for the model (mirrors the service's UNAVAILABLE_SUFFIX
# but built on the Atria side, deps-free, when the whole container is down).
UNAVAILABLE_SUFFIX = (
    "\n\n[SYSTEM: The maintenance copilot service is unavailable (connector "
    "unreachable). Tell the user the copilot cannot answer right now and that the "
    "structured card above explains why. Do NOT read the manual files in "
    "sample_manuals, do NOT grep or cat them via bash, and do NOT answer the "
    "maintenance question from your own knowledge.]"
)

_UNAVAILABLE_ANSWER = (
    "The maintenance copilot service is currently unavailable (connector "
    "unreachable), so this question cannot be answered with grounded citations "
    "right now. Please retry once the service is restored."
)


def unavailable_card(query: str, connector_name: str) -> dict:
    """A deps-free, fail-closed card matching the maintenance-answer shape."""
    return {
        "query": query,
        "answer": _UNAVAILABLE_ANSWER,
        "answer_type": "clarification_needed",
        "exact_quote": "",
        "is_sensitive": False,
        "related_suggestions": [],
        "data_collection_requirement": {"needs_user_input": False, "missing_fields": []},
        "citations": [],
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "advisory_note": "",
        "validation_warnings": [f"connector_unreachable:{connector_name}"],
        "structured": {},
    }


class RemoteConnector:
    """Thin HTTP client for one module's connector service."""

    def __init__(self, name: str, connector_url: str,
                 health_path: str = "/connector/health") -> None:
        self.name = name
        self.base_url = connector_url.rstrip("/")
        self.health_path = health_path
        self._client = httpx.Client(base_url=self.base_url)

    def is_healthy(self, timeout: float = 2.0) -> bool:
        try:
            r = self._client.get(self.health_path, timeout=timeout)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def call_tool(self, tool: str, arguments: dict, timeout: float = 110.0) -> dict:
        try:
            r = self._client.post(f"/connector/tools/{tool}",
                                  json={"arguments": arguments}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("connector %s call_tool(%s) failed: %s", self.name, tool, exc)
            raise ConnectorUnreachable(str(exc)) from exc


from typing import TYPE_CHECKING, Any, Callable  # noqa: E402

if TYPE_CHECKING:  # avoid import cycles / heavy imports at module load
    from atria.core.modules.store import Module
    from atria.core.skill_tools import SkillToolContext, ToolSpec


def _make_handler(ctx: "SkillToolContext", conn: "RemoteConnector",
                  tool_name: str) -> Callable[..., dict]:
    def handler(**kwargs: Any) -> dict:
        query = str(kwargs.get("query") or kwargs.get("text") or "")
        try:
            resp = conn.call_tool(tool_name, kwargs)
        except ConnectorUnreachable:
            card = unavailable_card(query, conn.name)
            if ctx.broadcaster:
                try:
                    ctx.broadcaster({"type": "maintenance_answer", **card})
                except Exception as exc:  # noqa: BLE001
                    ctx.logger.warning("card broadcast failed: %s", exc)
            return {"success": True, "output": card, "_llm_suffix": UNAVAILABLE_SUFFIX}

        card = resp.get("card")
        if card and ctx.broadcaster:
            try:
                ctx.broadcaster({"type": "maintenance_answer", **card})
            except Exception as exc:  # noqa: BLE001
                ctx.logger.warning("card broadcast failed: %s", exc)
        out: dict = {"success": bool(resp.get("success", True)), "output": resp.get("output")}
        if resp.get("llm_suffix"):
            out["_llm_suffix"] = resp["llm_suffix"]
        return out

    return handler


def build_remote_tool_specs(ctx: "SkillToolContext",
                            modules: "list[Module]") -> "list[ToolSpec]":
    """Build proxy ToolSpecs for every service-module, from its committed manifest."""
    from atria.core.skill_tools import ToolSpec  # local import: avoid cycle at module load

    specs: list[ToolSpec] = []
    for module in modules:
        svc = getattr(module.manifest, "service", None) if module.manifest else None
        if not svc:
            continue
        conn = RemoteConnector(module.name, svc.connector_url, svc.health_path)
        for tool in svc.tools:
            name = tool.get("name")
            if not name:
                continue
            specs.append(ToolSpec(
                name=name,
                description=tool.get("description", ""),
                parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                handler=_make_handler(ctx, conn, name),
            ))
    return specs
