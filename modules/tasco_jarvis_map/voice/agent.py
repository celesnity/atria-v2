"""Local LiveKit voice worker for tasco_jarvis_map (Phase 2, item 8).

Runs a livekit-agents **console** session against the machine's own mic/speakers
(NO LiveKit server) — the module dashboard iframe cannot open a mic
(sandbox="allow-scripts allow-forms"), so voice lives in a local worker that the
dashboard's mic button starts/stops via scripts/voice_session.py.

Pipeline is ALL-GPT per the module decision:
  STT  openai.STT   gpt-4o-mini-transcribe   (streaming)
  TTS  openai.TTS   gpt-4o-mini-tts          (voice "ash")
  VAD  silero.VAD                            (local, free)
  turn multilingual turn-detector            (local, free; good for Vietnamese)
The BRAIN is the map's own Jarvis: llm_node() shells out to scripts/jarvis_chat.py
(Step 1), so a spoken answer is identical to a typed one. For the Step-0 spike the
brain is a fixed string (VOICE_SPIKE=1) so we can prove the audio layer in isolation.

Runs in its OWN Python 3.11 env (the minderai-voice conda env, or a module-local
voice/.venv) — never the map module's .venv, to keep the deterministic test env clean.

  python voice/agent.py --selftest      # headless: build pipeline + load models, exit
  python voice/agent.py download-files  # prefetch silero/turn-detector models
  python voice/agent.py console         # real local mic/speaker session (manual)

OPENAI_API_KEY is read from the environment (loaded from the map project's .env by
the launcher) and is NEVER printed or logged.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterable

# Plugins MUST be imported on the MAIN thread: importing a livekit plugin package
# auto-registers it (and its inference runners) with the agents plugin registry,
# and that registration is main-thread-only. Console mode runs the job on a THREAD
# executor, so a lazy import inside the entrypoint raises "Plugins must be
# registered on the main thread". Import them here, at module load (main thread).
from livekit.plugins import openai as lk_openai  # noqa: E402
from livekit.plugins import silero as lk_silero  # noqa: E402

logger = logging.getLogger("map-voice")

# --- pipeline model choices (all-GPT) --------------------------------------
STT_MODEL = os.environ.get("MAP_VOICE_STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("MAP_VOICE_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("MAP_VOICE_TTS_VOICE", "ash")
# STT language: the map is Vietnamese-first, so bias to "vi" (embedded English
# brand names still transcribe). Override with MAP_VOICE_STT_LANG. NOTE: the plugin
# rejects None (LanguageCode(None) raises) — must be a non-empty code, default "vi".
STT_LANGUAGE = os.environ.get("MAP_VOICE_STT_LANG", "vi") or "vi"
# Turn detection: "vad" (silero endpointing — robust in console mode) or
# "multilingual" (semantic turn model). The multilingual model uses an ONNX
# InferenceRunner that must be registered on the MAIN thread, but console mode
# runs the job on a THREAD executor -> "InferenceRunner must be registered on the
# main thread". So default to VAD for the local console worker; multilingual is
# opt-in (works under the room/worker executor, not console).
TURN_MODE = os.environ.get("MAP_VOICE_TURN", "vad").strip().lower()


def _bootstrap_env() -> None:
    """Make a DIRECT `python voice/agent.py {console,--selftest}` run self-sufficient
    — identical to what scripts/voice_session.py injects for the bridge-launched
    worker, so the manual smoke-test path and the mic-button path share one env.

    1. Console mode validates LIVEKIT_URL/API_KEY/API_SECRET are non-empty but,
       being `unregistered`, never dials them (worker.py gates the conn task); set
       harmless dummy dev values so a bare run doesn't die with "ws_url is required".
    2. Backfill a few keys from the map project's .env if the launcher didn't export
       them (OPENAI_API_KEY for STT/TTS, Redis/backend for the status+brain path).
       Values are read into os.environ only — NEVER printed or logged.
    """
    from pathlib import Path as _Path

    os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
    os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
    os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret_local_console_only")

    missing = [k for k in ("OPENAI_API_KEY", "ATRIA_REDIS_URL", "ATRIA_MAP_BACKEND")
               if not os.environ.get(k)]
    if not missing:
        return
    env_file = _Path(os.environ.get("MAP_MODULE_DIR")
                     or _Path(__file__).resolve().parent.parent).parent.parent / ".env"
    try:
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in missing and not os.environ.get(key):
                os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass  # no .env is fine; selftest will report a still-missing key


def _build_audio():
    """Instantiate the headless-safe stages (STT/TTS/VAD). The multilingual turn
    detector is NOT here: it requires a live job context (get_job_context().
    inference_executor) and can only be built inside the entrypoint — so --selftest
    validates these three and the turn detector is exercised at real runtime (its
    model is prefetched via `download-files`)."""
    stt = lk_openai.STT(model=STT_MODEL, language=STT_LANGUAGE)
    tts = lk_openai.TTS(model=TTS_MODEL, voice=TTS_VOICE)
    vad = lk_silero.VAD.load()
    return stt, tts, vad


def _selftest() -> int:
    """Prove the all-GPT pipeline builds and the local models load, with no mic and
    no OpenAI network call (STT/TTS construct lazily). Exit 0 on success."""
    import time

    if not os.environ.get("OPENAI_API_KEY"):
        print("SELFTEST FAIL: OPENAI_API_KEY not in environment", file=sys.stderr)
        return 2
    try:
        t0 = time.monotonic()
        stt, tts, vad = _build_audio()
        dt = time.monotonic() - t0
    except Exception as e:  # noqa: BLE001 - selftest reports any build failure
        print(f"SELFTEST FAIL: pipeline build error: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 1
    print("SELFTEST OK: all-GPT audio pipeline built + silero loaded")
    print(f"  STT  {STT_MODEL}  (lang={STT_LANGUAGE})  -> {type(stt).__name__}")
    print(f"  TTS  {TTS_MODEL}  voice={TTS_VOICE}  -> {type(tts).__name__}")
    print(f"  VAD  silero -> {type(vad).__name__}")
    print("  turn multilingual -> validated at runtime (job-only); prefetch via "
          "`python voice/agent.py download-files`")
    print(f"  build+load {dt:.1f}s")
    return 0


# --- the real worker (console mode) ----------------------------------------
def _latest_user_text(chat_ctx) -> str:
    """Last user utterance from the chat context (mirrors MinderAI's helper)."""
    for item in reversed(getattr(chat_ctx, "items", []) or []):
        if getattr(item, "role", None) == "user":
            return (item.text_content or "").strip()
    return ""


# --- session identity + brain wiring (set by scripts/voice_session.py) ------
import json  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

_MODULE_DIR = Path(
    os.environ.get("MAP_MODULE_DIR")
    or Path(__file__).resolve().parent.parent  # voice/ -> module root
)
def _resolve_map_python() -> str:
    """The interpreter that runs jarvis_chat — it MUST be the map's own 3.12 .venv
    (psycopg/pgvector), never this worker's 3.11 voice env. The bridge sets
    MAP_PYTHON explicitly (its own sys.executable = map venv); for a direct run we
    fall back to the repo .venv, and only then to sys.executable as a last resort."""
    env_py = os.environ.get("MAP_PYTHON")
    if env_py:
        return env_py
    repo_venv = _MODULE_DIR.parent.parent / ".venv" / "Scripts" / "python.exe"
    if repo_venv.exists():
        return str(repo_venv)
    return sys.executable


_MAP_PYTHON = _resolve_map_python()  # map .venv python (3.12), NOT the voice env
_JARVIS = str(_MODULE_DIR / "scripts" / "jarvis_chat.py")
SESSION_ID = os.environ.get("MAP_VOICE_SESSION", "voice-console")


def _viewport() -> dict | None:
    raw = os.environ.get("MAP_VOICE_VIEWPORT")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _call_jarvis(user_text: str) -> dict:
    """Run the map's own chat brain (scripts/jarvis_chat.py) in the MAP env so a
    spoken answer is identical to a typed one. Returns {reply, map_actions,
    session_id}. Blocking -> callers wrap in asyncio.to_thread."""
    payload = {
        "message": user_text,
        "chat_session_id": SESSION_ID,
        "interactive": True,
    }
    vp = _viewport()
    if vp:
        payload["viewport"] = vp
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    # This worker is 3.11 but jarvis_chat runs under the map's 3.12 python; a
    # leaked PYTHONHOME/PYTHONPATH from the voice env makes the child load the wrong
    # stdlib -> "AssertionError: SRE module mismatch". Strip them (same guard the
    # bridge applies when it spawns this worker).
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        proc = subprocess.run(
            [_MAP_PYTHON, _JARVIS],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, cwd=str(_MODULE_DIR), env=env, timeout=115)
        out = proc.stdout.decode("utf-8", "replace").strip()
        return json.loads(out) if out else {"reply": "", "map_actions": []}
    except Exception as e:  # noqa: BLE001 - brain failure must not kill the voice loop
        logger.warning("jarvis_chat call failed: %s", e)
        return {"reply": "", "map_actions": [], "error": str(e)}


async def _brain_reply(user_text: str) -> AsyncIterable[str]:
    """Map Jarvis brain. Spike (VOICE_SPIKE=1) short-circuits to a fixed line so the
    audio layer can be proven without the map stack; otherwise call jarvis_chat and
    publish the turn (transcript/reply/map_actions) to the Redis status channel so
    the dashboard can render it and drive the map."""
    import asyncio

    if not user_text:
        return
    if os.environ.get("VOICE_SPIKE") == "1":
        yield "Xin chào, tôi là trợ lý bản đồ."
        return

    import status as vstatus
    vstatus.publish(SESSION_ID, state="thinking", transcript=user_text,
                    reply=None, map_actions=None, error=None)
    res = await asyncio.to_thread(_call_jarvis, user_text)
    reply = (res.get("reply") or "").strip()
    if not reply:
        reply = "Xin lỗi, tôi chưa tìm được kết quả."
    vstatus.publish(SESSION_ID, state="speaking", transcript=user_text,
                    reply=reply, map_actions=res.get("map_actions") or [],
                    error=res.get("error"))
    yield reply
    # ready for the next utterance
    vstatus.publish(SESSION_ID, state="listening", bump=False)


def _make_agent():
    from livekit.agents import Agent

    class MapVoiceAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions="")  # brain owns behavior, not the LLM

        async def llm_node(self, chat_ctx, tools, model_settings) -> AsyncIterable[str]:
            user_text = _latest_user_text(chat_ctx)
            async for tok in _brain_reply(user_text):
                yield tok

    return MapVoiceAgent()


