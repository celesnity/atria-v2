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
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import fold, haversine_km, load_abbreviations, load_json, normalize_query  # noqa: E402
from search import (  # noqa: E402
    _category_index, _category_radius, _detect_category, _time_ok, cmd_near, cmd_search,
)
from session_context import clear_context, load_context, save_context  # noqa: E402

MODULE_NAME = "tasco_jarvis_map"

_GREETING_RE = re.compile(r"^(hi|hii+|hey+|hello|helo|yo|chao|xin chao|alo|hallo)\b")

# Chit-chat guard for the deterministic fast path: a message that is ENTIRELY a
# greeting / thanks / farewell (+ optional politeness particles and punctuation).
# Full-match anchored on the folded text, so real queries like "highlands coffee"
# (starts with "hi") or "bv bach mai" never match. Reused by _chitchat_kind below.
_CHIT_FILLER = r"(?:\s+(?:there|ban|nhe|nha|oi|a|jarvis|you|u|all|guys))*"
_CHIT_GREET_RE = re.compile(
    rf"^\s*(?:hi+|hey+|hello+|helo|hallo|halo|yo+|chao|xin chao|alo|hola|"
    rf"good (?:morning|afternoon|evening)){_CHIT_FILLER}[\s!.,?~]*$")
_CHIT_THANKS_RE = re.compile(
    rf"^\s*(?:thank you|thank u|thankyou|thanks|thank|thx|tks|ty|"
    rf"cam on|cang on|cam ang){_CHIT_FILLER}[\s!.,?~]*$")
_CHIT_BYE_RE = re.compile(
    rf"^\s*(?:bye+|byebye|good ?bye|see you|tam biet){_CHIT_FILLER}[\s!.,?~]*$")
# Navigation / nearby / coordinate intents are now detected by the query_intent
# router (via cmd_search), not by regex here. Reasoning questions still bypass
# the plain-search fast path so the agent handles them.
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
    "Never fabricate an attribute or opening hours that the CANDIDATES rows do "
    "not show; if the data cannot confirm a requested detail (parking, a private "
    "room, a named feature), still pick the closest candidates but briefly note "
    "the data cannot confirm that detail rather than presenting them as a full match. "
    "Treat any city / district / street / anchor / coordinate the user gave as a "
    "HARD constraint: candidates are already scoped to it, so never widen to another "
    "city, and never replace a location-scoped search with unrelated global results. "
    "When the requested district or place has no exact match, the candidates are the "
    "nearest in the SAME city -- say so instead of implying they sit in it. "
    "When a candidate row carries a distance, state it. "
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
            "opening_hours": r.get("opening_hours"),
            # per-POI "why this matches" (matched amenities/attributes); empty for
            # non-semantic turns, so pins carry a reasons key only when meaningful.
            "reasons": r.get("reasons") or [],
            # per-need confirmation status (confirmed / not_confirmed) when the
            # query carried needs — powers honest "wifi confirmed / not confirmed".
            "matched_needs": r.get("matched_needs") or [],
        })
    return items


def _needs_caveat(res: dict, vi: bool) -> str:
    """An honest one-line note when the hard needs could not be confirmed in the
    data (graceful fallback): the places are the closest matches but the data does
    not confirm the requested amenity. Anti-fabrication: never claim it's a match."""
    needs = res.get("needs") or {}
    if not needs.get("hard_relaxed"):
        return ""
    keys = list(needs.get("must_have") or [])
    keys += [n.get("key") for n in (needs.get("numeric") or [])]
    keys = [k for k in keys if k]
    if not keys:
        return ""
    label = ", ".join(keys)
    return (f"\n(Lưu ý: dữ liệu chưa xác nhận {label} cho các địa điểm này.)"
            if vi else f"\n(Note: the data cannot confirm {label} for these places.)")


