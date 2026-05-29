SHELL := /bin/bash
.PHONY: help install redis-up redis-down redis-logs api worker web dev lint format typecheck test check clean migrate migrate-new create-platform-owner

help:
	@echo "Xtrusio dev Makefile"
	@echo ""
	@echo "  make install              - install JS + Python dependencies"
	@echo "  make redis-up             - start xtrusio-redis (optional, for workers)"
	@echo "  make redis-down           - stop xtrusio-redis"
	@echo "  make redis-logs           - tail Redis logs"
	@echo "  make api                  - run FastAPI dev server against managed Supabase dev project"
	@echo "  make worker               - run arq worker"
	@echo "  make web                  - run Vite dev server"
	@echo "  make dev                  - run api + web in parallel"
	@echo "  make migrate              - apply migrations to the project in DATABASE_URL"
	@echo "  make migrate-new name=... - create a new SQL migration file"
	@echo "  make lint                 - lint Python + JS"
	@echo "  make format               - format Python + JS"
	@echo "  make typecheck            - mypy + tsc"
	@echo "  make test                 - run all tests (Python + JS)"
	@echo "  make check                - lint + typecheck + test"
	@echo "  make create-platform-owner email=... password=...  [force=true]"
	@echo "  make clean                - remove caches and venvs"
	@echo ""
	@echo "First-time setup: create a Supabase project at supabase.com, copy"
	@echo "credentials into .env (see .env.example), then 'make migrate'."

install:
	pnpm install
	uv sync --all-packages

redis-up:
	docker compose up -d redis
	@echo "Waiting for xtrusio-redis to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-redis 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo "Redis ready (host :6379)."

redis-down:
	docker compose down

redis-logs:
	docker compose logs -f redis

api:
	XTRUSIO_PROCESS_ROLE=api uv run uvicorn xtrusio_api.main:app --reload --port 8000 --app-dir apps/api/src

worker:
	XTRUSIO_PROCESS_ROLE=worker uv run --directory apps/api arq xtrusio_api.workers.main.WorkerSettings

web:
	pnpm --filter @xtrusio/web dev

dev:
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

migrate:
	uv run --directory apps/api alembic upgrade head

migrate-new:
	@if [ -z "$(name)" ]; then \
		echo "Usage: make migrate-new name=add_some_table"; \
		exit 1; \
	fi
	uv run --directory apps/api alembic revision -m "$(name)"

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
