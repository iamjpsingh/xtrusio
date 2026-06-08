SHELL := /bin/bash
.PHONY: help install valkey-up valkey-down db-up db-down db-logs dev-local dev-local-down api worker web dev lint format typecheck test test-cov test-clean check clean migrate migrate-down rbac-seed create-platform-owner

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
	@echo "  make rbac-seed       - project the permission catalog + backfill enum->user_roles"
	@echo "  make create-platform-owner email=you@x.com password='...' [force=true]"
	@echo "  make lint            - lint Python + JS"
	@echo "  make format          - format Python + JS"
	@echo "  make typecheck       - mypy + tsc"
	@echo "  make test            - run all tests (Python + JS)"
	@echo "  make test-cov        - backend tests with coverage gate (>=70%); not in 'check'"
	@echo "  make dev-local       - OPT-IN local Postgres (pgvector) for non-Supabase dev"
	@echo "  make check           - lint + typecheck + test"
	@echo "  make clean           - remove caches and venvs"
	@echo ""
	@echo "Supabase (managed): create a project at https://supabase.com, copy keys"
	@echo "from Project Settings into a .env file (use .env.example as the template),"
	@echo "then run 'make migrate' to apply migrations against your project's database."

install:
	pnpm install
	uv sync --all-packages
	@# Install BOTH git hook types (pre-commit + pre-push). The hook types come
	@# from default_install_hook_types in .pre-commit-config.yaml (PAR-F F.9).
	@# Best-effort: don't fail `make install` in CI where the hooks aren't wanted.
	-uv run pre-commit install 2>/dev/null || true

valkey-up:
	docker compose up -d valkey
	@echo "Waiting for xtrusio-valkey to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-valkey 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo "Valkey ready (host: 127.0.0.1:63792)."

valkey-down:
	docker compose down

db-up: valkey-up
	@echo ""
	@echo "Local infra up:"
	@echo "  Valkey  127.0.0.1:63792 (docker compose)"
	@echo ""
	@echo "Supabase Postgres/Auth/Realtime is managed — see .env for the project URL."

db-down: valkey-down

db-logs:
	docker compose logs -f valkey

dev-local:
	@echo "Starting OPT-IN local Postgres (pgvector) on host port 5433..."
	@echo "DEFAULT dev runtime is managed Supabase — this is a convenience for"
	@echo "contributors without a Supabase project. See ENGINEERING_PRINCIPLES §8a."
	docker compose -f docker-compose.local.yml up -d postgres-local
	@echo "Waiting for xtrusio-postgres-local to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-postgres-local 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo ""
	@echo "Local Postgres ready. Point DATABASE_URL at it, then 'make migrate':"
	@echo "  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/postgres"
	@echo "Supabase-free tests:  uv run pytest apps/api/tests -m 'not requires_supabase'"

dev-local-down:
	docker compose -f docker-compose.local.yml down

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

# Coverage gate (PAR-F F.5 / §9.4). NOT part of `make check` — local gates stay
# fast. The 70% floor is enforced authoritatively in CI (.github/workflows/
# security.yml::backend-coverage). Run this locally when you want the number.
test-cov:
	uv run --directory apps/api python -m tests._cleanup
	uv run pytest apps/api/tests \
		--cov=apps/api/src/xtrusio_api --cov-report=term-missing --cov-fail-under=70

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
