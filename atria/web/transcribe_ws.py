"""Streaming speech-to-text WebSocket — thin proxy to the ASR sidecar.

The browser streams 16 kHz mono Int16 PCM binary frames to ``/ws/transcribe``;
this endpoint pipes them to the ASR sidecar's ``/v1/realtime`` socket (derived
from ``ATRIA_ASR_BASE_URL``) and relays ``partial``/``final`` transcript JSON
back. Engine-agnostic: any backend speaking the same tiny protocol is a
config-only swap.

Auth mirrors the main ``/ws`` chat socket (cookie-based, soft): browsers cannot
set Authorization headers on WebSocket upgrades, so Keycloak bearer-token
deployments carry no usable header here — exactly why ``/ws`` attaches the user
when the cookie is valid and accepts regardless. The audio stream is no more
sensitive than the chat stream riding ``/ws``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:9000/v1"


def _asr_realtime_url() -> str:
    """Derive the sidecar's realtime WS URL from ATRIA_ASR_BASE_URL."""
    base = os.environ.get("ATRIA_ASR_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return f"{base}/realtime"


async def transcribe_ws_endpoint(websocket: WebSocket) -> None:
    """Bidirectional pipe: browser PCM/stop -> sidecar; sidecar JSON -> browser."""
    # Soft cookie auth, same pattern as websocket_endpoint (atria/web/websocket.py).
    from atria.web.routes.auth import TOKEN_COOKIE, verify_token
    from atria.web.state import get_state

    token = websocket.cookies.get(TOKEN_COOKIE)
    if token:
        try:
            user_id_str = verify_token(token)
            state = get_state()
            user = await state.user_store.get_by_id(int(user_id_str))
            if user:
                websocket.scope["user"] = user
        except Exception:
            pass  # fall through, mirroring /ws

    await websocket.accept()

    import websockets  # local import so unit tests can monkeypatch cleanly

    url = _asr_realtime_url()
    try:
        upstream = await websockets.connect(url, max_size=2**22)
    except Exception as e:  # noqa: BLE001 — sidecar down/unreachable
        logger.warning("ASR realtime upstream unreachable at %s: %s", url, e)
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "detail": "ASR streaming backend unreachable"})
            )
            await websocket.close()
        except Exception:
            pass
        return

    async def pump_up() -> None:
        """Browser -> sidecar: binary PCM frames + the stop control message."""
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data:
                await upstream.send(data)
            elif msg.get("text"):
                await upstream.send(msg["text"])

    async def pump_down() -> None:
        """Sidecar -> browser: partial/final/error JSON passthrough."""
        async for frame in upstream:
            if isinstance(frame, bytes):
                frame = frame.decode("utf-8", errors="replace")
            await websocket.send_text(frame)

    up_task = asyncio.create_task(pump_up())
    down_task = asyncio.create_task(pump_down())
    try:
        done, pending = await asyncio.wait(
            {up_task, down_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        # Surface unexpected pump failures (normal closes return/StopIteration out).
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, (WebSocketDisconnect,)):
                logger.warning("transcribe WS pump ended with error: %s", exc)
    finally:
        try:
            await upstream.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
