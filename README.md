# Atria

## Repository Structure

```
opendev-py/
├── atria/                  # Main Python package
│   ├── cli/                # CLI entry points & commands
│   ├── config/             # Config loading & models
│   ├── core/               # Agent core
│   │   ├── agents/         # Main, planning, sub-agents + prompt templates
│   │   ├── context_engineering/   # Tools, MCP, memory, compaction, history
│   │   └── runtime/        # Config, mode manager, approval system
│   ├── models/             # Shared data models / agent deps
│   ├── ui_textual/         # Textual TUI (chat_app, runner, ui_callback)
│   ├── web/                # FastAPI backend + websocket + static UI
│   └── skills/             # Built-in skills
├── web-ui/                 # React/Vite/Zustand frontend (builds into atria/web/static)
├── tests/                  # Pytest suite
├── docs/                   # Provider setup & guides
├── schema.sql              # Postgres schema (loaded by db container on init)
├── Dockerfile              # Atria app image
├── docker-compose.yml      # Prod-ish stack: db + adminer + atria
├── docker-compose.dev.yml  # Dev overrides (live reload, mounted volumes)
├── Makefile                # install / format / lint / typecheck / test / build-ui
├── pyproject.toml          # Package metadata & deps
└── requirements.txt
```

## Run with Docker Compose

Requirements: Docker + Docker Compose v2.

```bash
# 1. Copy env template and set your keys
cp .env.example .env
# edit .env -> set OPENAI_API_KEY (or your provider key)

# 2. Build and start the full stack (postgres + adminer + atria)
docker compose up -d --build

# 3. Tail logs
docker compose logs -f atria
```

Services:

- **atria** — http://localhost:8080 (web UI + API)
- **adminer** — http://localhost:8081 (DB browser, server `db`, user/pass `atria`/`atria`)
- **db** — Postgres 16 on internal network, schema auto-loaded from `schema.sql`

### Dev mode (live reload, source mounted)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### Common ops

```bash
docker compose ps                 # status
docker compose restart atria      # restart app only
docker compose down               # stop stack (keeps volumes)
docker compose down -v            # stop + wipe postgres volume
```
