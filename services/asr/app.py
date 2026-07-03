"""CPU ASR sidecar for nvidia/nemotron-3.5-asr-streaming-0.6b.

Two entry points:

- ``POST /v1/audio/transcriptions`` — OpenAI-compatible batch transcription
  (multipart ``file``), used by push-to-talk.
- ``WS /v1/realtime`` — live streaming: the client sends 16 kHz mono Int16 PCM
  binary frames; the sidecar re-decodes a rolling tail window every ~1 s and
  streams ``{"type":"partial","text":...}`` back, then ``final`` after
  ``{"type":"stop"}``. True cache-aware streaming needs NeMo+GPU; on CPU this
  incremental re-decode gives live-captions UX (~1–2 s behind speech).

The model is loaded lazily behind a lock and inference runs in a threadpool so
the event loop is never blocked. Audio container decoding (librosa/ffmpeg) is
imported lazily inside the batch path so the module stays importable without it.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

ASR_MODEL = os.environ.get("ASR_MODEL", "nvidia/nemotron-3.5-asr-streaming-0.6b")
TARGET_SR = 16_000

# ── Streaming (incremental re-decode) tuning — module attrs so tests can shrink them ──
BYTES_PER_SEC = TARGET_SR * 2  # Int16 mono
TICK_SEC = float(os.environ.get("ASR_TICK_SEC", "1.0"))  # partial-decode cadence
WINDOW_SEC = 10.0  # active tail window re-decoded each tick
COMMIT_SEC = 6.0  # oldest chunk committed once the window overflows
OVERLAP_SEC = 0.5  # window re-includes this much committed audio (naive join)
MAX_UTTERANCE_SEC = 60.0  # hard cap per streaming utterance
MIN_DECODE_SEC = 0.4  # don't decode until at least this much new audio exists

app = FastAPI(title="atria-asr", version="0.1.0")

_pipe = None
_pipe_lock = threading.Lock()


@app.on_event("startup")
def _warm_model() -> None:
    """Preload the model in a background thread so the first utterance isn't
    stalled ~20s by a cold load. /health stays responsive meanwhile."""
    threading.Thread(target=_get_pipe, daemon=True).start()


def _get_pipe():
    """Lazily construct the ASR pipeline once (thread-safe)."""
    global _pipe
    if _pipe is None:
        with _pipe_lock:
            if _pipe is None:
                from transformers import pipeline

                _pipe = pipeline("automatic-speech-recognition", model=ASR_MODEL)
    return _pipe


def _transcribe_file(raw: bytes, suffix: str) -> str:
    """Decode arbitrary audio bytes to 16 kHz mono and transcribe."""
    import librosa  # lazy: only the batch path needs container decoding

    # librosa reads compressed formats (webm/opus/mp3) via ffmpeg when given a
    # real path, so spill the upload to a temp file first.
    with tempfile.NamedTemporaryFile(suffix=suffix or ".bin", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        audio, _ = librosa.load(tmp_path, sr=TARGET_SR, mono=True)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    result = _get_pipe()({"raw": audio, "sampling_rate": TARGET_SR})
    text = result.get("text", "") if isinstance(result, dict) else str(result)
    return text.strip()


def _transcribe_pcm(raw: bytes) -> str:
    """Transcribe raw 16 kHz mono Int16 PCM bytes (the streaming path)."""
    if len(raw) < 2:
        return ""
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    result = _get_pipe()({"raw": audio, "sampling_rate": TARGET_SR})
    text = result.get("text", "") if isinstance(result, dict) else str(result)
    return text.strip()


def _join(committed: str, tail: str) -> str:
    """Naive text join of committed prefix and the live tail-window decode."""
    return f"{committed} {tail}".strip() if committed else tail.strip()


@app.get("/health")
async def health() -> dict:
    """Liveness probe. Server is up as soon as this responds; ``loaded`` tells
    whether the (lazy) model has been constructed yet."""
    return {"status": "ok", "model": ASR_MODEL, "loaded": _pipe is not None}


@app.websocket("/v1/realtime")
async def realtime(ws: WebSocket) -> None:
    """Live streaming transcription over WebSocket.

    Upstream: binary Int16 PCM @16 kHz mono frames; ``{"type":"stop"}`` ends the
    utterance. Downstream: ``partial`` JSON every ~TICK_SEC while audio arrives,
    one ``final`` after stop. Incremental re-decode with chunked commit: the tail
    window (≤ WINDOW_SEC) is re-decoded each tick; once the window overflows, the
    oldest COMMIT_SEC chunk's text is committed and the window slides, keeping
    per-tick CPU decode time bounded on long utterances.
    """
    await ws.accept()
    buffer = bytearray()
    committed = ""
    window_start = 0  # byte offset where the active window begins
    stopped = asyncio.Event()
    max_bytes = int(MAX_UTTERANCE_SEC * BYTES_PER_SEC)

    async def decode_loop() -> None:
        nonlocal committed, window_start
        last_len = 0
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=TICK_SEC)
                return  # stop arrived; final decode happens in the main path
            except asyncio.TimeoutError:
                pass
            if len(buffer) - last_len < int(MIN_DECODE_SEC * BYTES_PER_SEC):
                continue  # not enough new audio to be worth a decode
            last_len = len(buffer)
            try:
                # Chunked commit: slide the window when it overflows.
                while len(buffer) - window_start > int(WINDOW_SEC * BYTES_PER_SEC):
                    commit_end = window_start + int(COMMIT_SEC * BYTES_PER_SEC)
                    chunk_text = await run_in_threadpool(
                        _transcribe_pcm, bytes(buffer[window_start:commit_end])
                    )
                    committed = _join(committed, chunk_text)
                    window_start = max(window_start, commit_end - int(OVERLAP_SEC * BYTES_PER_SEC))
                tail_text = await run_in_threadpool(_transcribe_pcm, bytes(buffer[window_start:]))
                await ws.send_json({"type": "partial", "text": _join(committed, tail_text)})
            except Exception as e:  # noqa: BLE001 — report and keep the socket alive
                try:
                    await ws.send_json({"type": "error", "detail": f"decode failed: {e}"})
                except Exception:
                    return

    decoder = asyncio.create_task(decode_loop())
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return  # client vanished; no final
            data = msg.get("bytes")
            if data:
                if len(buffer) < max_bytes:
                    buffer += data[: max_bytes - len(buffer)]
                continue
            text = msg.get("text")
            if text:
                try:
                    if json.loads(text).get("type") == "stop":
                        break
                except (ValueError, AttributeError):
                    continue
        # Stop: settle the decoder, then one final decode of the remaining tail.
        stopped.set()
        await decoder
        try:
            tail_text = await run_in_threadpool(_transcribe_pcm, bytes(buffer[window_start:]))
            await ws.send_json({"type": "final", "text": _join(committed, tail_text)})
        except Exception as e:  # noqa: BLE001
            await ws.send_json({"type": "error", "detail": f"final decode failed: {e}"})
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        stopped.set()
        if not decoder.done():
            decoder.cancel()


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: str | None = Form(None),  # accepted for OpenAI compat; ignored
    language: str | None = Form(None),  # accepted for OpenAI compat; ignored
) -> dict:
    """OpenAI-compatible transcription: multipart ``file`` -> ``{"text": ...}``."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    suffix = os.path.splitext(file.filename or "")[1].lower() or ".webm"
    try:
        text = await run_in_threadpool(_transcribe_file, raw, suffix)
    except Exception as e:  # noqa: BLE001 — surface decode/inference failure as 500
        raise HTTPException(status_code=500, detail=f"transcription failed: {e}") from e
    return {"text": text}