def _reason_suffix(it: dict) -> str:
    """' · wifi, yên tĩnh, phù hợp làm việc' — the top matched amenities that
    explain why this POI was returned. Empty when the turn surfaced no reasons."""
    rs = it.get("reasons") or []
    return f" · {', '.join(rs[:3])}" if rs else ""


def _fast_reply_lines(items: list[dict], vi: bool, want_hours: bool = False) -> str:
    lines = []
    for it in items:
        star = f" ★{it['rating']}" if it.get("rating") else ""
        hrs = f" · {it['opening_hours']}" if want_hours and it.get("opening_hours") else ""
        lines.append(f"{it['n']}. {it['name']}{star}{hrs}{_reason_suffix(it)}")
    return "\n".join(lines)


def _fast_reply_lines_split(items: list[dict], n_exact: int, vi: bool,
                            want_hours: bool = False, divider: str | None = None) -> str:
    """Same numbered list as _fast_reply_lines, but with a labeled divider after
    the n_exact-th item so the top block reads apart from the fills below it. No
    divider when every item is above the split (n_exact == len) or none is
    (n_exact == 0). `divider` defaults to the brand-fills label."""
    if divider is None:
        divider = ("— Địa điểm chất lượng cao khác gần đó —" if vi
                   else "— Other highly-rated nearby —")
    lines = []
    for it in items:
        star = f" ★{it['rating']}" if it.get("rating") else ""
        hrs = f" · {it['opening_hours']}" if want_hours and it.get("opening_hours") else ""
        lines.append(f"{it['n']}. {it['name']}{star}{hrs}{_reason_suffix(it)}")
        if it["n"] == n_exact and 0 < n_exact < len(items):
            lines.append(divider)
    return "\n".join(lines)


def _grouped_reply_lines(items: list[dict], vi: bool, want_hours: bool = False) -> str:
    """Top-3 best first, then a '— More suggestions —' divider, then the rest.
    Results already arrive best-first (score, or distance for nearby), so this is
    presentation only. With ≤3 items the split guard emits no divider."""
    divider = "— Gợi ý thêm —" if vi else "— More suggestions —"
    return _fast_reply_lines_split(items, min(3, len(items)), vi, want_hours, divider=divider)


def _want_hours(res: dict) -> bool:
    return bool((res.get("entities") or {}).get("time"))


def _scope_prefix(res: dict, vi: bool) -> str:
    """Disclosure line when the requested district/street had no match, so the
    reply is honest that the shown places are the nearest alternatives."""
    scope = res.get("place_scope")
    if not scope or scope.get("matched", True):
        return ""
    where = scope.get("district") or scope.get("street") or ""
    return (f"Không có kết quả đúng tại '{where}' trong dữ liệu — đây là các lựa chọn gần nhất:\n"
            if vi else f"No exact match in '{where}' in the data — here are the nearest options:\n")


def _should_ask_city(res: dict) -> bool:
    """A category/brand turn with no resolved city whose candidates span more than
    one city — the interactive agent should ask which city rather than guess."""
    if res.get("anchor") is not None or res.get("city"):
        return False
    if not (res.get("category") or (res.get("entities") or {}).get("category")):
        return False
    cities = {r.get("city") for r in (res.get("results") or []) if r.get("city")}
    return len(cities) > 1


def _ask_city_payload(res: dict, vi: bool) -> dict:
    """Clarifying question naming the cities found; no pins. The pending category
    is remembered by the caller so the city reply re-runs the search (rule R1)."""
    cities = sorted({r["city"] for r in res.get("results") or [] if r.get("city")})
    listed = ", ".join(cities)
    reply = (f"Mình thấy kết quả ở {listed}. Bạn muốn tìm ở thành phố nào?"
             if vi else f"I found results in {listed}. Which city do you want?")
    return {"reply": reply, "map_actions": [], "source": "fast"}


