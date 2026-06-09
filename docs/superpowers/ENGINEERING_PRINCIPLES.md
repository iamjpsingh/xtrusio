# Engineering Principles

Project-wide engineering constraints. These apply to **every** spec, every PR, every file. Reviewers reject changes that violate these without justification.

---

## 1. File size

- **Hard ceiling: 500 lines of code per file** (excluding blank lines, imports, and comments).
- **Target: 200-300 lines.** If a file is approaching 400, plan how to split before it gets there.
- A file that grows past 500 lines is a signal that it has too many responsibilities. Split by responsibility, not by alphabetical order.

**How to split:**

- Routes file too big → split per resource (`tenants/routes.py`, `users/routes.py`).
- Service file too big → split into smaller services with single responsibility (`tenant_create_service.py`, `tenant_update_service.py`) OR extract pure-function helpers to a `helpers/` module.
- Component file too big → split into smaller composable components, lift shared types into `types.ts`.
- Test file too big → mirror the split of the source file.

---

## 2. TypeScript discipline

### 2.0 No JavaScript files anywhere in the frontend stack

**Allowed extensions in `apps/web/`, `packages/ui/`, `packages/api-types/`, and any future frontend package: `.ts` and `.tsx` only.** Forbidden: `.js`, `.jsx`, `.mjs`, `.cjs`. This applies to **source AND config files**.

- ESLint flat config: **`eslint.config.ts`** — load via `jiti` (devDep) so ESLint 9 reads TypeScript natively. Never `eslint.config.js`/`.mjs`.
- Vite config: **`vite.config.ts`** (already the default).
- Vitest config: **`vitest.config.ts`** (already the default).
- Tailwind / PostCSS / Storybook configs (when added): use the `.ts` variant. If a tool *fundamentally* cannot load TypeScript and JS is the only option, raise it for review before introducing any `.js` file — never silently add one.
- Backend (`apps/api/`, future `apps/worker/`) is unaffected — Python uses `.py`.
- Build outputs (`dist/`, `.turbo/`, etc.) are gitignored and don't count.

A grep gate in CI (see .github/workflows/ci.yml) and as a local pre-commit hook fails the build if a `.js`/`.jsx`/`.mjs`/`.cjs` file is staged in any frontend path. **No exceptions without a written deviation in this doc.**

### 2.1 Compiler strictness

- **Strict mode on.** `tsconfig.json` enables `strict: true`, `noUncheckedIndexedAccess: true`.
- **`exactOptionalPropertyTypes` is OFF** (deviation from "fully strict"). Reason: shadcn-ui's prop-spread patterns are fundamentally incompatible with this flag, and we treat shadcn as a vendored library we own but don't fork. Re-enabling means patching every shadcn component on every CLI re-add — not worth the marginal type-safety win. We compensate with `noUncheckedIndexedAccess` + `noImplicitAny` + lint rules forbidding `any`.
- **No `any`.** Ever. If you genuinely need an escape hatch, use `unknown` and narrow it. PRs with `any` are rejected unless an inline comment explains why no type works.
- **No `// @ts-ignore` / `// @ts-expect-error`** without a reason on the same line: `// @ts-expect-error: Supabase types lag SDK v3.x release, see issue #N`.

### 2.2 Type design

- **Branded types for IDs.** `type TenantId = string & { __brand: "TenantId" }`. This prevents passing a `userId` where a `tenantId` is expected — the compiler catches it.
- **Zod schemas are the source of truth.** Infer TS types from Zod (`type X = z.infer<typeof xSchema>`). Don't define a TS interface and a Zod schema separately — they will drift.
- **Prefer `type` over `interface`** for new code, except when you need declaration merging.

---

## 3. Python discipline

- **`mypy --strict` passes.** No `# type: ignore` without a reason comment.
- **Pydantic v2 models for all I/O.** Never accept dicts at API boundaries; coerce to a model immediately.
- **`async def` everywhere except CPU-bound work.** No mixing sync and async DB calls in the same handler.
- **Ruff lint + format** in CI. No exceptions.

---

## 4. Reusable code

- **DRY, but don't over-abstract.** Three repeated lines is fine. The same logic in three different files with subtle drift is not.
- **Shared utilities live in `packages/ui` (frontend) and a `xtrusio_api.shared` module (backend).** Don't reach across feature folders for utilities — promote them.
- **Components in `packages/ui` must be:**
  - Stateless or have explicit, prop-driven state
  - Theme-agnostic (use CSS variables, never hardcoded colors)
  - Tested in isolation with Vitest + RTL
  - Exported with explicit prop types (no `Props` interface inferred from JSX)
- **Backend services accept dependency-injected sessions and clients,** never reach for globals. This makes testing trivial and prevents request-scoping bugs.

---

## 5. Robustness

