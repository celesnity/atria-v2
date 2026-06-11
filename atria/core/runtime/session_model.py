"""Per-session model configuration overlay.

Stores a sparse dict in session.metadata["session_model"] with only the slots
the user explicitly set. Missing keys fall through to global config.

Precedence: session-model > project config > global config > defaults
"""

from __future__ import annotations

import logging
from typing import Any

from atria.models.config import AppConfig

logger = logging.getLogger(__name__)

SESSION_MODEL_FIELDS = {
    "model",
    "model_thinking",
    "model_vlm",
    "model_critique",
    "model_compact",
}


class SessionModelManager:
    """Manages the session-model overlay lifecycle.

    Tracks original config values so we can:
    - Restore before save_config() to prevent leaking overlay to settings.json
    - Revert on /session-model clear or /clear
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._originals: dict[str, Any] = {}
        self._active_overlay: dict[str, str] | None = None

    @property
    def is_active(self) -> bool:
        return self._active_overlay is not None and len(self._active_overlay) > 0

    def apply(self, overlay: dict[str, str]) -> None:
        """Apply overlay to config, saving originals for later restoration."""
        if not overlay:
            return
        self._active_overlay = dict(overlay)
        self._originals = {}
        for key, value in overlay.items():
            if key not in SESSION_MODEL_FIELDS:
                continue
            self._originals[key] = getattr(self._config, key)
            setattr(self._config, key, value)

        # Recalculate max_context_tokens if normal model changed
        if "model" in overlay:
            model_info = self._config.get_model_info()
            if model_info and model_info.context_length:
                self._originals.setdefault("_max_context_tokens", self._config.max_context_tokens)
                self._config.max_context_tokens = int(model_info.context_length * 0.8)

    def restore(self) -> None:
        """Restore original config values, removing overlay."""
        for key, value in self._originals.items():
            if key == "_max_context_tokens":
                self._config.max_context_tokens = value
            else:
                setattr(self._config, key, value)
        self._originals = {}
        self._active_overlay = None

    def get_overlay(self) -> dict[str, str] | None:
        """Return current overlay dict (for persistence)."""
        return dict(self._active_overlay) if self._active_overlay else None


def get_session_model(session) -> dict[str, str] | None:
    """Read session-model overlay from session.metadata."""
    return session.metadata.get("session_model")


def set_session_model(session, overlay: dict[str, str]) -> None:
    """Write session-model overlay to session.metadata."""
    session.metadata["session_model"] = overlay


def clear_session_model(session) -> None:
    """Remove session-model overlay from session.metadata."""
    session.metadata.pop("session_model", None)


def validate_session_model(overlay: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Validate overlay entries against model registry.

    Returns:
        (valid_overlay, warnings) - valid entries and warning messages for dropped ones
    """
    if not overlay:
        return {}, []

    valid = {}
    warnings = []

    try:
        from atria.config import get_model_registry

        registry = get_model_registry()
    except Exception:
        # Can't validate without registry, keep all entries
        return {k: v for k, v in overlay.items() if k in SESSION_MODEL_FIELDS}, []

    for key, value in overlay.items():
        if key not in SESSION_MODEL_FIELDS:
            continue
        result = registry.find_model_by_id(value)
        if result:
            valid[key] = value
        else:
            warnings.append(f"Model '{value}' no longer available, removed from session")

    return valid, warnings
