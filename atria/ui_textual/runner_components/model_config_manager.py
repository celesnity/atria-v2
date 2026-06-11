"""Model configuration management for TextualRunner.

This module handles model configuration, switching, and UI updates for model slots.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from atria.core.runtime import ConfigManager
from atria.repl.repl import REPL


class ModelConfigManager:
    """Manages model configuration, selection, and UI updates."""

    def __init__(
        self,
        config_manager: ConfigManager,
        repl: REPL,
    ) -> None:
        """Initialize the manager.

        Args:
            config_manager: Configuration manager instance.
            repl: REPL instance for agent rebuilding and commands.
        """
        self._config_manager = config_manager
        self._repl = repl
        self._app: Any | None = None

    def set_app(self, app: Any) -> None:
        """Set the Textual app instance for UI updates."""
        self._app = app

    def get_model_config_snapshot(self) -> dict[str, dict[str, str]]:
        """Return current model configuration details for the UI."""
        config = self._config_manager.get_config()

        try:
            from atria.config import get_model_registry

            registry = get_model_registry()
        except Exception:  # pragma: no cover - defensive
            registry = None

        def resolve(model_id: Optional[str]) -> dict[str, str]:
            if not model_id:
                return {}
            model_display = model_id
            if registry is not None:
                found = registry.find_model_by_id(model_id)
                if found:
                    _, _, model_info = found
                    model_display = model_info.name
            elif "/" in model_id:
                model_display = model_id.split("/")[-1]
            return {"model": model_id, "model_display": model_display}

        snapshot: dict[str, dict[str, str]] = {}
        snapshot["normal"] = resolve(config.model)
        if entry := resolve(config.model_thinking):
            snapshot["thinking"] = entry
        if entry := resolve(config.model_vlm):
            snapshot["vision"] = entry
        if entry := resolve(config.model_critique):
            snapshot["critique"] = entry
        if entry := resolve(config.model_compact):
            snapshot["compact"] = entry

        return snapshot

    def refresh_ui_config(self) -> None:
        """Refresh cached config-driven UI indicators after config changes."""
        if not self._app:
            return

        # Use get_model_config_snapshot as single source of truth for display names
        snapshot = self.get_model_config_snapshot()
        normal_info = snapshot.get("normal", {})
        model_display = normal_info.get("model_display", "")

        # Append [session] indicator if session-model overlay is active
        session_model_mgr = getattr(self._repl, "session_model_manager", None)
        if session_model_mgr and session_model_mgr.is_active:
            model_display += " [session]"

        if hasattr(self._app, "update_primary_model"):
            self._app.update_primary_model(model_display)
        if hasattr(self._app, "update_model_slots"):
            self._app.update_model_slots(self._build_model_slots(snapshot))

    async def apply_model_selection(self, slot: str, provider_id: str, model_id: str) -> Any:
        """Apply a model selection coming from the Textual UI."""
        # This calls internal repl methods.
        # We assume repl.config_commands exists and has _switch_to_model
        if not hasattr(self._repl, "config_commands"):
            # Fallback if config_commands not available (e.g. dummy repl)
            from types import SimpleNamespace

            return SimpleNamespace(success=False, message="Config commands not available")

        result = await asyncio.to_thread(
            self._repl.config_commands._switch_to_model,
            provider_id,
            model_id,
            slot,
        )
        if result.success:
            # Rebuild agents with new config (needed for API key changes)
            await asyncio.to_thread(self._repl.rebuild_agents)
            self.refresh_ui_config()
        return result

    async def apply_session_model_selection(
        self, slot: str, provider_id: str, model_id: str
    ) -> Any:
        """Apply a model selection to the session overlay instead of global config."""
        from types import SimpleNamespace

        from atria.core.runtime.session_model import set_session_model

        session_mgr = getattr(self._repl, "session_manager", None)
        session_model_mgr = getattr(self._repl, "session_model_manager", None)

        if not session_mgr or not session_model_mgr:
            return SimpleNamespace(success=False, message="Session manager not available")

        session = await session_mgr.get_current_session()
        if not session:
            return SimpleNamespace(success=False, message="No active session")

        slot_to_key = {
            "normal": "model",
            "thinking": "model_thinking",
            "vision": "model_vlm",
            "critique": "model_critique",
            "compact": "model_compact",
        }

        model_key = slot_to_key.get(slot, "model")
        overlay = session_model_mgr.get_overlay() or {}
        overlay[model_key] = model_id

        # Restore old overlay, apply updated one
        session_model_mgr.restore()
        session_model_mgr.apply(overlay)

        # Persist to session metadata
        set_session_model(session, overlay)
        session_mgr.save_session()

        # Rebuild agents with new config
        await asyncio.to_thread(self._repl.rebuild_agents)
        self.refresh_ui_config()

        return SimpleNamespace(success=True, message="")

    def _build_model_slots(
        self, snapshot: Optional[dict[str, dict[str, str]]] = None
    ) -> dict[str, tuple[str, str]]:
        """Prepare formatted model slot information for the footer.

        Args:
            snapshot: Optional pre-computed snapshot from get_model_config_snapshot().
                      If not provided, will compute it.
        """
        if snapshot is None:
            snapshot = self.get_model_config_snapshot()

        def extract_slot(slot_name: str) -> tuple[str, str] | None:
            info = snapshot.get(slot_name, {})
            if not info:
                return None
            provider_display = info.get("provider_display", "")
            model_display = info.get("model_display", "")
            if not provider_display or not model_display:
                return None
            return (provider_display, model_display)

        slots = {}

        normal = extract_slot("normal")
        if normal:
            slots["normal"] = normal

        # Show thinking slot if explicitly set (even if same as normal)
        thinking = extract_slot("thinking")
        if thinking:
            slots["thinking"] = thinking

        # Show vision slot if explicitly set (even if same as normal)
        vision = extract_slot("vision")
        if vision:
            slots["vision"] = vision

        # Show critique slot if explicitly set
        critique = extract_slot("critique")
        if critique:
            slots["critique"] = critique

        # Show compact slot if explicitly set
        compact = extract_slot("compact")
        if compact:
            slots["compact"] = compact

        return slots