- **Errors at the boundary, not in the middle.** Validate at the edge (HTTP request, file upload, external API response). Once data is inside the system, trust it.
- **No bare `except`.** Catch specific exceptions; log; re-raise or convert to a domain error.
- **Every external call has a timeout.** httpx clients, LLM SDKs, Supabase clients — none can block indefinitely.
- **Idempotent writes where possible.** Use idempotency keys for any mutation that might be retried (Dramatiq retries, browser double-clicks, network retries).
- **Migrations are reversible.** Every Alembic migration has a working `downgrade()`. PRs without it fail review.
- **Migrations on populated tables follow the lock-safe patterns** in [`migration-style.md`](./migration-style.md) — `CREATE INDEX CONCURRENTLY`, two-step `NOT NULL`, batched backfills, and ordering guards for data-dependent migrations.

---

## 6. Scalability

- **No N+1 queries.** Use `selectinload`/`joinedload` in SQLAlchemy. PRs with detected N+1s fail review (sqlalchemy_n_plus_one detector in tests).
- **Pagination on every list endpoint.** Default `limit=50`, max `limit=200`. Cursor-based for infinite scroll, offset for admin tables.
- **No unbounded queries.** Every list query has a limit, every aggregation has a tenant_id scope.
- **Cache reads, not writes.** Valkey is for derived data. Authoritative state is in Postgres.
- **Async-first.** No blocking I/O on the event loop.

---

## 7. Code quality principles (the short list)

- **Single responsibility per module.** A file does one thing or coordinates one workflow.
- **Pure where possible.** Push side effects (DB writes, HTTP calls) to the edges; keep business logic in pure functions that are trivial to test.
- **Names are honest.** A function called `update_user` updates a user. Not "and also sends an email and logs to audit" — those are separate functions composed by the caller.
- **No comments for what — only for why.** If the code can't be made self-explanatory, add a comment about the *reason* (e.g., a workaround for a bug, a counter-intuitive constraint), not a paraphrase of what the code does.
- **No premature abstraction.** Wait for the third occurrence before extracting a base class or helper.
- **Composition over inheritance.** Class hierarchies more than 2 deep require justification.
- **Fail loudly in dev, gracefully in prod.** `assert` is fine in tests and dev startup; production raises typed exceptions that the global handler converts to clean error responses.

---

## 8. Testing principles

- **Tests are first-class code.** Same lint rules, same naming standards, same review bar.
- **Test behavior, not implementation.** Refactoring should not break tests unless behavior changed.
- **Test the unhappy paths.** Every endpoint has a test for: unauthenticated, unauthorized, validation error, not found, success.
- **Don't mock what you don't own** unless it's slow or expensive. Tests run against either a Postgres test container OR a dedicated managed-Supabase test project (`xtrusio-ci`) — never against dev or prod. Per-run isolation comes from the `_cleanup` fixture purging `@example.com` rows. CI is partitioned (PAR-F F.1): the Supabase-free test subset (`-m "not requires_supabase"`) runs on an **ephemeral Postgres** service with `cancel-in-progress: true`; the Supabase-dependent subset (auth schema, real JWT/JWKS, multi-connection concurrency) runs against the shared `xtrusio-ci` project under `concurrency: ci-test-db` (serialized, never cancelled mid-run). Mock only third-party LLM APIs and email senders.

---

## 8a. Local development runtime

- **Default: managed Supabase.** Dev hits a managed Supabase project directly (Postgres + Auth + Realtime). There is no local Supabase stack — `supabase start` is not used. The only optional local container is Valkey (`make db-up`).
- **Opt-in: local Postgres.** Contributors who can't or won't provision a Supabase project can run a throwaway Postgres locally via the `local` Compose **profile** (`make dev-local`, i.e. `docker compose --profile local up -d postgres-local`) — defined in the single `docker-compose.yml` alongside Valkey, so all local infra groups under the one `xtrusio` Compose project. This brings up a `postgres:16`-compatible (pgvector) container on a published port and is intended for running migrations and the Supabase-free test subset (`uv run pytest apps/api/tests -m "not requires_supabase"`). It does **not** provide Supabase's `auth`/GoTrue, real JWT/JWKS, or Realtime — the Supabase-dependent tests and the full auth flow still require a managed project. The managed-Supabase path remains the supported default; local Postgres is a convenience, not a parallel supported runtime.

---

## 9. Reviewing PRs against these

A PR fails review if:
- Any file exceeds 500 LoC
- **Any frontend path contains a `.js`/`.jsx`/`.mjs`/`.cjs` file** (section 2.0)
- Any new TS file uses `any` without a justification comment
- Any new endpoint is missing pagination, error tests, or auth tests
- Any new tenant-scoped table is missing RLS policies + RLS tests
- Any new external call lacks a timeout
- Any new migration is missing a working `downgrade()`
- Coverage of new code is under 80%

Reviewers cite the specific clause when blocking ("section 1: file is 612 LoC, please split").
