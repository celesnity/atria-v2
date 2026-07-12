"""Bridge control for the local LiveKit voice worker (Phase 2, item 8).

Runs in the MAP env and is called from the dashboard via AtriaDash.json:
    AtriaDash.json('voice_session.py', ['start','--session', sid, '--viewport', vp])
    AtriaDash.json('voice_session.py', ['status','--session', sid])
    AtriaDash.json('voice_session.py', ['stop','--session', sid])

The voice loop itself is long-running (OS mic/speakers) and can't live inside the
request/response bridge, so `start` spawns voice/agent.py DETACHED (its own console
worker, own Python 3.11 env) and returns immediately; the worker publishes each
turn to Redis (voice/status.py) and the frontend polls `status`. `stop` kills it.

The worker's env (voice env) is resolved as:
  MAP_VOICE_PYTHON  ->  <module>/voice/.venv  ->  error (with setup hint)
No secrets are printed; OPENAI_API_KEY is inherited into the worker env, never
echoed. Console mode also needs non-empty LIVEKIT_* (dummy dev values — an
unregistered console session never dials them).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(os.environ.get("ATRIA_MODULE_ROOT")
                  or Path(__file__).resolve().parent.parent)
VOICE_DIR = MODULE_DIR / "voice"
RUN_DIR = MODULE_DIR / "_local" / "voice_run"

sys.path.insert(0, str(VOICE_DIR))  # share the status schema with the worker
import status as vstatus  # noqa: E402  (map env has redis)


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=True))


def _voice_python() -> str | None:
    """Resolve the voice env's python (3.11 + livekit-agents)."""
    p = os.environ.get("MAP_VOICE_PYTHON")
    if p and Path(p).exists():
        return p
    local = VOICE_DIR / ".venv" / "Scripts" / "python.exe"
    if local.exists():
        return str(local)
    return None


def _pidfile(sid: str) -> Path:
    return RUN_DIR / f"{_safe(sid)}.pid"


def _logfile(sid: str) -> Path:
    return RUN_DIR / f"{_safe(sid)}.log"


def _safe(sid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (sid or "s"))[:64]


def _alive(pid: int) -> bool:
    """Is a PID running? (Windows-safe, no psutil dependency.)"""
    if pid <= 0:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001 - assume dead on query failure
        return False


def _read_pid(sid: str) -> int:
    try:
        return int(_pidfile(sid).read_text().strip())
    except Exception:  # noqa: BLE001
        return 0


def _running_pid(sid: str) -> int:
    pid = _read_pid(sid)
    return pid if pid and _alive(pid) else 0


def cmd_start(sid: str, viewport: str | None) -> dict:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    existing = _running_pid(sid)
    if existing:  # idempotent: a worker is already up for this session
        blob = vstatus.read(sid)
        return {"ok": True, "session_id": sid, "pid": existing,
                "state": blob.get("state", "listening"), "already_running": True}

    vpy = _voice_python()
    if not vpy:
        return {"ok": False, "session_id": sid, "state": "error",
                "error": "voice env not found. Set MAP_VOICE_PYTHON or create "
                         "voice/.venv (see voice/README)."}

    env = dict(os.environ)
    # The worker is a DIFFERENT Python (voice env, 3.11) than this bridge (map env,
    # 3.12). PYTHONPATH/PYTHONHOME inherited from the map env make the 3.11 worker
    # import 3.12 stdlib -> "AssertionError: SRE module mismatch". Strip them so the
    # worker uses only its own interpreter's stdlib.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["MAP_VOICE_SESSION"] = sid
    env["MAP_PYTHON"] = sys.executable          # this (map) env runs jarvis_chat
    env["MAP_MODULE_DIR"] = str(MODULE_DIR)
    env.setdefault("PYTHONUTF8", "1")
    if viewport:
        env["MAP_VOICE_VIEWPORT"] = viewport
    # console mode requires non-empty LIVEKIT_* (unregistered -> never dialed)
    env.setdefault("LIVEKIT_URL", "ws://localhost:7880")
    env.setdefault("LIVEKIT_API_KEY", "devkey")
    env.setdefault("LIVEKIT_API_SECRET", "devsecret_local_console_only")

    vstatus.publish(sid, state="listening", bump=False, transcript=None,
                    reply=None, map_actions=None, error=None)

    creationflags = 0
    if os.name == "nt":
        creationflags = (subprocess.DETACHED_PROCESS
                         | subprocess.CREATE_NEW_PROCESS_GROUP)
    log = open(_logfile(sid), "ab", buffering=0)  # noqa: SIM115 - handed to child
    proc = subprocess.Popen(
        [vpy, str(VOICE_DIR / "agent.py"), "console"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        cwd=str(MODULE_DIR), env=env, creationflags=creationflags, close_fds=True)
    _pidfile(sid).write_text(str(proc.pid))
    return {"ok": True, "session_id": sid, "pid": proc.pid, "state": "listening"}


def cmd_stop(sid: str) -> dict:
    pid = _read_pid(sid)
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, 9)
        except Exception:  # noqa: BLE001
            pass
    try:
        _pidfile(sid).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    vstatus.publish(sid, state="stopped", bump=False, transcript=None,
                    reply=None, map_actions=None, error=None)
    return {"ok": True, "session_id": sid, "state": "stopped"}


def cmd_status(sid: str) -> dict:
    blob = vstatus.read(sid)
    running = bool(_running_pid(sid))
    if not blob:
        blob = {"state": "listening" if running else "stopped", "seq": 0}
    blob["running"] = running
    blob["session_id"] = sid
    return blob


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "stop", "status"):
        s = sub.add_parser(name)
        s.add_argument("--session", required=True)
        if name == "start":
            s.add_argument("--viewport", default=None)
    args = ap.parse_args()

    if args.cmd == "start":
        _emit(cmd_start(args.session, args.viewport))
    elif args.cmd == "stop":
        _emit(cmd_stop(args.session))
    else:
        _emit(cmd_status(args.session))


if __name__ == "__main__":
    main()
