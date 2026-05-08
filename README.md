# Xtrusio

Multi-tenant AI SaaS platform.

## Prerequisites

- **Docker Desktop** (or compatible runtime) — running.
- **Node 22** — manage with `mise` (preferred), `fnm`, `nvm`, or `volta`. Project uses the version in `.nvmrc` / `mise.toml`.
- **pnpm 10** — `corepack enable && corepack prepare pnpm@10 --activate`, or installed via `mise`.
- **Python 3.12** — `uv` will manage the interpreter; install `uv` itself:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **GNU Make** (preinstalled on macOS / Linux).

Optional but recommended: install [`mise`](https://mise.jdx.dev) (`brew install mise` on macOS), then `mise install` from the repo root pins Node, Python, and pnpm in one shot.

## First-time setup

```bash
git clone <repo>
cd xtrusio
cp .env.example .env       # optional — defaults work for local dev
make install
```

## Daily development

| Command                       | What it does                                                |
| ----------------------------- | ----------------------------------------------------------- |
| `make dev`                    | Brings up Postgres + Valkey + API + Web in one terminal.    |
| `make db-up` / `make db-down` | DBs only.                                                   |
| `make api`                    | FastAPI dev server on `:8000` (`XTRUSIO_PROCESS_ROLE=api`). |
| `make web`                    | Vite dev server on `:5173`.                                 |
| `make worker`                 | Placeholder until later plans add Dramatiq / Prefect.       |
| `make lint`                   | Ruff + ESLint check.                                        |
| `make format`                 | Auto-format Python + TypeScript.                            |
| `make typecheck`              | mypy + tsc.                                                 |
| `make test`                   | pytest + Vitest.                                            |
| `make check`                  | lint + typecheck + test (run before committing).            |
| `make clean`                  | Wipe caches and venvs.                                      |

## Layout

```
apps/
  api/       FastAPI backend (Python, uv-managed)
  web/       Vite + React frontend (TypeScript only — no .js anywhere)
packages/
  ui/        Shared UI components (placeholder until later plans)
  api-types/ Generated OpenAPI types (placeholder until later plans)
infra/
  postgres/  Postgres init scripts (extensions)
docs/
  superpowers/specs/   Design specs
  superpowers/plans/   Implementation plans
```

## Local services (Docker)

All services run on a custom Docker network (`xtrusio-net`) with named containers and **non-default host ports** so they don't collide with other databases on your machine:

| Service                | Container name     | Host port         | In-network address |
| ---------------------- | ------------------ | ----------------- | ------------------ |
| Postgres 16 + pgvector | `xtrusio-postgres` | `localhost:54322` | `postgres:5432`    |
| Valkey 8               | `xtrusio-valkey`   | `localhost:63792` | `valkey:6379`      |

Apps running on the host connect via the host ports above (defaults already set in `.env.example`). Containers that join `xtrusio-net` (later plans) talk to each other by name.

## URLs

- **API:** http://localhost:8000
  - Health: `/health`
  - OpenAPI: `/docs`
- **Web:** http://localhost:5173

## Engineering rules

See [`docs/superpowers/ENGINEERING_PRINCIPLES.md`](docs/superpowers/ENGINEERING_PRINCIPLES.md). The big ones:

- **TypeScript only on the frontend.** No `.js` / `.jsx` / `.mjs` / `.cjs`. Source AND configs (§2.0).
- **Strict typing.** No `any`, branded IDs, Zod-as-source-of-truth.
- **mypy --strict** on Python.
- **500 LoC ceiling per file**, 200-300 target.
- **Pre-commit hook** (added in Task 17A of Plan 1A) enforces these locally.

## CI/CD

Not in scope yet. Project policy: CI/CD is added once the local development environment runs cleanly end-to-end. Until then, `make check` and the pre-commit hook are the contract.
