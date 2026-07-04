"""Speech-to-text endpoint — thin authed proxy to an external ASR service.

The browser records a short push-to-talk clip and POSTs it here; we forward it
to whatever OpenAI-compatible transcription backend ``ATRIA_ASR_BASE_URL`` points
at (the local `asr` CPU sidecar by default, but a managed HF/NIM endpoint or a
Whisper server are drop-in swaps). The design principle is *audio in -> text
out, backend swappable* — nothing here is Nemotron-specific.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from atria.web.dependencies.auth import require_authenticated_user

router = APIRouter(
    prefix="/api/transcribe",
    tags=["transcribe"],
    dependencies=[Depends(require_authenticated_user)],
)

# 25 MB — a generous ceiling for a push-to-talk clip; blocks accidental huge uploads.
_MAX_BYTES = 25 * 1024 * 1024
_DEFAULT_BASE_URL = "http://localhost:9000/v1"


def _asr_config() -> tuple[str, str, str | None]:
    """Return (base_url, model, api_key) for the ASR backend, from env."""
    base_url = os.environ.get("ATRIA_ASR_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("ATRIA_ASR_MODEL", "nvidia/nemotron-3.5-asr-streaming-0.6b")
    api_key = os.environ.get("ATRIA_ASR_API_KEY") or None
    return base_url, model, api_key


@router.post("")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Forward an audio clip to the ASR backend and return ``{"text": ...}``."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (max 25 MB)")

    base_url, model, api_key = _asr_config()
    url = f"{base_url}/audio/transcriptions"
    files = {"file": (file.filename or "audio.webm", raw, file.content_type or "audio/webm")}
    data = {"model": model}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, files=files, data=data, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"ASR backend error: {e.response.status_code}"
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ASR backend unreachable: {e}") from e

    text = payload.get("text", "") if isinstance(payload, dict) else ""
    return {"text": text}
