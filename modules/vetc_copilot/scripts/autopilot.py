#!/usr/bin/env python
"""VETC Auto-Pilot CLI: radar / ask / recommend / renew / wallet / eval / serve / audit."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datastore import load_dataset  # type: ignore[import-not-found]
from radar import radar_for_user  # type: ignore[import-not-found]
from brain import ask as brain_ask, recommend as brain_recommend  # type: ignore[import-not-found]
from hands import renew as hands_renew  # type: ignore[import-not-found]
from guardrails import privacy_refusal  # type: ignore[import-not-found]
from config import load_brain_config  # type: ignore[import-not-found]
from client import BrainClient  # type: ignore[import-not-found]
import audit  # type: ignore[import-not-found]


def _today(s: str | None) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else date.today()


def _brain_client() -> BrainClient:
    return BrainClient(load_brain_config())


def api_dispatch(endpoint: str, params: dict, ds, today: date, client=None) -> dict:
    """Route one API/CLI call to the right feature. Enforces cross-user privacy.

    ``params`` may include ``as_user`` (the acting user); a mismatch with the
    requested ``user`` triggers a privacy refusal.
    """
    user = params.get("user", "")
    as_user = params.get("as_user", user)
    refusal = privacy_refusal(as_user, user) if user else None
    if refusal:
        return {"error": refusal}
    if endpoint == "radar":
        return radar_for_user(ds, user, today)
    if endpoint == "ask":
        return brain_ask(ds, user, params.get("q", ""), today, client=client)
    if endpoint == "recommend":
        return {"user_id": user, "recommendations": brain_recommend(ds, user, today)}
    if endpoint == "renew":
        return hands_renew(
            ds,
            user,
            params.get("vehicle", ""),
            params.get("service", ""),
            today,
            consent=str(params.get("consent", "true")).lower() != "false",
        )
    if endpoint == "wallet":
        return {
            "vehicle_id": params.get("vehicle"),
            "documents": ds.documents_for_vehicle(params.get("vehicle", "")),
        }
    return {"error": f"unknown endpoint: {endpoint}"}


def run_eval(ds, today: date, client=None) -> list[dict]:
    """Run every eval scenario end-to-end, routing by category/task type."""
    results: list[dict] = []
    for sc in ds.eval_scenarios:
        cat = sc.get("category", "")
        uid, vid = sc.get("user_id", ""), sc.get("vehicle_id", "")
        if "Renewal" in cat and "Reminder" not in cat:
            res = api_dispatch(
                "renew", {"user": uid, "vehicle": vid, "service": "SVC001"}, ds, today
            )
        elif cat in {"Roadside Recommendation", "EV Owner", "Service Discovery", "Missing Upload"}:
            res = api_dispatch("recommend", {"user": uid}, ds, today, client)
        elif cat in {"Inspection Reminder", "Urgent Deadlines", "Multi Vehicle", "Motorbike Case"}:
            res = api_dispatch("radar", {"user": uid}, ds, today)
        else:
            res = api_dispatch(
                "ask", {"user": uid, "q": sc.get("user_query", "")}, ds, today, client
            )
        results.append({"category": cat, "user_id": uid, "result": res})
    return results


def _cmd_serve(ds, today: date, port: int) -> int:
    """Serve dashboard.html + /api/* backed by api_dispatch (stdlib http)."""
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    module_dir = Path(__file__).resolve().parent.parent
    client = _brain_client()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", "/index.html", "/dashboard.html"):
                self._send(
                    200, (module_dir / "dashboard.html").read_bytes(), "text/html; charset=utf-8"
                )
                return
            if parsed.path.startswith("/api/"):
                params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                out = api_dispatch(parsed.path[len("/api/") :], params, ds, today, client)
                self._send(
                    200,
                    json.dumps(out, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            self._send(404, b"not found", "text/plain")

        def log_message(self, *a) -> None:  # silence stdout noise
            return

    print(json.dumps({"serving": f"http://localhost:{port}", "dashboard": "/"}))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    ``--data``/``--today`` are global options. argparse subparsers don't
    inherit a parent's optionals when they appear *after* the subcommand
    token, so each subparser also declares them (shared via ``_global``)
    letting callers pass ``--today``/``--data`` either before or after the
    command name.
    """
    _global = argparse.ArgumentParser(add_help=False)
    _global.add_argument("--data", default=None, help="Data dir (default: module data/).")
    _global.add_argument(
        "--today", default=None, help="Reference date YYYY-MM-DD (default: today)."
    )

    p = argparse.ArgumentParser(
        prog="autopilot", description="VETC Auto-Pilot CLI", parents=[_global]
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("radar", "recommend"):
        s = sub.add_parser(name, parents=[_global])
        s.add_argument("--user", required=True)
    a = sub.add_parser("ask", parents=[_global])
    a.add_argument("text")
    a.add_argument("--user", required=True)
    r = sub.add_parser("renew", parents=[_global])
    r.add_argument("--user", required=True)
    r.add_argument("--vehicle", required=True)
    r.add_argument("--service", default="SVC001")
    r.add_argument("--no-consent", action="store_true")
    w = sub.add_parser("wallet", parents=[_global])
    w.add_argument("--vehicle", required=True)
    sub.add_parser("eval", parents=[_global])
    e = sub.add_parser("serve", parents=[_global])
    e.add_argument("--port", type=int, default=8770)
    au = sub.add_parser("audit", parents=[_global])
    au.add_argument("--limit", type=int, default=50)
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints JSON; returns 0 on success."""
    args = build_parser().parse_args(argv)
    ds = load_dataset(args.data)
    today = _today(args.today)
    client = _brain_client()

    if args.command == "radar":
        print(
            json.dumps(
                api_dispatch("radar", {"user": args.user}, ds, today), ensure_ascii=False, indent=2
            )
        )
    elif args.command == "ask":
        print(
            json.dumps(
                api_dispatch("ask", {"user": args.user, "q": args.text}, ds, today, client),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "recommend":
        print(
            json.dumps(
                api_dispatch("recommend", {"user": args.user}, ds, today),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "renew":
        params = {
            "user": args.user,
            "vehicle": args.vehicle,
            "service": args.service,
            "consent": "false" if args.no_consent else "true",
        }
        print(json.dumps(api_dispatch("renew", params, ds, today), ensure_ascii=False, indent=2))
    elif args.command == "wallet":
        print(
            json.dumps(
                api_dispatch("wallet", {"vehicle": args.vehicle}, ds, today),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "eval":
        print(json.dumps(run_eval(ds, today, client), ensure_ascii=False, indent=2))
    elif args.command == "audit":
        events = audit.read_events()
        print(json.dumps({"events": events[-args.limit :]}, ensure_ascii=False, indent=2))
    elif args.command == "serve":
        return _cmd_serve(ds, today, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
