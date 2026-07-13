"""OpenAI-compatible embedding client used by dense indexing and query."""

from __future__ import annotations

import os

import httpx

_BATCH_SIZE = 64
_TIMEOUT_S = 30.0


class Embedder:
    """Thin synchronous client for an OpenAI-compatible /embeddings endpoint."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("SEARCH_EMBED_MODEL", "text-embedding-3-small")
        self.base_url = (
            base_url or os.environ.get("SEARCH_EMBED_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get(
            "SEARCH_EMBED_API_KEY", os.environ.get("OPENAI_API_KEY", "")
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in order, batching requests."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            response = httpx.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": batch},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_TIMEOUT_S,
            )
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda r: r["index"])
            vectors.extend([row["embedding"] for row in rows])
        return vectors
