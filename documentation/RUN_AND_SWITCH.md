# Minder V2 — run & switch LLM provider (Windows / PowerShell)

Quick cheat-sheet for running Minder locally and flipping the chat LLM between
**Qwen (DashScope)** and **OpenAI (GPT)**.

---

## Go to the project (run this first in every terminal)

The project path contains `[` `]`, which PowerShell treats as wildcards — use
`-LiteralPath` (a plain `cd 'D:\[Project]_minderV2'` fails):

```powershell
Set-Location -LiteralPath 'D:\[Project]_minderV2'
```

The `.\scripts\windows\run-*.ps1` and `.\scripts\windows\switch-llm.ps1` scripts already `cd` to the project root
internally, so you can also just call them by full path from anywhere, e.g.
`& 'D:\[Project]_minderV2\scripts\windows\switch-llm.ps1' status`.

---

## TL;DR

```powershell
Set-Location -LiteralPath 'D:\[Project]_minderV2'   # go to project
.\scripts\windows\switch-llm.ps1 openai      # use OpenAI (gpt-5.4-mini / fallback gpt-5-mini)
.\scripts\windows\run-backend.ps1            # Terminal 1  -> API  http://127.0.0.1:8080
.\run-frontend.ps1           # Terminal 2  -> Web  http://localhost:5173  (open this)
```

Open **http://localhost:5173** and chat.

---

## 1. Prerequisites (once)

- **uv** installed (`uv --version`).
- **Docker Desktop running** — Minder's backend needs Postgres on `localhost:5432`.
- Frontend deps install automatically on first `run-frontend.ps1` (`npm install`).

### Start Postgres (localhost:5432)

If you already have the Minder Postgres container, just start it:

```powershell
docker start minder-pg
```

First time (creates it, loads schema, publishes 5432):

```powershell
docker run -d --name minder-pg -p 5432:5432 `
  -e POSTGRES_DB=minder -e POSTGRES_USER=minder -e POSTGRES_PASSWORD=minder `
  -v "D:\[Project]_minderV2\schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro" `
  postgres:16-alpine
```

Check it's up:

```powershell
(Test-NetConnection localhost -Port 5432 -WarningAction SilentlyContinue).TcpTestSucceeded  # -> True
```

`DATABASE_URL` in `.env` is already `postgresql://minder:minder@localhost:5432/minder`.

---

## 2. Run the app (two terminals)

**Terminal 1 — backend** (FastAPI, auto-restart loop, loads `.env` on each start):

```powershell
.\scripts\windows\run-backend.ps1     # -> http://127.0.0.1:8080
```

**Terminal 2 — frontend** (Vite dev server, proxies /api + /ws to :8080):

```powershell
.\run-frontend.ps1    # -> http://localhost:5173
```

Then open **http://localhost:5173** in a browser and chat.

---

## 3. Switch LLM provider

The switch rewrites four lines in `.env` (`OPENAI_API_KEY`, `MINDER_MODEL`,
`MINDER_FALLBACK_MODEL`, `MINDER_API_BASE_URL`). Minder reads the active provider's
key via `OPENAI_API_KEY` regardless of provider. **Everything — keys AND models —
lives in the `.env` vault** (commented `LLM_KEY_/LLM_MODEL_/LLM_FALLBACK_/LLM_BASE_<PROVIDER>`
lines); nothing is hardcoded in the script. To change a model or fallback, edit
its `LLM_MODEL_*` / `LLM_FALLBACK_*` line in `.env` and re-run the switch.

```powershell
.\scripts\windows\switch-llm.ps1 qwen      # Qwen via DashScope  (models from LLM_*_QWEN in .env)
.\scripts\windows\switch-llm.ps1 openai    # OpenAI              (models from LLM_*_OPENAI in .env)
.\scripts\windows\switch-llm.ps1 status    # show what's active now
```

**After switching, restart Terminal 1** (Ctrl+C, then `.\scripts\windows\run-backend.ps1`) so the
new `.env` is reloaded. The frontend needs no restart.

---

## 4. Quick API smoke test (no app needed)

Confirm a provider's key+endpoint+model are live before launching everything:

```powershell
$key='sk-b0bbbf41d88d4a77a0f3364b73d11502'   # DashScope key (see .env key vault)
$url='https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions'
$body=@{ model='qwen3.5-122b-a10b'; messages=@(@{role='user';content='Reply with: OK'}); max_tokens=16 } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri $url -Method Post -Headers @{ Authorization="Bearer $key" } -ContentType 'application/json' -Body $body
```

Expect a JSON response with `choices[0].message.content = "OK"`.

---

## Notes / gotchas

- **Endpoint must be the full path** including `/chat/completions`, and the
  **international** host `dashscope-intl.aliyuncs.com` (the key is invalid on the
  Beijing endpoint). `scripts\windows\switch-llm.ps1` sets this for you.
- **Qwen model choice:** `qwen3.5-122b-a10b` (capable, reliable tool calls, free
  quota). Avoid `qwen-max` / `qwen3-max` / `qwen-plus` / `qwen-turbo` — their free
  tier is exhausted (HTTP 403 `FreeTierOnly`) and qwen-max garbles tool output.
  `qwen3.5-flash` is the cheap fallback (free quota, "nearly out").
- **OpenAI** — active key is a project key (`proj_Zkh4…`) with live quota,
  verified via a real `gpt-5.4-mini` call (HTTP 200). If it ever returns 429
  `insufficient_quota` again, top up that project's credit or swap `LLM_KEY_OPENAI`
  in the `.env` vault.
- **qwen3.5 is a thinking model** — it spends some `reasoning_tokens` per reply;
  Minder's `max_tokens=8192` leaves plenty of room.
- `.env` is git-ignored; both API keys live only there (in the key vault comments).
