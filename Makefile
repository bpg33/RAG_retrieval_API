# Synology RAG Retrieval Platform - developer tasks.
# On Windows, run these from WSL or Git Bash, or use scripts/install-windows.ps1.

PY ?= python
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help install dev lint format typecheck test test-int test-cov \
        run-api run-mcp discover-qdrant discover-postgres verify-readonly \
        smoke benchmark openapi docker-build docker-up clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install locked dependencies
	uv venv $(VENV)
	VIRTUAL_ENV=$(VENV) uv pip install -e ".[dev]"

dev: install ## Alias for install

lint: ## Ruff lint
	$(BIN)/ruff check src scripts tests

format: ## Ruff format + autofix
	$(BIN)/ruff format src scripts tests
	$(BIN)/ruff check --fix src scripts tests

typecheck: ## mypy strict type check
	MYPYPATH=src $(BIN)/mypy src

test: ## Run unit/contract/security/quality tests (no live services)
	PYTHONPATH=src:. $(BIN)/python -m pytest

test-int: ## Run integration tests against live services (needs .env + RUN_INTEGRATION=1)
	PYTHONPATH=src:. RUN_INTEGRATION=1 $(BIN)/python -m pytest -m integration

test-cov: ## Tests with coverage
	PYTHONPATH=src:. $(BIN)/python -m pytest --cov=synology_rag --cov-report=term-missing

run-api: ## Start the REST API
	$(BIN)/python -m synology_rag.api

run-mcp: ## Start the MCP server (stdio)
	$(BIN)/python -m synology_rag.mcp.server

discover-qdrant: ## Read-only Qdrant discovery
	$(BIN)/python scripts/inspect_qdrant.py

discover-postgres: ## Read-only PostgreSQL discovery
	$(BIN)/python scripts/inspect_postgres.py

verify-readonly: ## Verify read-only enforcement
	$(BIN)/python scripts/verify_read_only.py

smoke: ## End-to-end smoke test (needs .env). Usage: make smoke Q="your question"
	$(BIN)/python scripts/smoke_test.py --query "$(Q)"

benchmark: ## Retrieval benchmark (needs .env + dataset)
	$(BIN)/python scripts/benchmark.py

openapi: ## Export the OpenAPI schema to docs/openapi.json
	PYTHONPATH=src $(BIN)/python scripts/export_openapi.py

docker-build: ## Build the container image
	docker build -t synology-rag-retrieval:local .

docker-up: ## Start with docker compose
	docker compose up --build

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__
