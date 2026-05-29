# Xtrusio

Multi-tenant AI SaaS platform — measures how AI assistants (Claude, ChatGPT, Gemini, Grok, Perplexity) perceive your tenants, then closes the gap with targeted content, link placement, and outreach.

Full architectural picture: [`infra.md`](./infra.md).

---

## Prerequisites

- **Node 22** — manage with `mise` (preferred), `fnm`, `nvm`, or `volta` (`.nvmrc` / `mise.toml` pin the version).
- **pnpm 10** — `corepack enable && corepack prepare pnpm@10 --activate`, or via `mise`.
- **Python 3.12** — `uv` will manage the interpreter; install `uv` itself:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Docker Desktop** — only needed if you want a local Redis for arq workers (optional; remote Redis like Upstash works too).
- **Supabase CLI** — used as a _migration tool_ (`supabase db push`), not as a local stack runner:

  ```bash
  brew install supabase/tap/supabase   # macOS
  ```

- **GNU Make** (preinstalled on macOS / Linux).

Optional: install [`mise`](https://mise.jdx.dev) (`brew install mise` on macOS), then `mise install` pins Node, Python, and pnpm in one shot.

---

## First-time setup

There is **no local Supabase stack**. Dev connects directly to a managed Supabase project on supabase.com.

### 1. Create a Supabase project

1. Sign up at [supabase.com](https://supabase.com) and create a new project named `xtrusio-dev` (free or Pro tier).
2. In **Project Settings → API**, copy:
   - Project URL
   - `anon` key
   - `service_role` key
   - JWT secret
3. In **Project Settings → Database → Connection string**, copy the **pooled** URI.

### 2. Configure `.env`

```bash
git clone <repo>
cd xtrusio
cp .env.example .env
# Edit .env and fill in values from step 1.
make install
```

`.env` is gitignored — never commit it.

### 3. Apply schema + bootstrap a platform owner

```bash
make migrate
make create-platform-owner email=you@x.com password='SecurePass123!'
```

Then sign in at http://localhost:5173/sign-in with those credentials.

---

## Daily development

| Command                                | What it does                                                |
| -------------------------------------- | ----------------------------------------------------------- |
| `make dev`                             | API + Web in parallel.                                      |
| `make api`                             | FastAPI dev server on `:8000` (`XTRUSIO_PROCESS_ROLE=api`). |
| `make web`                             | Vite dev server on `:5173`.                                 |
| `make worker`                          | arq worker (needs Redis running).                           |
| `make redis-up`                        | Start local Redis container (optional).                     |
| `make redis-down`                      | Stop local Redis.                                           |
| `make migrate`                         | Apply Alembic migrations to the project in `DATABASE_URL`.  |
| `make migrate-new name=add_some_table` | Create a new migration file.                                |
| `make lint`                            | Ruff + ESLint check.                                        |
| `make format`                          | Auto-format Python + TypeScript.                            |
| `make typecheck`                       | mypy + tsc.                                                 |
| `make test`                            | pytest + Vitest.                                            |
| `make check`                           | lint + typecheck + test (run before committing).            |
| `make clean`                           | Wipe caches and venvs.                                      |

---

## Layout

```
apps/
  api/       FastAPI backend (Python, uv-managed) — bounded contexts as packages
  web/       Vite + React frontend (TypeScript only — no .js anywhere)
packages/
  ui/        Shared UI components
  api-types/ Generated OpenAPI types
supabase/
  migrations/  SQL migrations (applied via `supabase db push` or `make migrate`)
  config.toml  Kept only for migration tool compatibility
docs/
  superpowers/specs/   Design specs
  superpowers/plans/   Implementation plans
infra.md     Full infrastructure + architecture brief
```

---

## URLs

- **Web (Vite):** http://localhost:5173
- **API:** http://localhost:8000
  - Health: `/health`
  - OpenAPI: `/docs`
- **Supabase Studio:** `https://supabase.com/dashboard/project/<ref>` (managed)

---

## Engineering rules

See [`docs/superpowers/ENGINEERING_PRINCIPLES.md`](docs/superpowers/ENGINEERING_PRINCIPLES.md) and [`infra.md`](./infra.md) §21. The big ones:

- **TypeScript only on the frontend.** No `.js` / `.jsx` / `.mjs` / `.cjs`. Source AND configs.
- **No custom CSS** outside `apps/web/src/globals.css`. Every component composes Tailwind utilities + shadcn primitives.
- **No hardcoded colors.** Use semantic tokens (`bg-background`, `text-muted-foreground`, `bg-success/10`, etc.). Pre-commit hook (`no-hardcoded-colors`) blocks `#hex` and `bg-zinc-*` / `bg-gray-*` / etc.
- **No demo or mock data.** Empty states are first-class. First platform owner via CLI; everyone else via real invites.
- **Strict typing.** No `any`, branded IDs, Zod-as-source-of-truth.
- **`mypy --strict`** on Python.
- **500 LoC ceiling per file**, 200–300 target.
- **Pre-commit hooks** enforce ruff, prettier, no-js-in-frontend, no-hardcoded-colors, and large-file checks.
- **Enterprise register.** Hairline borders, B/W palette, no aurora / mesh / decorative color. Every screen ships empty / loading / error / dense-data states on day one.
- **Build one feature end-to-end before the next.** Sequence in `infra.md` §16.

---

## Why dev connects to managed Supabase (not a local stack)

| Reason                | Detail                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Dev↔prod parity       | Same managed product, same RLS behavior, same pgvector behavior, same Auth flows. Zero "works on my machine" surprises. |
| Less local complexity | No `supabase start`, no 8 containers, no port collisions, no waiting.                                                   |
| Real Studio           | Browse data in the actual Supabase dashboard.                                                                           |
| Real email            | Resend (or any custom SMTP) configured in the Supabase Auth dashboard works in dev.                                     |
| Real backups          | PITR + daily backups available even in dev.                                                                             |

Application code (FastAPI, Vite/React, arq workers) runs natively on the host via `uv` and `pnpm`. The only optional local Docker dependency is Redis.

---

## Production target

- **Database + Auth + Storage + Realtime:** managed Supabase (`xtrusio-prod` project).
- **Web frontend:** Cloudflare Pages — connected to GitHub `main`, standard Vite build.
- **API + Workers:** VPS-hosted FastAPI + arq, Docker Compose (`api`, `worker`, `caddy`, `redis`).
- **TLS:** Caddy with built-in ACME / Let's Encrypt.
- **Secrets:** Doppler (or `sops` + age).
- **Transactional email:** Resend, configured as Supabase Auth's custom SMTP.

See [`infra.md`](./infra.md) §14 for the full deployment topology.

---

## CI/CD

GitHub Actions on push to `main`:

1. Lint (ruff, mypy, eslint, tsc) + tests.
2. Build API image, tag `:sha`, push to GHCR.
3. Build web bundle, deploy to Cloudflare Pages preview.
4. Migrations: `supabase db push --db-url $PROD_DB_URL` (gated on tag for prod).
5. On tag `v*`: deploy API to VPS, run `alembic upgrade head`, promote web.
