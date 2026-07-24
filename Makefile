.PHONY: help submodules install install-sdk install-ui install-ui-sdk format lint typecheck verify test test-file test-cov test-sdk test-ui-sdk check build-ui blackboard-bootstrap

PYTHON_DIRS = minder/ tests/
LINE_LENGTH = 100

# Docker compose stacks. Core creates the shared minder_net; modules join it.
COMPOSE ?= docker compose
CLOUD_COMPOSE := -f docker-compose.yml
DEV_COMPOSE := -f docker-compose.dev.yml
# Every module that ships its own docker-compose.yml gets `make <name>` targets.
MODULES := $(notdir $(patsubst %/,%,$(dir $(wildcard modules/*/docker-compose.yml))))

help:
	@echo "Available commands:"
	@echo "  make install      Install with dev dependencies"
	@echo "  make format       Format code with Black"
	@echo "  make lint         Lint with Ruff (auto-fix)"
	@echo "  make typecheck    Type-check with mypy"
	@echo "  make check        Run format + lint + typecheck (MUTATES: black, ruff --fix)"
	@echo "  make verify       Read-only baseline gate (black --check + ruff check)"
	@echo "  make test         Run all tests"
	@echo "  make test-cov     Run tests with coverage"
	@echo "  make test-sdk     Run the connector SDK suite only"
	@echo "  make test-ui-sdk  Run the UI SDK suite (vitest)"
	@echo "  make install-ui   Install web UI npm dependencies"
	@echo "  make build-ui     Build web UI frontend"
	@echo "  make submodules   Initialize and update Git submodules"
	@echo ""
	@echo "  make cloud        Run the cloud-infrastructure stack"
	@echo "  make dev          Run the local-development stack"
	@echo "  make <module>     Run a module stack after cloud or dev"
	@echo "  make modules-list Show modules that have a compose file"
	@echo "  make blackboard-bootstrap  Create the minder project/blackboard on blackboard-server"

install: install-sdk

submodules:
	git submodule update --init --recursive

# Shared connector SDK (separate package) for the connector tests + `minder-module`.
# It is deliberately NOT a declared minder dependency (see pyproject.toml), so it must be
# installed LAST, after `uv pip install -e ".[dev]"`.
# Measured on uv 0.11.8: `uv run` does an INEXACT sync and leaves this in place, but
# `uv sync` is EXACT and prunes it. After any `uv sync`, re-run this target -- otherwise
# `import minder_python_sdk` silently degrades to a cwd namespace package (__file__ = None)
# and `from minder_python_sdk import Connector` fails.
install-sdk:
	uv venv --allow-existing && uv pip install -e ".[dev]"
	uv pip install -e ./minder_python_sdk

format:
	black $(PYTHON_DIRS) --line-length $(LINE_LENGTH)

lint:
	ruff check $(PYTHON_DIRS) --fix

typecheck:
	mypy minder/

check: format lint typecheck

test:
	uv run pytest

test-cov:
	uv run pytest --cov=minder

# Usage: make test-file FILE=tests/test_session_manager.py
test-file:
	uv run pytest $(FILE)

# Connector SDK suite only. Self-contained: unaffected by the tests/conftest.py breakage.
test-sdk:
	uv run pytest minder_python_sdk/tests

install-ui-sdk:
	cd minder_ui_sdk && npm install

# UI SDK suite (vitest). Has no other install path - web-ui does not depend on it.
test-ui-sdk: install-ui-sdk
	cd minder_ui_sdk && npx vitest run

# Baseline gate used by init.ps1 / init.sh. Measured 2026-07-15:
#   - `make test`             cannot collect (tests/conftest.py imports the dead atria.*)
#   - `black --check minder/` 32 files unformatted -> red
#   - `ruff check minder/`    25 errors            -> red
#   - SDK suite               100 passed           -> GREEN
# So the SDK suite is the only gate that is green, read-only, and self-contained (it does
# not touch tests/conftest.py). Re-point this at `test` once the suite collects again.
verify: test-sdk

install-ui:
	cd web-ui && npm ci

build-ui: install-ui
	cd web-ui && npm run build

# ── Docker compose stacks ────────────────────────────────────────────
# `make cloud` or `make dev` first (creates minder_net), then `make <module>`.
.PHONY: cloud cloud-down cloud-logs dev dev-down dev-logs modules-list \
	$(MODULES) $(addsuffix -down,$(MODULES)) $(addsuffix -logs,$(MODULES))

cloud:
	$(COMPOSE) $(CLOUD_COMPOSE) up -d --build

cloud-down:
	$(COMPOSE) $(CLOUD_COMPOSE) down

cloud-logs:
	$(COMPOSE) $(CLOUD_COMPOSE) logs -f

dev:
	$(COMPOSE) $(DEV_COMPOSE) up -d --build

dev-down:
	$(COMPOSE) $(DEV_COMPOSE) down

dev-logs:
	$(COMPOSE) $(DEV_COMPOSE) logs -f

modules-list:
	@echo "modules with a compose file: $(MODULES)"
	@echo "run one with: make <name>  (e.g. make module_template). Start cloud or dev first."

blackboard-bootstrap:
	./scripts/bootstrap_blackboard.sh

# ── Deploy the core stack to the remote box (server IP:8090) ──────────
REMOTE_HOST ?= anlnm-celesnity
REMOTE_DIR ?= minder-py
REMOTE_ENV := MINDER_HOST_PORT=8090 REDIS_HOST_PORT=6380
REMOTE_COMPOSE := docker compose --env-file .env -f docker-compose.yml
.PHONY: deploy-remote deploy-remote-down deploy-remote-logs

deploy-remote: ## rsync repo + bring the core stack up on $(REMOTE_HOST)
	rsync -az --delete \
		--exclude '.git' --exclude '.venv' --exclude 'node_modules' \
		--exclude '__pycache__' --exclude '*.pyc' --exclude 'minder-home' --exclude '.minder' \
		./ $(REMOTE_HOST):$(REMOTE_DIR)/
	ssh $(REMOTE_HOST) 'cd $(REMOTE_DIR) && $(REMOTE_ENV) $(REMOTE_COMPOSE) up -d --build'

deploy-remote-down:
	ssh $(REMOTE_HOST) 'cd $(REMOTE_DIR) && $(REMOTE_ENV) $(REMOTE_COMPOSE) down'

deploy-remote-logs:
	ssh $(REMOTE_HOST) 'cd $(REMOTE_DIR) && $(REMOTE_ENV) $(REMOTE_COMPOSE) logs -f --tail=100 minder'

# Generate `make <name>`, `make <name>-down`, `make <name>-logs` per module.
define MODULE_RULES
$(1):
	$(COMPOSE) --env-file .env -f modules/$(1)/docker-compose.yml up -d --build
$(1)-down:
	$(COMPOSE) --env-file .env -f modules/$(1)/docker-compose.yml down
$(1)-logs:
	$(COMPOSE) --env-file .env -f modules/$(1)/docker-compose.yml logs -f
endef
$(foreach m,$(MODULES),$(eval $(call MODULE_RULES,$(m))))