def _chitchat_kind(folded: str) -> str | None:
    """'thanks' | 'bye' | 'greet' | None — None unless the WHOLE message is chit-chat."""
    if _CHIT_THANKS_RE.match(folded):
        return "thanks"
    if _CHIT_BYE_RE.match(folded):
        return "bye"
    if _CHIT_GREET_RE.match(folded):
        return "greet"
    return None


def _chitchat_payload(kind: str, vi: bool) -> dict:
    """A friendly, place-less reply so a greeting never triggers a search."""
    if kind == "thanks":
        reply = ("Không có gì! Cần tìm địa điểm nào nữa cứ nhắn mình nhé."
                 if vi else "Happy to help! Ask me about any place whenever you like.")
    elif kind == "bye":
        reply = ("Tạm biệt! Hẹn gặp lại." if vi else "Goodbye! See you next time.")
    else:
        reply = ("Xin chào! Mình là Jarvis — hỏi mình về địa điểm ở TP.HCM, Hà Nội "
                 "hay Đà Nẵng nhé." if vi else
                 "Hi! I'm Jarvis — ask me about places in HCMC, Hà Nội or Đà Nẵng.")
    return {"reply": reply, "map_actions": [], "source": "fast"}


def _try_fast_path(res: dict, message: str, folded: str, viewport: dict | None,
                   interactive: bool = False,
                   user_location: dict | None = None) -> dict | None:
    """Deterministic answers driven by the intent router (``res`` is a prebuilt
    cmd_search result so the caller can reuse it for context saving). Navigation,
    coordinate and anchored-nearby intents are resolved locally (the LLM is never
    called); plain hits pin when confident. Returns a full response payload or
    None to fall through to the agent."""
    vi = _is_vietnamese(message)
    # Greeting / thanks / farewell — reply conversationally, never run a place
    # search (fixes "hi" pinning Highlands Coffee via a "hi"->"highlands" prefix
    # score). Full-match anchored, so real queries fall through untouched.
    chit = _chitchat_kind(folded)
    if chit:
        return _chitchat_payload(chit, vi)
    intent = res.get("intent")
    results = res.get("results") or []
    anchor = res.get("anchor")
    want_hours = _want_hours(res)
    origin = (res.get("entities") or {}).get("origin")
    action = (res.get("entities") or {}).get("action")
    # GPS beats the map view: an explicit user_location is a truer origin for
    # distance / "near me" than wherever the map happens to be panned. Falls back
    # to the viewport, so behaviour is unchanged when no location is shared.
    user_here = bool(user_location and user_location.get("lat") is not None)
    origin_pt = user_location if user_here else viewport
    # A nearby answered from the user/viewport origin ("gần đây" / "gần tôi", or any
    # nearby that names no place). Honest ONLY when NO city was named: a named-city
    # nearby whose landmark anchor merely failed to geocode ("khách sạn gần biển đà
    # nẵng") must use the city-filtered results below — answering it from the
    # (possibly stale) viewport leaks the previous turn's city. `named_scope` is the
    # sole discriminator; a self-referential cue adds nothing it doesn't already decide.
    named_scope = bool(res.get("city"))
    origin_nearby = intent == "Nearby Search" and not anchor and not named_scope
    # Interactive-only: ask which city when a category turn is city-ambiguous. But
    # a shared GPS + "near me" already pins the city (the user's own location), so
    # don't ask — fall through to the origin-based nearby answer.
    if interactive and _should_ask_city(res) and not (user_here and origin_nearby):
        return _ask_city_payload(res, vi)

    # "Toa do cua X" — state the coordinates of the resolved POI. No LLM.
    if action == "coordinate_lookup" and results:
        top = results[0]
        loc = ", ".join(x for x in (top.get("district"), top.get("city")) if x)
        actions = [{"type": "pins", "items": _pin_items([top]), "fit": False},
                   {"type": "focus", "lat": top["lat"], "lng": top["lng"], "zoom": 15}]
        tail = f" ({loc})" if loc else ""
        reply = (f"{top['name']} ở toạ độ {top['lat']:.5f}, {top['lng']:.5f}{tail}."
                 if vi else
                 f"{top['name']} is at {top['lat']:.5f}, {top['lng']:.5f}{tail}.")
        return {"reply": reply, "map_actions": actions, "source": "fast"}

    # Reverse geocode ("<coord> là chỗ nào"): describe the spot, don't list options.
    if res.get("reverse_geocode") and anchor and results:
        top = results[0]
        items = _pin_items(results[:3], with_distance=True)
        actions = [{"type": "pins", "items": items, "fit": True},
                   {"type": "focus", "lat": anchor["lat"], "lng": anchor["lng"], "zoom": 15}]
        d = top.get("distance_km")
        dtxt = (f", cách ~{d} km" if vi else f", ~{d} km away") if d is not None else ""
        loc = ", ".join(x for x in (top.get("district"), top.get("city")) if x)
        addr = top.get("address") or ""
        where = (f" ({addr})" if addr else "") + dtxt + (f" — {loc}" if loc else "")
        reply = (f"Vị trí đó nằm gần {top['name']}{where}."
                 if vi else f"That location is near {top['name']}{where}.")
        return {"reply": reply, "map_actions": actions, "source": "fast"}

    # Navigation: focus the destination, pin it, draw a straight route from the
    # current viewport, and report the as-the-crow-flies distance. No LLM.
    if intent == "Navigation" and results:
        dest = results[0]
        actions = [{"type": "pins", "items": _pin_items([dest]), "fit": False},
                   {"type": "focus", "lat": dest["lat"], "lng": dest["lng"], "zoom": 15}]
        dist_txt = ""
        if origin_pt and origin_pt.get("lat") is not None:
            km = haversine_km(float(origin_pt["lat"]), float(origin_pt["lng"]),
                              dest["lat"], dest["lng"])
            actions.append({"type": "route",
                            "from": {"lat": float(origin_pt["lat"]), "lng": float(origin_pt["lng"])},
                            "to": {"lat": dest["lat"], "lng": dest["lng"]}})
            dist_txt = (f" (~{km:.1f} km đường chim bay)" if vi else f" (~{km:.1f} km as the crow flies)")
        # A shared GPS location is the honest "from" even when the query names no origin.
        frm_txt = origin or (("vị trí của bạn" if vi else "your location") if user_here else "")
        frm = (f" từ {frm_txt}" if frm_txt and vi else f" from {frm_txt}" if frm_txt else "")
        reply = (f"Chỉ đường{frm} tới {dest['name']}{dist_txt} — đã ghim và vẽ tuyến trên bản đồ."
                 if vi else
                 f"Directions{frm} to {dest['name']}{dist_txt} — pinned and drawn on the map.")
        return {"reply": reply, "map_actions": actions, "source": "fast"}

    # Coordinate / anchored-nearby: results are already distance-ranked; pin them
    # and focus the anchor so the user sees what "near" was measured from.
    if intent in ("Coordinate Search", "Nearby Search") and anchor and results:
        items = _pin_items(results, with_distance=True)
        actions = [{"type": "pins", "items": items, "fit": True}]
        if anchor.get("lat") is not None:
            actions.append({"type": "focus", "lat": anchor["lat"], "lng": anchor["lng"], "zoom": 14})
        near_what = anchor.get("label") or ("vị trí đã chọn" if vi else "the chosen spot")
        far = anchor.get("resolution") == "nearest_available"
        head = (f"Không có địa điểm ngay gần {near_what}; gần nhất trong bán kính ~{anchor.get('radius_km')} km:\n"
                if far and vi else
                f"None right next to {near_what}; nearest within ~{anchor.get('radius_km')} km:\n" if far else
                f"Có {len(items)} địa điểm gần {near_what}:\n" if vi else
                f"Found {len(items)} places near {near_what}:\n")
        reply = head + _grouped_reply_lines(items, vi, want_hours)
        return {"reply": reply, "map_actions": actions, "source": "fast"}

    # Nearby with no resolvable anchor and NO named city ("cafe gần đây" / "gần tôi",
    # or "khách sạn gần biển" with no city): measure from the user's GPS location
    # when shared, else the live viewport. A named-city nearby never reaches here —
    # it is handled by the city-scoped branch below, never from the viewport.
    if origin_nearby and origin_pt and origin_pt.get("lat") is not None:
        terms, max_ngram = load_abbreviations()
        norm = normalize_query(message, terms, max_ngram)
        categories = load_json("pois.json")["categories"]
        cat_key, _ = _detect_category(norm, _category_index(categories))
        near = cmd_near(SimpleNamespace(
            lat=float(origin_pt["lat"]), lng=float(origin_pt["lng"]),
            radius_km=_category_radius(cat_key, 3.0), category=cat_key, limit=12))
        near_rows = near["results"]
        # Apply the router's opening-hours constraint (cmd_near ignores it).
        time_c = (res.get("entities") or {}).get("time")
        time_note = ""
        if time_c and near_rows:
            open_rows = [r for r in near_rows if _time_ok(r, time_c, 12 * 60)]
            if open_rows:
                near_rows = open_rows
            else:
                # Nothing nearby matches the requested hours. Rather than a bare
                # not-found, disclose honestly and still offer the nearest
                # same-category places (their real hours are shown, want_hours=True).
                time_note = (
                    "Không có nơi mở đúng khung giờ bạn hỏi ở gần đây; gần nhất cùng loại:\n"
                    if vi else "No place open at that time nearby; nearest of the same type:\n")
        items = _pin_items(near_rows[:7], with_distance=True)
        whereat = ("vị trí của bạn" if user_here else "khu vực bản đồ") if vi else \
                  ("your location" if user_here else "the map view")
        if not items:
            reply = (f"Không tìm thấy địa điểm phù hợp trong ~3 km quanh {whereat}."
                     if vi else f"No matching places within ~3 km of {whereat}.")
            return {"reply": reply, "map_actions": [], "source": "fast"}
        near_head = ("Có %d địa điểm gần %s:\n" % (len(items), whereat) if vi
                     else "Found %d places near %s:\n" % (len(items), whereat))
        reply = time_note or near_head
        reply += _grouped_reply_lines(items, vi, want_hours)
        return {"reply": reply,
                "map_actions": [{"type": "pins", "items": items, "fit": True}],
                "source": "fast"}

    # Nearby whose landmark anchor didn't geocode but a CITY was named
    # ("khách sạn gần biển đà nẵng"): answer from the city-filtered results the
    # router already produced — NEVER the (possibly stale) map viewport. This is
    # what prevents the cross-city leak: a follow-up naming a new city stays in
    # that city instead of falling back to wherever the map happens to be panned.
    # Guarded by `named_scope`, so results are genuinely city-scoped and the city
    # label below is truthful (a no-city nearby is answered from the viewport above).
    if intent == "Nearby Search" and not anchor and named_scope and results:
        items = _pin_items(results, with_distance=False)
        city = (results[0].get("city") or "")
        where = (f" ở {city}" if vi else f" in {city}") if city else ""
        head = (f"Có {len(items)} địa điểm{where}:\n" if vi
                else f"Found {len(items)} places{where}:\n")
        reply = head + _grouped_reply_lines(items, vi, want_hours) + _needs_caveat(res, vi)
        return {"reply": reply,
                "map_actions": [{"type": "pins", "items": items, "fit": True}],
                "source": "fast"}

    # Plain search: short message, no reasoning language, and a confident hit.
    if not _COMPLEX_RE.search(folded) and len(folded.split()) <= 6:
        if results and results[0].get("score", 0) >= 55:
            # When a real origin (viewport) exists, attach honest distances — but
            # only when the viewport is actually LOCAL to the result (<50 km). A
            # viewport in another city is not a meaningful origin for a city-scoped
            # search (e.g. an HCMC map view vs a "... Hà Nội" query), so we never
            # show a cross-city distance, and never fabricate one with no origin.
            has_origin = bool(origin_pt and origin_pt.get("lat") is not None)
            shown = False
            if has_origin:
                for r in results:
                    d = round(haversine_km(float(origin_pt["lat"]), float(origin_pt["lng"]),
                                           r["lat"], r["lng"]), 2)
                    if d <= 50.0:
                        r["distance_km"] = d
                        shown = True
            brand_label = res.get("inherited_brand")
            if brand_label:
                # Inherited-brand follow-up (e.g. "sg" after "bv bach mai"): keep the
                # same-category fills but list the real brand matches first and label
                # the extras, and build an honest header from the brand + city instead
                # of echoing the raw follow-up text.
                exact = [r for r in results if r.get("is_brand_match")]
                extra = [r for r in results if not r.get("is_brand_match")]
                ordered = exact + extra
                items = _pin_items(ordered, with_distance=shown)
                # Pretty display city lives on the result rows (e.g. "TP Hồ Chí Minh");
                # res["city"] is the lowercase canonical ("ho chi minh").
                city = (ordered[0].get("city") if ordered else "") or ""
                where = ((f" ở {city}" if vi else f" in {city}") if city else "")
                if exact:
                    head = (
                        f"Tìm thấy {len(items)} địa điểm cho \"{brand_label}\"{where} — đã ghim lên bản đồ:\n"
                        if vi else
                        f"Found {len(items)} places for \"{brand_label}\"{where} — pinned on the map:\n")
                else:
                    head = (
                        f"Không có \"{brand_label}\"{where} trong dữ liệu — đây là các lựa chọn chất lượng gần nhất:\n"
                        if vi else
                        f"No \"{brand_label}\"{where} in the data — here are the nearest top-rated options:\n")
                reply = head + _fast_reply_lines_split(items, len(exact), vi, want_hours)
            else:
                items = _pin_items(results, with_distance=shown)
                head = _scope_prefix(res, vi) or (
                    f"Tìm thấy {len(items)} địa điểm cho \"{message}\" — đã ghim lên bản đồ:\n"
                    if vi else
                    f"Found {len(items)} places for \"{message}\" — pinned on the map:\n")
                reply = head + _grouped_reply_lines(items, vi, want_hours)
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


