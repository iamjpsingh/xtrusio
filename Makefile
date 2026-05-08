SHELL := /bin/bash
.PHONY: help install db-up db-down db-logs api worker web dev lint format typecheck test check clean

help:
	@echo "Xtrusio dev Makefile"
	@echo ""
	@echo "  make install     - install JS + Python dependencies"
	@echo "  make db-up       - start xtrusio-postgres + xtrusio-valkey"
	@echo "  make db-down     - stop them"
	@echo "  make db-logs     - tail Postgres + Valkey logs"
	@echo "  make api         - run FastAPI dev server (XTRUSIO_PROCESS_ROLE=api)"
	@echo "  make worker      - placeholder; real worker added in later plans"
	@echo "  make web         - run Vite dev server"
	@echo "  make dev         - bring up DBs + API + web in parallel"
	@echo "  make lint        - lint Python + JS"
	@echo "  make format      - format Python + JS"
	@echo "  make typecheck   - mypy + tsc"
	@echo "  make test        - run all tests (Python + JS)"
	@echo "  make check       - lint + typecheck + test"
	@echo "  make clean       - remove caches and venvs"

install:
	pnpm install
	uv sync --all-packages

db-up:
	docker compose up -d postgres valkey
	@echo "Waiting for xtrusio-postgres and xtrusio-valkey to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-postgres 2>/dev/null | grep -q healthy; do sleep 1; done
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-valkey 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo "DBs ready (postgres on host :54322, valkey on host :63792)."

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres valkey

api:
	XTRUSIO_PROCESS_ROLE=api uv run uvicorn xtrusio_api.main:app --reload --port 8000 --app-dir apps/api/src

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

test:
	uv run pytest apps/api/tests
	pnpm exec turbo run test

check: lint typecheck test

clean:
	rm -rf node_modules .pnpm-store .venv .turbo
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
