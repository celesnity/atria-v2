"""Per-tool enable/disable API.

Lets the web UI toggle individual built-in tools on/off. Disabled tools are
stripped from the LLM ``tools`` array on the next request (see
:func:`minder.core.agents.components.schemas.disabled_tools.load_disabled_tools`),
cutting their schemas from context without a restart.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from minder.core.agents.components.schemas.disabled_tools import (
    all_builtin_tool_meta,
    load_disabled_tools,
)
from minder.core.paths import get_paths
from minder.web.state import get_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])


class DisabledToolsUpdate(BaseModel):
    """Body for PUT /api/tools."""

    disabled_tools: List[str]


def _serialize_tools() -> List[Dict[str, Any]]:
    """Return every built-in tool with its current enabled state."""
    disabled = load_disabled_tools()
    tools = []
    for meta in all_builtin_tool_meta():
        tools.append({**meta, "enabled": meta["name"] not in disabled})
    return tools


@router.get("")
async def list_tools() -> Dict[str, Any]:
    """List all built-in tools with name, description, category and enabled flag."""
    try:
        return {"tools": _serialize_tools()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def update_disabled_tools(update: DisabledToolsUpdate) -> Dict[str, Any]:
    """Persist the set of disabled tools to the global settings file.

    Unknown tool names are ignored. The write is a non-destructive merge — other
    keys in ``~/.minder/settings.json`` are preserved. Takes effect on the next
    LLM call (schemas are rebuilt per request).
    """
    try:
        known = {m["name"] for m in all_builtin_tool_meta()}
        disabled = sorted({name for name in update.disabled_tools if name in known})

        # Merge into the global settings file, preserving unrelated keys.
        settings_path = get_paths().global_settings
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if settings_path.exists():
            raw = settings_path.read_text().strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        data = parsed
                except json.JSONDecodeError:
                    logger.warning("global settings.json is not valid JSON; rewriting fresh")
        data["disabled_tools"] = disabled
        settings_path.write_text(json.dumps(data, indent=2))

        # Keep the in-memory config in sync so it survives further save_config calls.
        try:
            state = get_state()
            state.config_manager.get_config().disabled_tools = disabled
        except Exception:
            pass  # web state may be unavailable in some contexts

        return {"status": "success", "tools": _serialize_tools()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
