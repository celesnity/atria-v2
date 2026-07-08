#!/usr/bin/env python
"""Bridge the Minder dashboard widget to the real main-chat agent.

The dashboard iframe can only run module scripts (AtriaDash bridge), so this
script is the loopback hop: it reads ``{"message", "chat_session_id"}`` as JSON
on stdin, POSTs it to the backend's ``/api/modules/warehouse/chat`` route
(which awaits a full agent turn in a dedicated, auto-titled session) and
prints ``{"reply", "session_id", "error"}`` as ASCII-safe JSON on stdout.

Exit code 0 whenever a JSON answer could be produced (agent errors are carried
in the ``error`` field so the bridge resolves instead of throwing); 1 only on
transport/protocol failure.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
import urllib.error
import urllib.request

# Intent detection (diacritics-folded). A weak model won't reliably write
# files, so we produce reports deterministically; and we never let it pretend
# to make images (no image-generation tool exists).
_REPORT_RE = re.compile(
    r"report|bao cao|xuat|export|tai file|tai xuong|luu.*file|luu.*bao cao|"
    r"tao.*file|create.*file|generate.*file|make.*file|download|xuat.*file",
)
_IMAGE_RE = re.compile(r"image|hinh anh|hinh|anh|picture|photo|\bve\b|draw|graphic|do hoa")


def _fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()

# Grounding preamble. We inline the CURRENT warehouse snapshot into every
# question so the agent answers straight from data (reliable even with a weak
# model that won't drive a tool-call loop). Stock CHANGES still run the CLI —
# the session cwd is the warehouse module, so `python scripts/inventory.py
# sell/receive ...` works directly.
PREAMBLE_HEAD = (
    "[You are Minder, the warehouse assistant. Answer from the live warehouse "
    "data below — never invent numbers or explore the filesystem. To CHANGE "
    "stock run `python scripts/inventory.py sell --line SKU=QTY` / `... receive "
    "--sku SKU --qty N`. You cannot generate images; never claim to do something "
    "you didn't. Answer in ONE or TWO short sentences, in the user's language, "
    "and never narrate what you did.]\n"
)

# Greeting / small-talk only messages: answer in one line, no data needed.
GREETING_PREAMBLE = (
    "[You are Minder, a friendly warehouse assistant. Reply to this greeting in "
    "ONE short sentence in the user's language, e.g. \"Xin chào, tôi có thể giúp "
    "gì cho kho hàng?\". Do not narrate or explain.]\n"
)
_GREETING_RE = re.compile(r"^(hi|hii+|hey+|hello|helo|yo|chao|xin chao|alo|hallo)\b")


def _module_root() -> str:
    return os.environ.get("ATRIA_MODULE_ROOT") or os.getcwd()


def _generate_report() -> str | None:
    """Deterministically write a report file into the module dir (= the chat's
    working directory). Returns the relative path, or None on failure."""
    root = _module_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rel = os.path.join("reports", f"warehouse-report-{stamp}.md")
    script = os.path.join(root, "scripts", "inventory.py")
    try:
        proc = subprocess.run(
            [sys.executable, script, "report", "--out", rel, "--format", "md"],
            capture_output=True, text=True, encoding="utf-8", cwd=root, timeout=25,
        )
        if proc.returncode == 0 and os.path.isfile(os.path.join(root, rel)):
            return rel.replace(os.sep, "/")
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _fetch_snapshot_context() -> str:
    """Run inventory.py snapshot and format a compact data block for the agent.

    The /run route sets cwd + ATRIA_MODULE_ROOT to the warehouse module, so the
    script path resolves directly. Returns "" on any failure (the agent can
    still fall back to running the CLI itself).
    """
    root = os.environ.get("ATRIA_MODULE_ROOT") or os.getcwd()
    script = os.path.join(root, "scripts", "inventory.py")
    try:
        proc = subprocess.run(
            [sys.executable, script, "snapshot"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=root, timeout=25,
        )
        if proc.returncode != 0:
            return ""
        snap = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""

    st = snap.get("stats", {})
    lines = [
        "CURRENT WAREHOUSE DATA (live):",
        (f"Totals: {st.get('skus', 0)} SKUs, {st.get('units', 0)} units, "
         f"value {st.get('value', 0):,.0f} VND, low {st.get('low_count', 0)}, "
         f"out {st.get('out_count', 0)}, sold today {st.get('sold_today_count', 0)}."),
        "Items (sku | name | vi | category | qty | reorder | price | status):",
    ]
    for it in snap.get("items", []):
        lines.append(
            f"  {it.get('sku','')} | {it.get('name','')} | {it.get('name_vi','')} | "
            f"{it.get('category','')} | {it.get('quantity',0)} | "
            f"{it.get('reorder_level',0)} | {it.get('unit_price',0):,.0f} | "
            f"{it.get('status','')}"
        )
    week = snap.get("week", [])
    if week:
        wk = ", ".join(f"{w.get('date','')[5:]}:{w.get('units',0)}" for w in week)
        lines.append(f"Units sold per day (last 7): {wk}")
    return "\n".join(lines) + "\n"


def main() -> int:
    api_base = os.environ.get("ATRIA_API_BASE")
    if not api_base:
        print(json.dumps({"reply": "", "session_id": None,
                          "error": "ATRIA_API_BASE is not set"}))
        return 0

    try:
        req_payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError as exc:
        print(f"ERROR: bad stdin JSON: {exc}", file=sys.stderr)
        return 1

    chat_session_id = req_payload.get("chat_session_id") or None

    # Forward the active chat session id so the backend can attribute the new
    # Minder session to the same user (history visibility).
    context_session_id = os.environ.get("ATRIA_SESSION_ID") or None
    if context_session_id == "default":
        context_session_id = None
    # Preferred identity: the logged-in browser user, resolved by the /run
    # route from the auth cookie and forwarded as ATRIA_USER_ID.
    try:
        user_id = int(os.environ.get("ATRIA_USER_ID", ""))
    except ValueError:
        user_id = None

    created_file = None
    action = req_payload.get("action") or "chat"
    if action == "save":
        if not chat_session_id:
            print("ERROR: chat_session_id is required for save", file=sys.stderr)
            return 1
        endpoint = "chat/save"
        payload = {
            "chat_session_id": chat_session_id,
            "create_workspace": bool(req_payload.get("create_workspace")),
            "context_session_id": context_session_id,
            "user_id": user_id,
        }
    else:
        message = (req_payload.get("message") or "").strip()
        if not message:
            print("ERROR: message is required", file=sys.stderr)
            return 1

        folded = _fold(message)
        endpoint = "chat"

        # Greeting / tiny small-talk: skip the snapshot + heavy preamble entirely
        # (cheap, one-line reply). Only when the whole message is short and has
        # no report/image intent.
        is_greeting = (
            _GREETING_RE.match(folded) and len(message) <= 20
            and not _REPORT_RE.search(folded) and not _IMAGE_RE.search(folded)
        )
        if is_greeting:
            message = GREETING_PREAMBLE + "\nUser: " + message
        else:
            # Intent handling for a weak model: create report files
            # deterministically ourselves, and never let it fake image gen.
            instructions = ""
            if _IMAGE_RE.search(folded) and not _REPORT_RE.search(folded):
                instructions = (
                    "\n[NOTE: The user seems to want an image. You CANNOT generate "
                    "images (no such tool exists). Say so plainly and offer a "
                    "text/markdown report or on-screen data instead.]"
                )
            elif _REPORT_RE.search(folded):
                rel = _generate_report()
                if rel:
                    created_file = rel
                    instructions = (
                        f"\n[NOTE: A report file `{rel}` has ALREADY been written to the "
                        "working directory for you. Tell the user the exact filename and "
                        "that it is available in the conversation's Files tab. Do NOT "
                        "claim to create any other file.]"
                    )
                else:
                    instructions = (
                        "\n[NOTE: The report file could not be generated; apologise and "
                        "suggest trying again. Do not claim a file was created.]"
                    )

            # Ground the turn: persona + live snapshot so the agent answers from
            # data without needing to drive a tool loop.
            data_block = _fetch_snapshot_context()
            message = (PREAMBLE_HEAD + (data_block and "\n" + data_block)
                       + instructions + "\nUser: " + message)

        payload = {
            "message": message,
            "chat_session_id": chat_session_id,
            "context_session_id": context_session_id,
            "user_id": user_id,
        }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/modules/warehouse/{endpoint}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=105) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        print(json.dumps({"reply": "", "session_id": chat_session_id,
                          "error": f"backend {exc.code}: {detail}"}))
        return 0
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(json.dumps({"reply": "", "session_id": chat_session_id,
                          "error": f"cannot reach backend: {exc}"}))
        return 0

    if action == "save":
        # Pass the save result through verbatim (ok/needs_workspace/workspace/title).
        print(json.dumps(data))
    else:
        print(json.dumps({
            "reply": data.get("reply") or "",
            "session_id": data.get("session_id") or chat_session_id,
            "error": data.get("error"),
            "file": created_file,
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
