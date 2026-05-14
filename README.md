# Xtrusio

Multi-tenant AI SaaS platform.

## Prerequisites

- **Docker Desktop** (or compatible runtime) — running. Used for the local Valkey container.
- **Node 22** — manage with `mise` (preferred), `fnm`, `nvm`, or `volta`. Project uses the version in `.nvmrc` / `mise.toml`.
- **pnpm 10** — `corepack enable && corepack prepare pnpm@10 --activate`, or installed via `mise`.
- **Python 3.12** — `uv` will manage the interpreter; install `uv` itself:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **GNU Make** (preinstalled on macOS / Linux).
- **Managed Supabase project** — create one at https://supabase.com. Postgres (with pgvector available), GoTrue, Realtime, and Storage are all provided by the project. We do **not** use the Supabase CLI for local dev.

Optional but recommended: install [`mise`](https://mise.jdx.dev) (`brew install mise` on macOS), then `mise install` from the repo root pins Node, Python, and pnpm in one shot.

## First-time setup

```bash
git clone <repo>
cd xtrusio
make install
cp .env.example .env       # fill in values from your Supabase project
make db-up                 # start local Valkey
make migrate               # apply Alembic migrations to your Supabase Postgres
```

Edit `.env`:

- `DATABASE_URL` — Supabase Dashboard → Project Settings → Database → **Direct connection** (port 5432, host `db.<PROJECT_REF>.supabase.co`). Prefix with `postgresql+asyncpg://` for SQLAlchemy.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWKS_URL` — Dashboard → Project Settings → API (JWKS URL under JWT Settings).
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` — same project URL + anon key (frontend bundle; never use service_role here).

`.env` is gitignored — never commit it.

## Bootstrap the first super_admin

Once migrations are applied, create the first platform owner via CLI:

```bash
make create-platform-owner email=you@x.com password='SecurePass123!'
```

This calls the Supabase Admin API (service_role) to create the auth user, then inserts the matching `platform_users` row with `role='super_admin'`.

Then sign in at http://localhost:5173/sign-in with those credentials.

## Daily development

| Command                       | What it does                                            |
| ----------------------------- | ------------------------------------------------------- |
| `make dev`                    | Brings up local Valkey + API + Web in one terminal.     |
| `make db-up` / `make db-down` | Local Valkey only.                                      |
| `make api`                    | FastAPI dev server on `:8000` (`XTRUSIO_PROCESS_ROLE=api`). |
| `make web`                    | Vite dev server on `:5173`.                             |
| `make worker`                 | Placeholder until later plans add Dramatiq / Prefect.   |
| `make migrate`                | Apply Alembic migrations to the `DATABASE_URL` project. |
| `make migrate-down`           | Revert the most recent migration.                       |
| `make lint`                   | Ruff + ESLint check.                                    |
| `make format`                 | Auto-format Python + TypeScript.                        |
| `make typecheck`              | mypy + tsc.                                             |
| `make test`                   | pytest + Vitest.                                        |
| `make check`                  | lint + typecheck + test (run before committing).        |
| `make clean`                  | Wipe caches and venvs.                                  |

## Layout

```
apps/
  api/       FastAPI backend (Python, uv-managed)
  web/       Vite + React frontend (TypeScript only — no .js anywhere)
packages/
  ui/        Shared UI components (placeholder until later plans)
  api-types/ Generated OpenAPI types (placeholder until later plans)
docs/
  superpowers/specs/   Design specs
  superpowers/plans/   Implementation plans
```

## Local services

Only Valkey runs locally; everything else lives in your managed Supabase project.

**`docker-compose.yml`:**

| Service  | Container name   | Host (OrbStack DNS)              | In-network address |
| -------- | ---------------- | -------------------------------- | ------------------ |
| Valkey 8 | `xtrusio-valkey` | `xtrusio-valkey.orb.local:6379`  | `valkey:6379`      |

No host ports are published — OrbStack's auto-DNS (`<container>.orb.local`) is how the host reaches Valkey. This guarantees zero conflict with other local Docker stacks. Containers we add later that need to talk to Valkey will join `xtrusio-net` and resolve `valkey:6379` by name.

(If you're on Docker Desktop instead of OrbStack, add a `ports:` mapping in `docker-compose.yml` and set `VALKEY_URL=redis://localhost:63792/0`.)

**Managed Supabase (set in `.env`):**

| Service             | URL                                                |
| ------------------- | -------------------------------------------------- |
| Supabase API        | `https://<PROJECT_REF>.supabase.co`                |
| Postgres (direct)   | `db.<PROJECT_REF>.supabase.co:5432`                |
| Auth (GoTrue)       | `https://<PROJECT_REF>.supabase.co/auth/v1`        |
| Realtime            | `https://<PROJECT_REF>.supabase.co/realtime/v1`    |
| Studio (dashboard)  | `https://supabase.com/dashboard/project/<PROJECT_REF>` |

## URLs

- **Web (Vite):** http://localhost:5173
  - `/` Dashboard
  - `/users`, `/clients`, `/settings`, `/sign-in`
- **API:** http://localhost:8000
  - Health: `/health`
  - OpenAPI: `/docs`

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

Valkey runs in Docker. **Application code (FastAPI, Vite/React, future workers) runs natively on the host** via `uv` and `pnpm`. The `Makefile` ties them together.

This is a deliberate choice:

- **Hot reload** is much faster on the host than across volume mounts.
- **IDE + types + debugger** work naturally on the host. In Docker, the IDE can't see container internals cleanly.
- **Test loops** are sub-second on the host.

Production is a separate concern — see below.

## Production target

- **Database + Auth + Realtime:** managed **Supabase** project (same one you use for dev, or a separate prod project). Migrations apply via `make migrate` against the prod `DATABASE_URL`.
- **Web frontend:** **Cloudflare Pages.** `pnpm build` produces the static `dist/` that ships to the CDN.
- **API:** **VPS-hosted FastAPI** (long-running uvicorn/gunicorn behind Caddy or nginx for TLS). Not Cloudflare Workers, not Fly machines — full VPS so we can run heavy Python libraries (sentence-transformers, Polars, etc.) and long-running background workers without edge-runtime constraints. Will land as `apps/api/Dockerfile` when we ship.
- **Workers (Dramatiq + Prefect, future):** same VPS as the API (or a sibling VPS if scale demands), as separate processes (systemd units or sibling containers).
- **Cache:** self-hosted Valkey on the API VPS.

A future deploy plan covers the API Dockerfile, VPS provisioning, the Pages build pipeline, migration deploy automation, backups, secrets management, and TLS.

## CI/CD

Not in scope yet. Project policy: CI/CD is added once the local development environment runs cleanly end-to-end. Until then, `make check` and the pre-commit hook are the contract.