def _build_server():
    from livekit.agents import AgentServer, AgentSession, JobContext
    from livekit.agents import TurnHandlingOptions

    server = AgentServer()

    @server.rtc_session()
    async def entrypoint(ctx: "JobContext"):
        stt, tts, vad = _build_audio()
        # Endpointing/interruption defaults are sensible in 1.5.x; the explicit
        # min/max_endpointing_delay + allow_interruptions kwargs are deprecated
        # (move to TurnHandlingOptions in v2.0), so rely on defaults here.
        kwargs = dict(stt=stt, tts=tts, vad=vad)
        if TURN_MODE == "multilingual":
            from livekit.plugins.turn_detector.multilingual import MultilingualModel
            kwargs["turn_handling"] = TurnHandlingOptions(
                turn_detection=MultilingualModel())
        session = AgentSession(**kwargs)
        await session.start(agent=_make_agent(), room=ctx.room)
        if os.environ.get("VOICE_SPIKE") != "1":
            import status as vstatus
            vstatus.publish(SESSION_ID, state="listening", bump=False)

    return server


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(level=logging.INFO)
    _bootstrap_env()  # dummy LIVEKIT_* + .env backfill -> direct runs are self-sufficient

    if "--selftest" in sys.argv[1:]:
        raise SystemExit(_selftest())

    from livekit import agents

    server = _build_server()
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
