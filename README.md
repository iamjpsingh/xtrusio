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

- **Supabase CLI** — manages the local Postgres + GoTrue + Realtime stack:

  ```bash
  brew install supabase/tap/supabase-beta   # macOS
  ```

- **GNU Make** (preinstalled on macOS / Linux).

Optional but recommended: install [`mise`](https://mise.jdx.dev) (`brew install mise` on macOS), then `mise install` from the repo root pins Node, Python, and pnpm in one shot.

## First-time setup

```bash
git clone <repo>
cd xtrusio
make install
make db-up    # start Supabase (CLI) + Valkey (docker)
make env      # generate .env with live Supabase keys
```

After this, `make dev` from now on. If Supabase keys ever rotate (e.g., you wiped local Supabase volumes), regenerate:

```bash
make env-force
```

`.env` is gitignored — never commit it.

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

## Local services

The local stack is split between two managers:

**Supabase CLI** (`supabase start` — wrapped by `make db-up`):

| Service                       | URL / port                        |
| ----------------------------- | --------------------------------- |
| Supabase API gateway (Kong)   | `http://localhost:54321`          |
| GoTrue (auth)                 | `http://localhost:54321/auth/v1`  |
| PostgREST                     | `http://localhost:54321/rest/v1`  |
| Realtime                      | `http://localhost:54321/realtime` |
| **Postgres 17 + pgvector**    | `localhost:54322`                 |
| Studio (web UI for Postgres)  | `http://localhost:54323`          |
| Inbucket (local email viewer) | `http://localhost:54324`          |

Run `make supabase-status` to print URLs + freshly-generated anon/service-role keys (copy the keys into your `.env`, never commit them).

**Our `docker-compose.yml`** (Valkey only — Supabase doesn't ship Valkey):

| Service  | Container name   | Host port         | In-network address |
| -------- | ---------------- | ----------------- | ------------------ |
| Valkey 8 | `xtrusio-valkey` | `localhost:63792` | `valkey:6379`      |

Valkey runs on the `xtrusio-net` Docker network. Containers we add later that need to talk to Valkey will join `xtrusio-net` and resolve `valkey:6379` by name.

> **Why split?** Supabase CLI manages its own private Docker network. Putting our Valkey on `xtrusio-net` keeps our future containerized services (workers, etc.) on a network we control, while Supabase services stay on the Supabase-managed network. Cross-network communication via host ports.

## URLs

- **Web (Vite):** http://localhost:5173
  - `/` Dashboard
  - `/users`, `/clients`, `/settings`, `/sign-in` (placeholder routes with empty states)
- **API:** http://localhost:8000
  - Health: `/health`
  - OpenAPI: `/docs`
- **Supabase Studio:** http://localhost:54323
- **Inbucket (mail):** http://localhost:54324

## Engineering rules

See [`docs/superpowers/ENGINEERING_PRINCIPLES.md`](docs/superpowers/ENGINEERING_PRINCIPLES.md). The big ones:

- **TypeScript only on the frontend.** No `.js` / `.jsx` / `.mjs` / `.cjs`. Source AND configs (§2.0).
- **No custom CSS** outside `apps/web/src/globals.css`. Every component composes Tailwind utilities + shadcn primitives.
- **No hardcoded colors.** Use semantic tokens (`bg-background`, `text-muted-foreground`, `bg-success/10`, etc.). Pre-commit hook (`no-hardcoded-colors`) blocks `#hex` and `bg-zinc-*`/`bg-gray-*`/etc.
- **No demo or mock data.** Empty states are first-class. The first platform owner is bootstrapped via a CLI script (Plan 1B/1C); every other user is invited via real flows.
- **Strict typing.** No `any`, branded IDs, Zod-as-source-of-truth.
- **`mypy --strict`** on Python.
- **500 LoC ceiling per file**, 200-300 target.
- **Pre-commit hooks** enforce ruff, prettier, no-js-in-frontend, no-hardcoded-colors, and large-file checks locally.

## Why apps run on the host (not in Docker) for dev

Stateful services (Postgres, Valkey, Inbucket, etc.) run in Docker. **Application code (FastAPI, Vite/React, future workers) runs natively on the host** via `uv` and `pnpm`. The `Makefile` ties them together.

This is a deliberate choice:

- **Hot reload** is much faster on the host than across volume mounts.
- **IDE + types + debugger** work naturally on the host. In Docker, the IDE can't see container internals cleanly.
- **Test loops** are sub-second on the host.

Production is a separate concern — see below.

If you've used a "full docker-compose" stack elsewhere and miss the "one command" simplicity: `make dev` is that one command, just with better DX.

## Production target

- **Database + Auth + Realtime:** **self-hosted Supabase** (the full stack on owned infrastructure — NOT supabase.com cloud). The Supabase CLI we use locally pulls the same Docker images as the official self-hosted reference, so dev→prod parity is real and migrations apply byte-identically.
- **Web frontend:** **Cloudflare Pages.** `pnpm build` produces the static `dist/` that ships to the CDN.
- **API:** **VPS-hosted FastAPI** (long-running uvicorn/gunicorn behind Caddy or nginx for TLS). Not Cloudflare Workers, not Fly machines — full VPS so we can run heavy Python libraries (sentence-transformers, Polars, etc.) and long-running background workers without edge-runtime constraints. Will land as `apps/api/Dockerfile` when we ship.
- **Workers (Dramatiq + Prefect, future):** same VPS as the API (or a sibling VPS if scale demands), as separate processes (systemd units or sibling containers).
- **Cache:** self-hosted Valkey on the API VPS.

A future deploy plan covers production `docker-compose.yml` for Supabase, the API Dockerfile, VPS provisioning, the Pages build pipeline, migration deploy automation, backups, secrets management, and TLS. None of this is part of Plan 1A.

## CI/CD

Not in scope yet. Project policy: CI/CD is added once the local development environment runs cleanly end-to-end. Until then, `make check` and the pre-commit hook are the contract.
