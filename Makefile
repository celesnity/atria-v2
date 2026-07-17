.PHONY: help install install-ui format lint typecheck test test-file test-cov check build-ui

PYTHON_DIRS = minder/ tests/
LINE_LENGTH = 100

# Docker compose stacks. Core creates the shared minder_net; modules join it.
COMPOSE ?= docker compose
CORE_FILES := -f docker-compose.yml -f docker-compose.local.yml
# Every module that ships its own docker-compose.yml gets `make <name>` targets.
MODULES := $(notdir $(patsubst %/,%,$(dir $(wildcard modules/*/docker-compose.yml))))

help:
	@echo "Available commands:"
	@echo "  make install      Install with dev dependencies"
	@echo "  make format       Format code with Black"
	@echo "  make lint         Lint with Ruff (auto-fix)"
	@echo "  make typecheck    Type-check with mypy"
	@echo "  make check        Run format + lint + typecheck"
	@echo "  make test         Run all tests"
	@echo "  make test-cov     Run tests with coverage"
	@echo "  make install-ui   Install web UI npm dependencies"
	@echo "  make build-ui     Build web UI frontend"
	@echo ""
	@echo "  make core         Run the core Minder stack (docker; creates minder_net)"
	@echo "  make <module>     Run a module stack, e.g. make produce  (run core first)"
	@echo "  make modules-list Show modules that have a compose file"

install:
	uv venv && uv pip install -e ".[dev]"
	# Shared connector SDK (separate package) for the connector tests + `minder-module`.
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

install-ui:
	cd web-ui && npm ci

build-ui: install-ui
	cd web-ui && npm run build

# ── Docker compose stacks ────────────────────────────────────────────
# `make core` first (creates minder_net), then `make <module>` (e.g. produce).
.PHONY: core core-down core-logs modules-list \
	$(MODULES) $(addsuffix -down,$(MODULES)) $(addsuffix -logs,$(MODULES))

core:
	$(COMPOSE) $(CORE_FILES) up -d --build

core-down:
	$(COMPOSE) $(CORE_FILES) down

core-logs:
	$(COMPOSE) $(CORE_FILES) logs -f

modules-list:
	@echo "modules with a compose file: $(MODULES)"
	@echo "run one with: make <name>  (e.g. make produce). Needs 'make core' first."

# ── Deploy the core stack to the remote box (server IP:8090) ──────────
REMOTE_HOST ?= anlnm-celesnity
REMOTE_DIR ?= minder-py
REMOTE_ENV := MINDER_HOST_PORT=8090 REDIS_HOST_PORT=6380
REMOTE_COMPOSE := docker compose --env-file .env -f docker-compose.yml -f docker-compose.local.yml -f docker-compose.remote.yml
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
