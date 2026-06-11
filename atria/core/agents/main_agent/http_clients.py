"""HTTP client management for LLM access."""

from typing import Any

from atria.core.agents.components import create_http_client


class HttpClientMixin:
    """Mixin for lazy HTTP client initialization.

    Backing stores use ``_priv_*`` names to avoid Python name-mangling
    issues that arise when double-underscore attributes are defined in
    one class (``MainAgent.__init__``) but accessed via properties in a
    mixin (where the mangled name would differ).
    """

    @property
    def _http_client(self) -> Any:
        """Lazily create HTTP client on first access (defers API key validation)."""
        if self._priv_http_client is None:
            self._priv_http_client = create_http_client(self.config)
        return self._priv_http_client

    @property
    def _thinking_http_client(self) -> Any:
        return self._http_client

    @property
    def _critique_http_client(self) -> Any:
        return self._http_client

    @property
    def _vlm_http_client(self) -> Any:
        return self._http_client

    def _resolve_vlm_model_and_client(self, messages: list[dict]) -> tuple[str, Any]:
        """Resolve model/client, routing to VLM model when images are present."""
        if self._messages_contain_images(messages):
            vlm_info = self.config.get_vlm_model_info()
            if vlm_info is not None:
                _, vlm_model_id, _ = vlm_info
                return vlm_model_id, self._http_client
        return self.config.model, self._http_client
