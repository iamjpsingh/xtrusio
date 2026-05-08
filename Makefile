SHELL := /bin/bash
.PHONY: help install env env-force supabase-start supabase-stop supabase-status valkey-up valkey-down db-up db-down db-logs api worker web dev lint format typecheck test check clean migrate migrate-down create-platform-owner

help:
	@echo "Xtrusio dev Makefile"
	@echo ""
	@echo "  make install         - install JS + Python dependencies"
	@echo "  make env             - generate .env from supabase status (refuses if .env exists)"
	@echo "  make env-force       - regenerate .env, overwriting if it exists"
	@echo "  make db-up           - start Supabase stack + xtrusio-valkey"
	@echo "  make db-down         - stop Supabase stack + xtrusio-valkey"
	@echo "  make db-logs         - tail Valkey logs (Supabase logs: \`supabase logs\`)"
	@echo "  make supabase-start  - Supabase only"
	@echo "  make supabase-stop   - Supabase only"
	@echo "  make supabase-status - print Supabase service URLs + keys"
	@echo "  make valkey-up       - Valkey only"
	@echo "  make valkey-down     - Valkey only"
	@echo "  make api             - run FastAPI dev server (XTRUSIO_PROCESS_ROLE=api)"
	@echo "  make worker          - placeholder; real worker added in later plans"
	@echo "  make web             - run Vite dev server"
	@echo "  make dev             - bring up DBs + API + web in parallel"
	@echo "  make lint            - lint Python + JS"
	@echo "  make format          - format Python + JS"
	@echo "  make typecheck       - mypy + tsc"
	@echo "  make test            - run all tests (Python + JS)"
	@echo "  make check           - lint + typecheck + test"
	@echo "  make clean           - remove caches and venvs"

install:
	pnpm install
	uv sync --all-packages

env:
	@if [ -f .env ]; then \
		echo "ERROR: .env already exists. Use 'make env-force' to overwrite, or edit it manually."; \
		exit 1; \
	fi
	@./scripts/generate-env.sh > .env
	@echo "Wrote .env with live Supabase keys."

env-force:
	@./scripts/generate-env.sh > .env
	@echo "Regenerated .env (existing values overwritten)."

supabase-start:
	supabase start

supabase-stop:
	supabase stop

supabase-status:
	supabase status

valkey-up:
	docker compose up -d valkey
	@echo "Waiting for xtrusio-valkey to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' xtrusio-valkey 2>/dev/null | grep -q healthy; do sleep 1; done
	@echo "Valkey ready (host :63792)."

valkey-down:
	docker compose down

db-up: supabase-start valkey-up
	@echo ""
	@echo "All services up:"
	@echo "  Supabase API     http://localhost:54321"
	@echo "  Supabase DB      postgresql://postgres:postgres@localhost:54322/postgres"
	@echo "  Supabase Studio  http://localhost:54323"
	@echo "  Inbucket (mail)  http://localhost:54324"
	@echo "  Valkey           localhost:63792"
	@echo ""
	@echo "Run 'make supabase-status' for anon/service-role keys."

db-down: supabase-stop valkey-down

db-logs:
	docker compose logs -f valkey

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

migrate:
	uv run --directory apps/api alembic upgrade head

migrate-down:
	uv run --directory apps/api alembic downgrade -1

create-platform-owner:
	@if [ -z "$(email)" ] || [ -z "$(password)" ]; then \
		echo "Usage: make create-platform-owner email=you@x.com password=..."; \
		exit 1; \
	fi
	XTRUSIO_PROCESS_ROLE=api uv run --directory apps/api \
		python -m xtrusio_api.scripts.bootstrap \
		--email "$(email)" --password "$(password)"

clean:
	rm -rf node_modules .pnpm-store .venv .turbo
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
