"""``minder-module`` — scaffold and locally develop Minder service modules.

    minder-module new <name> [--summary "…"] [--port 9300]
        Scaffold a full service module (SDK connector backend + MF dashboard +
        manifest + compose snippet) under the active modules directory.

    minder-module dev <name>
        Run the module's connector backend (uvicorn --reload) and its dashboard
        frontend (vite dev) together, with the SDK on PYTHONPATH — an edit-save-
        refresh loop with no docker rebuild.

The backend serves the connector on the module's port; point Minder at it with the
manifest's ``connector_url`` (use ``http://localhost:<port>`` for host-run Minder).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path


def _modules_root() -> Path:
    from minder.core.modules.registry import resolve_modules_root

    return resolve_modules_root()


def _repo_root() -> Path:
    # minder/module_dev.py -> repo root is two parents up.
    return Path(__file__).resolve().parent.parent


def _port_from_manifest(module_dir: Path, default: int = 9300) -> int:
    mf = module_dir / "manifest.json"
    if not mf.is_file():
        return default
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    entry = (data.get("remote") or {}).get("remoteEntry") or ""
    conn = (data.get("service") or {}).get("connector_url") or ""
    for candidate in (entry, conn):
        m = re.search(r":(\d{2,5})(?:/|$)", candidate)
        if m:
            return int(m.group(1))
    return default


def cmd_new(args: argparse.Namespace) -> int:
    from minder.core.modules import store

    root = _modules_root()
    try:
        module = store.create_module(root, args.name, template="service",
                                     summary=args.summary or "")
    except store.ModuleExists:
        print(f"error: module {args.name!r} already exists at {root/args.name}",
              file=sys.stderr)
        return 1
    except store.InvalidModuleName as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Scaffolded service module at {module.dir}")
    print("Next:")
    print(f"  minder-module dev {args.name}        # run backend + dashboard locally")
    print(f"  see modules/{args.name}/docker-compose.snippet.yml to deploy")
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    root = _modules_root()
    module_dir = root / args.name
    backend = module_dir / "backend"
    frontend = module_dir / "frontend"
    if not (backend / "app.py").is_file():
        print(f"error: {backend/'app.py'} not found — is {args.name!r} a service module?",
              file=sys.stderr)
        return 1

    port = _port_from_manifest(module_dir)
    sdk_path = _repo_root() / "minder_module_sdk"

    env = os.environ.copy()
    # SDK on PYTHONPATH so ``import minder_module_sdk`` works without installing;
    # dashboard dist env unset in dev (frontend is served by vite, not the backend).
    env["PYTHONPATH"] = os.pathsep.join(
        [str(sdk_path), str(backend), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env.setdefault("MODULE_PUBLIC_BASE", f"http://localhost:{port}")

    procs: list[subprocess.Popen] = []
    print(f"[minder-module] backend  → uvicorn app:app --reload --port {port}")
    procs.append(subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--reload",
         "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(backend), env=env,
    ))

    if (frontend / "package.json").is_file() and not args.no_frontend:
        print(f"[minder-module] frontend → npm run dev  (in {frontend})")
        try:
            procs.append(subprocess.Popen(["npm", "run", "dev"], cwd=str(frontend), env=env))
        except FileNotFoundError:
            print("[minder-module] npm not found; skipping frontend dev server.",
                  file=sys.stderr)

    print(f"[minder-module] connector at http://localhost:{port}/connector/health  (Ctrl-C to stop)")

    def _stop(*_a: object) -> None:
        for p in procs:
            with __import__("contextlib").suppress(ProcessLookupError):
                p.terminate()

    signal.signal(signal.SIGINT, lambda *_: _stop())
    signal.signal(signal.SIGTERM, lambda *_: _stop())
    try:
        # Exit when any child exits (a crash shouldn't leave a half-running loop).
        while True:
            for p in procs:
                code = p.poll()
                if code is not None:
                    print(f"[minder-module] a process exited (code {code}); shutting down.")
                    _stop()
                    for q in procs:
                        with __import__("contextlib").suppress(Exception):
                            q.wait(timeout=5)
                    return code or 0
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        _stop()
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="minder-module",
        description="Scaffold and locally develop Minder service modules.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="scaffold a new service module")
    p_new.add_argument("name")
    p_new.add_argument("--summary", default="", help="one-line description")
    p_new.add_argument("--port", type=int, default=9300, help="connector port (default 9300)")
    p_new.set_defaults(func=cmd_new)

    p_dev = sub.add_parser("dev", help="run a module's backend + dashboard locally")
    p_dev.add_argument("name")
    p_dev.add_argument("--no-frontend", action="store_true", help="backend only")
    p_dev.set_defaults(func=cmd_dev)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
