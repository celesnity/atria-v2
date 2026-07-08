#!/usr/bin/env python
"""Bridge the Jarvis map copilot panel to the real main-chat agent.

The dashboard iframe can only run module scripts (AtriaDash bridge), so this
script is the loopback hop. stdin JSON:
  {"message", "chat_session_id", "viewport": {lat,lng,zoom}?, "pins": [{n,poi_id,name}]?}
stdout JSON (ASCII-safe, exit 0 even on agent errors):
  {"reply", "session_id", "error", "map_actions": [...], "source": "fast"|"agent"}

Two answer paths:
  fast  — simple search / nearby / route intents are resolved deterministically
          with the local search engine; the LLM is never called.
  agent — everything else POSTs to /api/modules/tasco_jarvis_map/chat with a
          grounding preamble (top search candidates, poi_ids only). The agent
          ends its reply with a fenced ```map-json block naming poi_ids; we
          validate it, resolve ids to real coords from the dataset, and strip
          the block. The LLM never emits coordinates — garbled output degrades
          to a reply without pins, never wrong pins.

map_actions vocabulary (dashboard applyActions):
  {"type":"pins","items":[{n,poi_id,name,lat,lng,category,rating,detail}],"fit":true}
  {"type":"focus","lat":..,"lng":..,"zoom":..}
  {"type":"clear","what":"ai"|"route"|"all"}
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import fold, load_abbreviations, load_json, normalize_query  # noqa: E402
from search import _category_index, _detect_category, cmd_near, cmd_search  # noqa: E402

MODULE_NAME = "tasco_jarvis_map"

_GREETING_RE = re.compile(r"^(hi|hii+|hey+|hello|helo|yo|chao|xin chao|alo|hallo)\b")
_ROUTE_RE = re.compile(
    r"duong di|chi duong|dan duong|di den|di toi|\bdi tu\b|tu .{2,40} den |"
    r"direction|\broute\b|how (do i|to) get|navigate"
)
_NEAR_RE = re.compile(r"\bgan day\b|\bgan toi\b|quanh day|xung quanh|near me|nearby|around here")
# Reasoning-ish questions go to the agent even when short.
_COMPLEX_RE = re.compile(
    r"\bnen\b|nao tot|nao ngon|vi sao|tai sao|so sanh|compare|recommend|goi y|"
    r"tu van|\bwhy\b|\bbest\b|tot nhat|ngon nhat|re nhat|đat nhat|danh gia|review|"
    r"mo cua|gio mo|open (late|now|until)|\bopen\b.*\b(am|pm)\b"
)

GREETING_PREAMBLE = (
    "[You are Jarvis, a friendly Vietnam map copilot. Reply to this greeting in "
    'ONE short sentence in the user\'s language, e.g. "Xin chào, bạn muốn tìm địa '
    'điểm nào?". Do not narrate or explain.]\n'
)

PREAMBLE_HEAD = (
    "[You are Jarvis, the Tasco map copilot for Vietnam (HCMC, Hanoi, Da Nang). "
    "Answer ONLY from the CANDIDATES list below — never invent places, addresses "
    "or coordinates, and never explore the filesystem. Reply in the user's "
    "language, 2-4 short sentences, numbering your picks 1..k to match the pins. "
    "End your reply with EXACTLY one fenced block in this form:\n"
    "```map-json\n"
    '{"actions":[{"type":"pins","items":[{"n":1,"poi_id":"POI001"}]}]}\n'
    "```\n"
    "Use ONLY poi_id values from CANDIDATES; n must match your prose numbering. "
    "If no candidate fits, say so and emit {\"actions\":[]}.]\n"
)


def _emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def _is_vietnamese(message: str) -> bool:
    if any(ord(ch) > 127 for ch in message):
        return True
    f = fold(message)
    return bool(re.search(
        r"\bquan\b|\bgan\b|\btim\b|\bo dau\b|\bcho\b|\bnha\b|\bquan an\b|"
        r"\bduong\b|\bden\b|\bdi\b|\bsan bay\b|\bben xe\b|\bthuoc\b|\bxang\b", f))


def _pin_items(results: list[dict], with_distance: bool = False) -> list[dict]:
    items = []
    for i, r in enumerate(results):
        detail = r.get("address") or ""
        if with_distance and r.get("distance_km") is not None:
            detail = f"{r['distance_km']} km · {detail}"
        items.append({
            "n": i + 1, "poi_id": r["poi_id"], "name": r["name"],
            "lat": r["lat"], "lng": r["lng"], "category": r["category"],
            "rating": r.get("rating"), "detail": detail,
        })
    return items


def _fast_reply_lines(items: list[dict], vi: bool) -> str:
    lines = []
    for it in items:
        star = f" ★{it['rating']}" if it.get("rating") else ""
        lines.append(f"{it['n']}. {it['name']}{star}")
    return "\n".join(lines)


def _try_fast_path(message: str, folded: str, viewport: dict | None) -> dict | None:
    """Deterministic answers for simple intents. Returns a full response payload
    or None to fall through to the agent."""
    vi = _is_vietnamese(message)

    if _ROUTE_RE.search(folded):
        reply = ("Chỉ đường sẽ có trong bản cập nhật tới — hiện tại tôi có thể tìm "
                 "địa điểm và ghim lên bản đồ giúp bạn."
                 if vi else
                 "Directions are coming in the next update — for now I can find "
                 "places and pin them on the map for you.")
        return {"reply": reply, "map_actions": [], "source": "fast"}

    if _NEAR_RE.search(folded) and viewport and viewport.get("lat") is not None:
        terms, max_ngram = load_abbreviations()
        norm = normalize_query(message, terms, max_ngram)
        categories = load_json("pois.json")["categories"]
        cat_key, _ = _detect_category(norm, _category_index(categories))
        res = cmd_near(SimpleNamespace(
            lat=float(viewport["lat"]), lng=float(viewport["lng"]),
            radius_km=3.0, category=cat_key, limit=5))
        items = _pin_items(res["results"], with_distance=True)
        if not items:
            reply = ("Không tìm thấy địa điểm phù hợp trong ~3 km quanh khu vực bản đồ."
                     if vi else "No matching places within ~3 km of the map view.")
            return {"reply": reply, "map_actions": [], "source": "fast"}
        reply = (f"Có {len(items)} địa điểm gần khu vực bạn đang xem:\n"
                 if vi else f"Found {len(items)} places near the current map view:\n")
        reply += _fast_reply_lines(items, vi)
        return {"reply": reply,
                "map_actions": [{"type": "pins", "items": items, "fit": True}],
                "source": "fast"}

    # Plain search: short message, no reasoning language, and a confident hit.
    if not _COMPLEX_RE.search(folded) and len(folded.split()) <= 6:
        res = cmd_search(SimpleNamespace(query=message, limit=5, city=None, category=None))
        results = res.get("results") or []
        if results and results[0].get("score", 0) >= 55:
            items = _pin_items(results)
            reply = (f"Tìm thấy {len(items)} địa điểm cho \"{message}\" — đã ghim lên bản đồ:\n"
                     if vi else
                     f"Found {len(items)} places for \"{message}\" — pinned on the map:\n")
            reply += _fast_reply_lines(items, vi)
            return {"reply": reply,
                    "map_actions": [{"type": "pins", "items": items, "fit": True}],
                    "source": "fast"}
    return None


_MAP_JSON_RE = re.compile(r"```map-json\s*(\{.*?\})\s*```", re.S)


def _extract_map_actions(reply: str) -> tuple[str, list[dict]]:
    """Pull the fenced map-json block out of an agent reply and resolve poi_ids
    to real dataset coordinates. Unknown/garbled input -> no actions."""
    m = _MAP_JSON_RE.search(reply)
    if not m:
        return reply.strip(), []
    stripped = (reply[: m.start()] + reply[m.end():]).strip()
    try:
        block = json.loads(m.group(1))
        raw_actions = block.get("actions") or []
    except (ValueError, AttributeError):
        return stripped, []

    poi_by_id = {p["poi_id"]: p for p in load_json("pois.json")["pois"]}
    actions: list[dict] = []
    for a in raw_actions:
        if not isinstance(a, dict):
            continue
        if a.get("type") == "pins":
            items = []
            for i, it in enumerate(a.get("items") or []):
                p = poi_by_id.get(str(it.get("poi_id", "")))
                if p is None:
                    continue  # drop ids the model invented
                items.append({
                    "n": int(it.get("n") or (i + 1)), "poi_id": p["poi_id"],
                    "name": p["name"], "lat": p["lat"], "lng": p["lng"],
                    "category": p["category"], "rating": p["rating"],
                    "detail": p["address"],
                })
            if items:
                actions.append({"type": "pins", "items": items, "fit": True})
        elif a.get("type") == "clear" and a.get("what") in ("ai", "route", "all"):
            actions.append({"type": "clear", "what": a["what"]})
        # focus is dashboard/fast-path only; the agent stays on poi_ids
    return stripped, actions


def _candidates_block(message: str, viewport: dict | None, pins: list[dict]) -> str:
    res = cmd_search(SimpleNamespace(query=message, limit=10, city=None, category=None))
    lines = ["CANDIDATES (poi_id | name | category | district | city | rating):"]
    for r in res.get("results") or []:
        lines.append(f"  {r['poi_id']} | {r['name']} | {r['category']} | "
                     f"{r['district']} | {r['city']} | {r['rating']}")
    if len(lines) == 1:
        lines.append("  (no matches — say you could not find it in the dataset)")
    if viewport and viewport.get("lat") is not None:
        lines.append(f"VIEWPORT: {viewport['lat']:.4f},{viewport['lng']:.4f} z{viewport.get('zoom', '')}")
    if pins:
        shown = ", ".join(f"{p.get('n')} {p.get('name')} ({p.get('poi_id')})" for p in pins[:8])
        lines.append(f"ACTIVE PINS: {shown}")
    return "\n".join(lines) + "\n"


def main() -> int:
    api_base = os.environ.get("ATRIA_API_BASE")

    try:
        req_payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError as exc:
        print(f"ERROR: bad stdin JSON: {exc}", file=sys.stderr)
        return 1

    chat_session_id = req_payload.get("chat_session_id") or None
    message = (req_payload.get("message") or "").strip()
    if not message:
        print("ERROR: message is required", file=sys.stderr)
        return 1
    viewport = req_payload.get("viewport") or None
    pins = req_payload.get("pins") or []
    folded = fold(message)

    # Deterministic fast path — the LLM is never called for simple intents.
    fast = None
    try:
        fast = _try_fast_path(message, folded, viewport)
    except Exception as exc:  # dataset problems must not kill chat entirely
        print(f"WARN: fast path failed: {exc}", file=sys.stderr)
    if fast is not None:
        return _emit({"reply": fast["reply"], "session_id": chat_session_id,
                      "error": None, "map_actions": fast["map_actions"],
                      "source": "fast"})

    if not api_base:
        return _emit({"reply": "", "session_id": chat_session_id,
                      "error": "ATRIA_API_BASE is not set", "map_actions": [],
                      "source": "agent"})

    # Attribute the dedicated Jarvis session to the same browser user.
    context_session_id = os.environ.get("ATRIA_SESSION_ID") or None
    if context_session_id == "default":
        context_session_id = None
    try:
        user_id = int(os.environ.get("ATRIA_USER_ID", ""))
    except ValueError:
        user_id = None

    is_greeting = _GREETING_RE.match(folded) and len(message) <= 20
    if is_greeting:
        grounded = GREETING_PREAMBLE + "\nUser: " + message
    else:
        try:
            data_block = _candidates_block(message, viewport, pins)
        except Exception:
            data_block = ""
        grounded = PREAMBLE_HEAD + "\n" + data_block + "\nUser: " + message

    payload = {
        "message": grounded,
        "chat_session_id": chat_session_id,
        "context_session_id": context_session_id,
        "user_id": user_id,
    }
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/modules/{MODULE_NAME}/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=105) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return _emit({"reply": "", "session_id": chat_session_id,
                      "error": f"backend {exc.code}: {detail}",
                      "map_actions": [], "source": "agent"})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _emit({"reply": "", "session_id": chat_session_id,
                      "error": f"cannot reach backend: {exc}",
                      "map_actions": [], "source": "agent"})

    reply, actions = _extract_map_actions(data.get("reply") or "")
    return _emit({
        "reply": reply,
        "session_id": data.get("session_id") or chat_session_id,
        "error": data.get("error"),
        "map_actions": actions,
        "source": "agent",
    })


if __name__ == "__main__":
    raise SystemExit(main())
