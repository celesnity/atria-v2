"""send_image tool — push an image to the web UI chat as a standalone bubble."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


class SendImageHandler:
    """Handler for the send_image tool.

    Accepts either a local server-side absolute path or a remote http(s) URL.
    Local files are base64-encoded into a data: URI. Remote URLs are passed
    through. The image is delivered to the UI via ui_callback.on_image().
    """

    _ALLOWED_MIMES = frozenset(
        {
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/svg+xml",
        }
    )
    _MAX_BYTES = 10 * 1024 * 1024  # 10 MB

    def send(self, args: dict[str, Any], context: Any) -> dict[str, Any]:
        path = (args.get("path") or "").strip()
        url = (args.get("url") or "").strip()
        caption = (args.get("caption") or "").strip()

        if bool(path) == bool(url):
            return {
                "success": False,
                "error": "Provide exactly one of 'path' or 'url'",
                "output": None,
            }

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_image"):
            return {
                "success": False,
                "error": "UI callback unavailable; send_image only works in the web UI",
                "output": None,
            }

        if url:
            if not (url.startswith("http://") or url.startswith("https://")):
                return {
                    "success": False,
                    "error": "URL must start with http:// or https://",
                    "output": None,
                }
            ui_callback.on_image(src=url, mime_type="", caption=caption)
            return {"success": True, "output": f"Sent image URL to UI: {url}"}

        p = Path(path)
        if not p.is_absolute():
            return {"success": False, "error": "Path must be absolute", "output": None}
        if not p.exists() or not p.is_file():
            return {"success": False, "error": f"File not found: {path}", "output": None}

        mime, _ = mimetypes.guess_type(str(p))
        if mime not in self._ALLOWED_MIMES:
            return {
                "success": False,
                "error": f"Unsupported image type: {mime or 'unknown'}",
                "output": None,
            }

        size = p.stat().st_size
        if size > self._MAX_BYTES:
            return {
                "success": False,
                "error": f"Image too large ({size} bytes; max {self._MAX_BYTES})",
                "output": None,
            }

        data = base64.b64encode(p.read_bytes()).decode("ascii")
        src = f"data:{mime};base64,{data}"
        ui_callback.on_image(src=src, mime_type=mime, caption=caption)
        return {"success": True, "output": f"Sent image to UI: {p.name} ({size} bytes)"}
