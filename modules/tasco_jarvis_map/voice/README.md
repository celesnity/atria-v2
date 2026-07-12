# Local voice for tasco_jarvis_map (LiveKit console worker, all-GPT)

The dashboard mic button runs a **local** voice session: a `livekit-agents`
**console** worker captures the machine's own mic/speakers, does **OpenAI STT →
the map's own Jarvis brain → OpenAI TTS**, and drives the map with the same pins
/routes a typed query would. No LiveKit server, no browser mic (the module iframe
is sandboxed and can't open one — that's why the worker uses the OS mic directly).

```
mic button ─▶ scripts/voice_session.py start ─▶ (detached) voice/agent.py console
                                                     │  OS mic ─▶ OpenAI STT
                                                     │  ─▶ jarvis_chat.py (map brain)
                                                     │  ─▶ OpenAI TTS ─▶ OS speakers
                                                     ▼  publishes each turn
                                              Redis  map:voice:{sid}
mic overlay ◀── voice_session.py status (poll ~1s) ◀──────┘   (transcript/reply/pins)
```

## One-time setup (Python 3.11 env)

The worker needs its own Python **3.11** env (livekit-agents pulls a heavy stack;
keep it out of the map module's `../../.venv`). Two options:

**A. Module-local venv (recommended for shipping):**
```powershell
py -3.11 -m venv voice\.venv          # or: <python3.11> -m venv voice\.venv
voice\.venv\Scripts\python -m pip install -r voice\requirements.txt
```
The bridge auto-detects `voice/.venv/Scripts/python.exe` — nothing else to set.

**B. Reuse an existing 3.11 env** (e.g. the MinderAI `minderai-voice` conda env,
which already has livekit-agents 1.5): point the bridge at it instead of creating
a venv, by setting in the Atria host `.env`:
```
MAP_VOICE_PYTHON=C:\Users\<you>\anaconda3\envs\minderai-voice\python.exe
```

First run downloads the silero VAD model. Prefetch it with:
```
voice\.venv\Scripts\python voice\agent.py download-files
```

## Config (env; secrets stay in the host .env, never printed)

- `OPENAI_API_KEY` — required (STT/TTS + agent brain). Inherited from the host env.
- `MAP_VOICE_PYTHON` — voice-env python (option B); else `voice/.venv` is used.
- `MAP_VOICE_STT_LANG` — STT language, default `vi` (Vietnamese-first). `en` etc.
- `MAP_VOICE_TTS_VOICE` — OpenAI TTS voice, default `ash`.
- `MAP_VOICE_TURN` — `vad` (default) or `multilingual` (room-only; see requirements).
- `ATRIA_REDIS_URL` — status channel (already set for the map module).
- `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — console mode validates
  these are non-empty but (unregistered) never dials them; `agent.py` self-injects
  dummy dev values, so you do NOT need a real LiveKit account for local console voice.

`agent.py` is **self-sufficient for a direct run**: on start it injects the dummy
`LIVEKIT_*`, backfills `OPENAI_API_KEY`/`ATRIA_REDIS_URL`/`ATRIA_MAP_BACKEND` from the
project `.env` if unset, and resolves the map's own `.venv` python for the brain — so
the commands below work in a bare shell (no manual `export`, no bridge needed).

## Run / smoke-test

The mic button drives everything; to test the worker directly:
```powershell
# headless: prove the all-GPT pipeline builds + models load (no mic)
voice\.venv\Scripts\python voice\agent.py --selftest

# real local session against your mic/speakers (speak a map query):
$env:MAP_VOICE_SESSION="smoke"; voice\.venv\Scripts\python voice\agent.py console
```

Runtime deps: voice reuses `jarvis_chat.py`, so the same stack as typed chat must
be up — the Atria server (agent-path fallback), Redis, and map-db.

## Files
- `agent.py` — the console worker (pipeline + brain bridge + status publish).
- `status.py` — Redis status channel (shared with `scripts/voice_session.py`).
- `../scripts/voice_session.py` — start/stop/status bridge (runs in the map env).
