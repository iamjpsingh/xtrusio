SHELL := /bin/bash
.PHONY: help install valkey-up valkey-down db-up db-down db-logs api worker web dev lint format typecheck test test-clean check clean migrate migrate-down rbac-seed create-platform-owner

# API bind host/port come from .env (no hardcoded values in the Makefile).
# Surgically extract just these two keys; never source the whole .env (its
# values contain characters the shell would mis-parse).
API_HOST := $(shell grep -E '^API_HOST=' .env 2>/dev/null | head -1 | cut -d= -f2-)
API_PORT := $(shell grep -E '^API_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2-)

help:
	@echo "Xtrusio dev Makefile"
	@echo ""
	@echo "  make install         - install JS + Python dependencies"
	@echo "  make db-up           - start local infra (Valkey container)"
	@echo "  make db-down         - stop local infra"
	@echo "  make db-logs         - tail Valkey logs"
	@echo "  make valkey-up       - Valkey only"
	@echo "  make valkey-down     - Valkey only"
	@echo "  make api             - run FastAPI dev server (XTRUSIO_PROCESS_ROLE=api)"
	@echo "  make worker          - placeholder; real worker added in later plans"
	@echo "  make web             - run Vite dev server"
	@echo "  make dev             - bring up Valkey + API + web in parallel"
	@echo "  make migrate         - apply Alembic migrations to the database in DATABASE_URL"
	@echo "  make migrate-down    - revert the most recent migration"
	@echo "  make rbac-seed       - project the permission catalog into the DB"
	@echo "  make create-platform-owner email=you@x.com password='...' [force=true]"
	@echo "  make lint            - lint Python + JS"
	@echo "  make format          - format Python + JS"
	@echo "  make typecheck       - mypy + tsc"
	@echo "  make test            - run all tests (Python + JS)"
	@echo "  make check           - lint + typecheck + test"
	@echo "  make clean           - remove caches and venvs"
	@echo ""
	@echo "Supabase (managed): create a project at https://supabase.com, copy keys"
	@echo "from Project Settings into a .env file (use .env.example as the template),"
	@echo "then run 'make migrate' to apply migrations against your project's database."

install:
	pnpm install
	uv sync --all-packages

valkey-up:
	docker compose up -d valkey
	@echo "Waiting for xtrusio-valkey to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-valkey 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo "Valkey ready (host: xtrusio-valkey.orb.local:6379 via OrbStack DNS)."

valkey-down:
	docker compose down

db-up: valkey-up
	@echo ""
	@echo "Local infra up:"
	@echo "  Valkey  xtrusio-valkey.orb.local:6379 (OrbStack DNS)"
	@echo ""
	@echo "Supabase Postgres/Auth/Realtime is managed — see .env for the project URL."

db-down: valkey-down

db-logs:
	docker compose logs -f valkey

api:
	@if [ -z "$(API_HOST)" ] || [ -z "$(API_PORT)" ]; then \
		echo "API_HOST and API_PORT must be set in .env (see .env.example)"; exit 1; \
	fi
	XTRUSIO_PROCESS_ROLE=api uv run uvicorn xtrusio_api.main:app --reload --host $(API_HOST) --port $(API_PORT) --app-dir apps/api/src

worker:
	@echo "worker target is a placeholder until later plans add Dramatiq/Prefect."
	@echo "Run 'XTRUSIO_PROCESS_ROLE=worker uv run python -c \"print(\\\"worker shell ready\\\")\"' for now."

web:
	pnpm --filter @xtrusio/web dev

dev: db-up
	@trap 'kill 0' INT TERM; \
	$(MAKE) api & \
	$(MAKE) web & \
	wait

lint:
	uv run ruff check apps/api
	uv run ruff format --check apps/api
	pnpm exec turbo run lint

format:
	uv run ruff format apps/api
	uv run ruff check --fix apps/api
	pnpm exec prettier --write .

typecheck:
	uv run mypy apps/api
	pnpm exec turbo run typecheck

test-clean:
	uv run --directory apps/api python -m tests._cleanup

test:
	uv run --directory apps/api python -m tests._cleanup
	uv run pytest apps/api/tests
	pnpm exec turbo run test

check: lint typecheck test

migrate:
	uv run --directory apps/api alembic upgrade head

rbac-seed:
	uv run --directory apps/api python -m xtrusio_api.rbac

migrate-down:
	uv run --directory apps/api alembic downgrade -1

create-platform-owner:
	@if [ -z "$(email)" ] || [ -z "$(password)" ]; then \
		echo "Usage: make create-platform-owner email=you@x.com password=...  [force=true]"; \
		exit 1; \
	fi
	@FORCE_FLAG=""; \
	if [ "$(force)" = "true" ]; then FORCE_FLAG="--force"; fi; \
	XTRUSIO_PROCESS_ROLE=api uv run --directory apps/api \
		python -m xtrusio_api.scripts.bootstrap \
		--email "$(email)" --password "$(password)" $$FORCE_FLAG

clean:
	rm -rf node_modules .pnpm-store .venv .turbo
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
