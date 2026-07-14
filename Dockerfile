# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: compile & install everything into a self-contained venv
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Pinned, reproducible uv binary (no pip bootstrap layer).
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

WORKDIR /app

# Build-only toolchain — never shipped in the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

# Build the venv against the image's own interpreter so its absolute paths
# (/app/.venv -> /usr/local/bin/python) stay valid when copied to the runtime
# stage, which shares the same python:3.12-slim base.
ENV UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# ── Layer 1: dependencies only (cached until the lockfile changes) ────────────
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── Layer 2: pre-cache tiktoken encodings so the container works offline ──────
# --no-dev: the image never installs dev-only deps (e.g. the minder_python_sdk
# path dep, which isn't in this layer's build context — module containers ship
# their own copy). Without it, `uv run` re-syncs dev and fails to resolve the path.
RUN uv run --no-dev python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# ── Layer 3: project source + install the package itself ──────────────────────
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Layer 4: pre-install every module's requirements.txt into the shared venv ─
# Mirrors minder.core.modules.deps.install_module_deps so the container is
# offline-safe and the first module call doesn't trigger an install. Stamp
# files match the runtime hash check, so registry load is a no-op.
RUN --mount=type=cache,target=/root/.cache/uv \
    for req in /app/modules/*/requirements.txt; do \
        [ -f "$req" ] || continue; \
        echo "[modules] installing $req"; \
        uv pip install --python /app/.venv/bin/python -r "$req" || exit 1; \
        sha256sum "$req" | awk '{print $1}' > "$(dirname "$req")/.deps.sha256"; \
    done

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: slim image, only shared libs the app needs at run time
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime-only shared libraries:
#   git                    -> gitpython shells out to the git binary
#   libpango* / libharfbuzz -> weasyprint PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (best practice: don't run the server as root).
RUN groupadd --system minder && useradd --system --gid minder --home-dir /home/minder --create-home minder \
    # Pre-create the settings dir owned by minder so a fresh named volume mounted
    # here (minder_data) inherits minder:minder ownership instead of defaulting to root.
    && mkdir -p /home/minder/.minder && chown minder:minder /home/minder/.minder

# Bring over the fully-built venv + application source from the builder.
COPY --from=builder --chown=minder:minder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # UTF-8 mode so logs/file writes never crash on non-ASCII (e.g. "✓").
    PYTHONUTF8=1 \
    HOME=/home/minder

USER minder

EXPOSE 8080

# Model + endpoint come from the environment (MINDER_MODEL / MINDER_API_BASE_URL,
# supplied via .env in compose). No hard-coded model default: the container
# fails fast if either is missing so misconfiguration is obvious.
ENTRYPOINT ["/bin/sh", "-c", "\
  mkdir -p \"$HOME/.minder\" && \
  : \"${MINDER_MODEL:?MINDER_MODEL must be set (add it to .env)}\" && \
  : \"${MINDER_API_BASE_URL:?MINDER_API_BASE_URL must be set (add it to .env)}\" && \
  SETTINGS=\"$HOME/.minder/settings.json\" && \
  TMP=\"$SETTINGS.tmp\" && \
  printf '{\"model\":\"%s\",\"api_base_url\":\"%s\"}\\n' \"$MINDER_MODEL\" \"$MINDER_API_BASE_URL\" > \"$TMP\" && \
  mv \"$TMP\" \"$SETTINGS\" && \
  exec minder --host 0.0.0.0 --port 8080\
"]
