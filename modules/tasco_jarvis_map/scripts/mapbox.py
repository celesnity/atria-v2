"""Mapbox config bridge (server-side token).

Delivers the Mapbox access token from the repo ``.env`` (``MAPBOX_API_KEY``) to the
sandboxed dashboard so it can render Mapbox raster tiles inside the existing Leaflet
map. The token is read server-side and only handed to the browser at runtime — it is
never committed to the served HTML. NOTE: a Mapbox *web* token is necessarily visible
in the page at runtime (that is how the tiles load); scope / URL-restrict it in your
Mapbox account. When no token is set, ``key_present`` is ``false`` so the frontend
degrades cleanly to the CARTO basemap. This never sits on the deterministic search /
eval path.

Subcommand (argv in, one JSON object on stdout):
  config   -> {ok, key_present, key, style, tile_size}

``MAPBOX_STYLE`` may override the default style (``mapbox/light-v11``); the browser
warms it toward the Marlow Bay cream palette with a CSS tile filter.

Run with PYTHONUTF8=1. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _db  # noqa: E402

_KEY_NAME = "MAPBOX_API_KEY"
_DEFAULT_STYLE = "mapbox/light-v11"


def cmd_config(_args) -> dict:
    """Runtime token delivery for the browser basemap. Returns key_present=false
    (no token) so the dashboard stays on the CARTO fallback."""
    key = _db.env_get(_KEY_NAME)
    style = (_db.env_get("MAPBOX_STYLE") or _DEFAULT_STYLE).strip()
    return {"ok": bool(key), "key_present": bool(key), "key": key or "",
            "style": style, "tile_size": 512}


def main() -> int:
    ap = argparse.ArgumentParser(description="Mapbox config bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    args = ap.parse_args()
    out = {"config": cmd_config}[args.cmd](args)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
