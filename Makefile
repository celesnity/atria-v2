.PHONY: help install install-sdk install-ui install-ui-sdk format lint typecheck verify test test-file test-cov test-sdk test-ui-sdk check build-ui

PYTHON_DIRS = minder/ tests/
LINE_LENGTH = 100

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

install: install-sdk

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
