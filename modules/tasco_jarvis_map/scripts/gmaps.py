"""Google Maps services bridge (server-side key).

An OPTIONAL enhancement layer over the local dataset. It is never a hard
dependency and never sits on the deterministic search / eval path (the offline
gates must run with no network). The API key is read from the repo ``.env`` as
``GG_MAP_API_KEY`` and stays server-side here; it is never printed or returned.
Every call is gated on the key being present and the endpoint reachable, and any
failure returns a structured error carrying Google's own ``status`` string
(``REQUEST_DENIED`` / ``ZERO_RESULTS`` / ``OVER_QUERY_LIMIT`` / ...) so the caller
can fall back to the local gazetteer / straight-line answer cleanly.

Subcommands (argv in, one JSON object on stdout):
  status                              key presence + a live reachability probe
  geocode    --query "<address>"      address/place text -> lat/lng + formatted
  reverse    --lat L --lng G          coordinate -> nearest formatted address
  directions --from "la,lo" --to "la,lo" [--mode driving|walking|bicycling|transit]
  places     --query "<text>" [--lat L --lng G] [--radius M]

Run with PYTHONUTF8=1. Requires only the standard library (urllib).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _db  # noqa: E402

_KEY_NAME = "GG_MAP_API_KEY"
_BASE = "https://maps.googleapis.com/maps/api"
_TIMEOUT = 8.0
# VN bias so ambiguous names resolve to the intended country/language.
_REGION = "vn"
_LANG = "vi"


def _key() -> str | None:
    return _db.env_get(_KEY_NAME)


def _err(status: str, message: str, **extra) -> dict:
    """Structured failure — carries Google's status string, never the key."""
    out = {"ok": False, "status": status, "error": message}
    out.update(extra)
    return out


def _call(path: str, params: dict) -> dict:
    """GET {_BASE}/{path}?... — returns Google's parsed JSON or raises RuntimeError
    with a message that NEVER contains the key."""
    key = _key()
    if not key:
        raise RuntimeError(f"NO_KEY:{_KEY_NAME} is not set in .env")
    q = dict(params)
    q["key"] = key
    url = f"{_BASE}/{path}?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "tasco-jarvis-map"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP_{exc.code}:Google endpoint returned {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"UNREACHABLE:{type(exc).__name__}") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise RuntimeError("BAD_JSON:non-JSON response from Google") from exc