def _next_ctx(prior: dict, res: dict) -> dict:
    """Carry the last turn's resolved slots forward for the soft-cache. A slot is
    updated only when this turn resolved it, so a coordinate/POI turn never wipes
    an established city or category."""
    ctx = dict(prior) if isinstance(prior, dict) else {}
    ctx.pop("v", None)  # re-stamped by save_context
    ent = res.get("entities") or {}
    if res.get("city"):
        ctx["city_canonical"] = res["city"]
        if ent.get("city"):
            ctx["city_name"] = ent["city"]
    cat = res.get("category") or ent.get("category")
    if cat:
        ctx["category"] = cat
    if res.get("intent"):
        ctx["intent"] = res["intent"]
    if ent.get("brand"):
        ctx["brands"] = ent["brand"]
    ctx["ts"] = int(time.time())
    return ctx


def _candidates_block(message: str, viewport: dict | None, pins: list[dict],
                      prior: dict | None = None,
                      user_location: dict | None = None) -> str:
    res = cmd_search(SimpleNamespace(query=message, limit=10, city=None,
                                     category=None, prior=prior))
    intent = res.get("intent")
    lines = []
    if intent:
        # The router's read of the query — helps the model frame its reply
        # (navigation vs nearby vs a bare ambiguous brand).
        anchor = res.get("anchor") or {}
        anchor_note = f" near {anchor.get('label')}" if anchor.get("label") else ""
        lines.append(f"INTENT: {intent}{anchor_note}")
    lines.append(
        "CANDIDATES (poi_id | name | category | district | city | rating | hours | why):")
    for r in res.get("results") or []:
        # 'why' carries the matched amenities so the model can cite a concrete,
        # non-fabricated reason ("quiet, work-friendly"); blank when none matched.
        why = ", ".join((r.get("reasons") or [])[:4])
        lines.append(f"  {r['poi_id']} | {r['name']} | {r['category']} | "
                     f"{r['district']} | {r['city']} | {r['rating']} | "
                     f"{r.get('opening_hours') or '?'} | {why}")
    if not (res.get("results") or []):
        lines.append("  (no matches — say you could not find it in the dataset)")
    if viewport and viewport.get("lat") is not None:
        lines.append(f"VIEWPORT: {viewport['lat']:.4f},{viewport['lng']:.4f} z{viewport.get('zoom', '')}")
    if user_location and user_location.get("lat") is not None:
        # The user's real position — the honest origin for "near me" / distances.
        lines.append(f"USER_LOCATION: {user_location['lat']:.4f},{user_location['lng']:.4f}")
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
    # Multi-turn soft-cache is interactive-only: the benchmark/eval never set this
    # flag, so they make zero Redis calls and carry no cross-turn state.
    interactive = bool(req_payload.get("interactive"))

    # Chat reset / "new conversation": wipe the soft-cache for this session.
    if req_payload.get("reset"):
        if chat_session_id:
            clear_context(chat_session_id)
        return _emit({"reply": "", "session_id": None, "error": None,
                      "map_actions": [], "source": "fast"})

    message = (req_payload.get("message") or "").strip()
    if not message:
        print("ERROR: message is required", file=sys.stderr)
        return 1
    viewport = req_payload.get("viewport") or None
    user_location = req_payload.get("user_location") or None
    pins = req_payload.get("pins") or []
    folded = fold(message)

    # A stable id so a fast-path-only conversation still has a cache key (the
    # dashboard sends null on turn 1 and adopts whatever id we echo back).
    if interactive and not chat_session_id:
        chat_session_id = uuid.uuid4().hex
    ctx = load_context(chat_session_id) if interactive else {}

    # One router call, reused for the fast path and for saving the next context.
    # limit=7 so the fast path can show a top-3 block plus real "more suggestions"
    # extras below the divider. (The eval/bench call cmd_search directly with their
    # own limit, so this does not affect any gate.)
    # A dataset/engine failure must degrade to the agent path, never kill the turn.
    try:
        res = cmd_search(SimpleNamespace(query=message, limit=7, city=None,
                                         category=None, prior=ctx or None))
    except Exception as exc:
        print(f"WARN: search failed: {exc}", file=sys.stderr)
        res = {}

    # Deterministic fast path — the LLM is never called for simple intents.
    fast = None
    try:
        fast = _try_fast_path(res, message, folded, viewport, interactive,
                              user_location=user_location)
    except Exception as exc:  # dataset problems must not kill chat entirely
        print(f"WARN: fast path failed: {exc}", file=sys.stderr)
    if fast is not None:
        if interactive:
            save_context(chat_session_id, _next_ctx(ctx, res))
        # Honest disclosure when hard needs couldn't be confirmed (graceful fallback).
        reply = fast["reply"] + _needs_caveat(res, _is_vietnamese(message))
        return _emit({"reply": reply, "session_id": chat_session_id,
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
            data_block = _candidates_block(message, viewport, pins, prior=ctx or None,
                                           user_location=user_location)
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
    if interactive:
        # Keep the map soft-cache id stable across turns (don't adopt a different
        # backend id); persist the slots this turn resolved.
        save_context(chat_session_id, _next_ctx(ctx, res))
        session_id = chat_session_id
    else:
        session_id = data.get("session_id") or chat_session_id
    return _emit({
        "reply": reply,
        "session_id": session_id,
        "error": data.get("error"),
        "map_actions": actions,
        "source": "agent",
    })


if __name__ == "__main__":
    raise SystemExit(main())