# ── encoded-polyline decoder (Google's algorithm) ──────────────────────────
def _decode_polyline(enc: str) -> list[list[float]]:
    """Decode a Google encoded polyline into [[lat, lng], ...]."""
    pts: list[list[float]] = []
    lat = lng = index = 0
    n = len(enc)
    while index < n:
        for is_lng in (False, True):
            shift = result = 0
            while True:
                b = ord(enc[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lng:
                lng += delta
            else:
                lat += delta
        pts.append([lat / 1e5, lng / 1e5])
    return pts


def _parse_latlng(text: str) -> tuple[float, float]:
    a, _, b = (text or "").partition(",")
    return float(a.strip()), float(b.strip())


# ── commands ────────────────────────────────────────────────────────────────
def cmd_config(_args) -> dict:
    """Runtime key delivery for the browser JS SDK. The dashboard fetches this via
    the bridge and injects the Maps JS loader, so the key lives in .env (never
    committed to the served HTML). NOTE: a browser key is necessarily visible in
    the page at runtime — that is expected for the JS SDK and is why the key must
    be HTTP-referrer restricted to your origins. Returns key_present=false (no key)
    so the frontend can degrade to the plain OSM map."""
    key = _key()
    return {"ok": bool(key), "key_present": bool(key),
            "key": key or "", "libraries": "places,geometry",
            "region": _REGION, "language": _LANG}


def cmd_status(_args) -> dict:
    """Key presence + a cheap live probe (geocode a fixed VN city). Confirms the
    key is valid AND Geocoding is enabled with billing on before anything is built
    on it."""
    if not _key():
        return _err("NO_KEY", f"{_KEY_NAME} is not set in .env", key_present=False)
    try:
        data = _call("geocode/json", {"address": "Ha Noi", "region": _REGION})
    except RuntimeError as exc:
        code, _, msg = str(exc).partition(":")
        return _err(code, msg or code, key_present=True, reachable=False)
    status = data.get("status", "UNKNOWN")
    ok = status == "OK"
    return {"ok": ok, "status": status, "key_present": True, "reachable": True,
            "error_message": data.get("error_message"),
            "note": "live geocode probe" if ok else "probe returned non-OK status"}


def cmd_geocode(args) -> dict:
    if not (args.query or "").strip():
        return _err("BAD_ARG", "geocode requires --query")
    params = {"address": args.query, "region": _REGION, "language": _LANG}
    try:
        data = _call("geocode/json", params)
    except RuntimeError as exc:
        code, _, msg = str(exc).partition(":")
        return _err(code, msg or code)
    status = data.get("status", "UNKNOWN")
    results = data.get("results") or []
    if status != "OK" or not results:
        return _err(status, data.get("error_message") or "no geocode result",
                    query=args.query)
    top = results[0]
    loc = top["geometry"]["location"]
    return {"ok": True, "status": "OK", "source": "google_geocode",
            "query": args.query, "lat": loc["lat"], "lng": loc["lng"],
            "formatted_address": top.get("formatted_address"),
            "place_id": top.get("place_id"),
            "types": top.get("types") or []}


def cmd_reverse(args) -> dict:
    params = {"latlng": f"{args.lat},{args.lng}", "language": _LANG}
    try:
        data = _call("geocode/json", params)
    except RuntimeError as exc:
        code, _, msg = str(exc).partition(":")
        return _err(code, msg or code)
    status = data.get("status", "UNKNOWN")
    results = data.get("results") or []
    if status != "OK" or not results:
        return _err(status, data.get("error_message") or "no reverse-geocode result")
    return {"ok": True, "status": "OK", "source": "google_reverse",
            "lat": args.lat, "lng": args.lng,
            "formatted_address": results[0].get("formatted_address"),
            "place_id": results[0].get("place_id")}


def cmd_directions(args) -> dict:
    try:
        o_lat, o_lng = _parse_latlng(args.__dict__["from"])
        d_lat, d_lng = _parse_latlng(args.to)
    except (ValueError, AttributeError):
        return _err("BAD_ARG", "directions needs --from 'lat,lng' --to 'lat,lng'")
    params = {"origin": f"{o_lat},{o_lng}", "destination": f"{d_lat},{d_lng}",
              "mode": args.mode, "language": _LANG, "region": _REGION}
    try:
        data = _call("directions/json", params)
    except RuntimeError as exc:
        code, _, msg = str(exc).partition(":")
        return _err(code, msg or code)
    status = data.get("status", "UNKNOWN")
    routes = data.get("routes") or []
    if status != "OK" or not routes:
        return _err(status, data.get("error_message") or "no route found",
                    frm={"lat": o_lat, "lng": o_lng}, to={"lat": d_lat, "lng": d_lng})
    route = routes[0]
    leg = (route.get("legs") or [{}])[0]
    path = _decode_polyline((route.get("overview_polyline") or {}).get("points", ""))
    return {"ok": True, "status": "OK", "source": "google_directions",
            "mode": args.mode,
            "distance_text": (leg.get("distance") or {}).get("text"),
            "distance_m": (leg.get("distance") or {}).get("value"),
            "duration_text": (leg.get("duration") or {}).get("text"),
            "duration_s": (leg.get("duration") or {}).get("value"),
            "from": {"lat": o_lat, "lng": o_lng},
            "to": {"lat": d_lat, "lng": d_lng},
            "polyline": path}


def cmd_places(args) -> dict:
    if not (args.query or "").strip():
        return _err("BAD_ARG", "places requires --query")
    params = {"query": args.query, "region": _REGION, "language": _LANG}
    if args.lat is not None and args.lng is not None:
        params["location"] = f"{args.lat},{args.lng}"
        params["radius"] = int(args.radius or 5000)
    try:
        data = _call("place/textsearch/json", params)
    except RuntimeError as exc:
        code, _, msg = str(exc).partition(":")
        return _err(code, msg or code)
    status = data.get("status", "UNKNOWN")
    if status not in ("OK", "ZERO_RESULTS"):
        return _err(status, data.get("error_message") or "places query failed",
                    query=args.query)
    items = []
    for r in (data.get("results") or [])[: (args.limit or 8)]:
        loc = (r.get("geometry") or {}).get("location") or {}
        items.append({
            "name": r.get("name"),
            "address": r.get("formatted_address"),
            "lat": loc.get("lat"), "lng": loc.get("lng"),
            "rating": r.get("rating"),
            "user_ratings_total": r.get("user_ratings_total"),
            "place_id": r.get("place_id"),
            "external": True, "source": "google_places",
        })
    return {"ok": True, "status": status, "source": "google_places",
            "query": args.query, "count": len(items), "results": items}


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Maps services bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config")
    sub.add_parser("status")

    g = sub.add_parser("geocode")
    g.add_argument("--query", required=True)

    rv = sub.add_parser("reverse")
    rv.add_argument("--lat", type=float, required=True)
    rv.add_argument("--lng", type=float, required=True)

    d = sub.add_parser("directions")
    d.add_argument("--from", dest="from", required=True)
    d.add_argument("--to", required=True)
    d.add_argument("--mode", default="driving",
                   choices=["driving", "walking", "bicycling", "transit"])

    p = sub.add_parser("places")
    p.add_argument("--query", required=True)
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lng", type=float, default=None)
    p.add_argument("--radius", type=int, default=5000)
    p.add_argument("--limit", type=int, default=8)

    args = ap.parse_args()
    handler = {"config": cmd_config, "status": cmd_status, "geocode": cmd_geocode,
               "reverse": cmd_reverse, "directions": cmd_directions,
               "places": cmd_places}[args.cmd]
    out = handler(args)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
