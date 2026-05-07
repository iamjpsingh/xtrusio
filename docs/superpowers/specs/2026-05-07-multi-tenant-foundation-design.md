# Multi-Tenant Foundation — Design Spec

**Project:** Xtrusio AI SaaS Platform
**Spec ID:** 2026-05-07-multi-tenant-foundation
**Status:** Draft (pending user review)
**Scope:** Subsystem #1 of N — the platform foundation that all subsequent features build on top of.

---

## 1. Overview

Xtrusio is a multi-tenant AI SaaS platform. The platform team onboards "client" companies (tenants) and configures each tenant's enabled features, prompts, theme, and LLM routing. All tenants share the same codebase; per-tenant configuration drives what each tenant sees and what their AI orchestration does.

This spec defines the **foundation** only: tenancy model, authentication, authorization, data isolation, observability, and the minimum admin UIs to onboard tenants and users. It explicitly does **not** include the prompt orchestration engine, client-facing features, full notification system, or Prefect workflow architecture — each of those is a separate downstream spec.

### 1.1 Goals

- A platform team can create a new client tenant, configure its features and theme, and invite the first owner — all from a platform admin UI.
- A tenant owner can invite/manage their own users and roles inside their tenant.
- A user can log in and is automatically routed to their correct portal (`/platform/...` or `/clients/<slug>/...`) based on their identity.
- Tenant data is provably isolated: tenant A's users cannot read or mutate tenant B's data, even with crafted requests. RLS is enforced at the database layer and verified by an automated test suite.
- Platform users can impersonate any tenant role for support, with every action recorded in a platform-only audit log invisible to the tenant.
- All user-facing actions are logged to a per-tenant activity feed; all worker jobs are logged to a worker log; all platform/audit events are logged separately.
- Per-tenant theme (colors, logo) is applied automatically via tenant config.

### 1.2 Non-goals (deferred to later specs)

- Prompt configuration UI and prompt orchestration engine (spec #2).
- LLM provider routing logic (spec #2).
- Full notification system: in-app inbox, real-time push, email digests beyond invite emails (spec #3).
- Prefect long-workflow integration beyond a stub (spec #4).
- Client-facing application features — what the app actually *does* for end users (spec #5+).
- Custom domains (`app.acme.com` CNAME).
- OAuth (Google/Microsoft) and SAML SSO providers.
- Billing, plan management, usage metering.
- pg_cron scheduled jobs beyond a placeholder.

---

## 2. Architecture overview

### 2.1 Repo strategy

Single git repository. Monorepo managed by **Turborepo + pnpm workspaces** for JavaScript and **uv workspaces** for Python.

```
xtrusio/
├── apps/
│   ├── api/              # FastAPI backend + Dramatiq workers
│   └── web/              # React 19 + Vite + TanStack frontend (single app)
├── packages/
│   ├── api-types/        # OpenAPI-generated TypeScript types (auto-generated)
│   ├── ui/               # Shared shadcn/Radix components
│   └── config/           # Shared eslint, tailwind, tsconfig presets
├── infra/
│   ├── supabase/         # supabase config, migrations, RLS policies
│   └── docker/           # Dockerfiles, docker-compose.yml for local dev
├── .github/workflows/    # CI: lint, type-check, test, build
├── turbo.json
├── pnpm-workspace.yaml
└── pyproject.toml        # uv root
```

**Why monorepo:** atomic changes that span schema → backend → frontend, OpenAPI types stay synchronized via codegen, shared UI components between platform and tenant routes, single CI pipeline.

### 2.2 Deployment topology

- **Frontend (`apps/web`)** — built by Vite, deployed as a static SPA (Cloudflare Pages or Vercel). Single deploy serves both `/platform/*` and `/clients/<slug>/*` routes.
- **Backend (`apps/api`)** — FastAPI ASGI app run by Uvicorn behind Gunicorn. Deployed as a container (Cloudflare Containers, Fly.io, or Railway for MVP).
- **Workers** — Same Docker image as `apps/api`, started with a different entrypoint (`dramatiq apps.api.workers`). Pulls jobs from Valkey.
- **Database** — Single Supabase project (Postgres 16 + pgvector + GoTrue + Realtime).
- **Cache / queue / locks** — Valkey instance (managed or self-hosted).
- **Object storage** — Cloudflare R2 (S3-compatible) accessed via boto3.

### 2.3 Request flow (one round trip)

1. Browser issues request to `app.xtrusio.com/clients/acme/dashboard`.
2. SPA hydrates, reads JWT from secure cookie / localStorage, calls FastAPI.
3. FastAPI middleware chain (in order):
   - **JWT validation** — verify signature using Supabase JWKS via `python-jose`. Reject if invalid/expired.
   - **Tenant resolution** — extract tenant slug from request path. Look up `tenant_id` from `tenants` table (cached in Valkey).
   - **Tenant claim match** — assert URL slug matches JWT's `tenant_slug` claim (or, if the JWT marks `is_platform_user=true`, allow access and set `impersonating=true` flag for audit).
   - **Postgres session vars** — set `app.current_tenant_id`, `app.current_user_id`, `app.is_platform_user`, `app.is_impersonating` for RLS.
   - **Permission check** — route handler decorator validates `user has permission X`.
4. Handler runs business logic; SQL queries automatically RLS-scoped.
5. After response, **activity log middleware** records the action to the appropriate log (tenant activity, platform audit, or both for impersonation).

---

## 3. Identity model

### 3.1 Three kinds of identities

| Identity | Created by | Belongs to | Effective session context |
|---|---|---|---|
| **Tenant user** | Tenant admin/owner, or platform | Exactly one tenant, forever | `{ user_id, tenant_id, tenant_slug, role, permissions[], is_platform_user: false }` |
| **Platform user** | Existing platform super_admin | No tenant; the platform itself | `{ user_id, platform_role, permissions[], is_platform_user: true }` |
| **Platform user impersonating a tenant** | Platform user clicks "Enter Tenant" | Same platform user, scoped to a tenant | `{ user_id, tenant_id, tenant_slug, mimic_role, permissions[], is_platform_user: true, is_impersonating: true, impersonation_session_id }` |

The "effective session context" is what the FastAPI request handler operates with after middleware enrichment (see §5.4). The raw Supabase JWT only carries `user_id` and standard claims; everything else is computed per request from the database.

Tenant users and platform users are stored in the same `users` table but distinguished by the `is_platform_user` boolean.

For impersonation specifically: the *raw* JWT is unchanged (still the platform user's Supabase token). The "switch" is a server-side state change — the active `impersonation_sessions` row tells the middleware to enrich the context as the mimicked role. Exiting impersonation marks `ended_at` and reverts to the normal platform context.

### 3.2 Roles

**Platform roles** (single role per platform user):
- `super_admin` — full platform control, the only role that can read the platform audit log, the only role that can create/delete platform users
- `admin` — can impersonate, can manage tenants, cannot manage other platform users
- `editor` — platform-only operations (e.g., editing prompt templates in the catalog), cannot impersonate

**Tenant roles** (one role per tenant_membership):
- `owner` — full tenant control, can manage billing, cannot be removed by other tenant users
- `admin` — manage users + settings inside the tenant
- `editor` — work in the app, cannot manage users
- `read_only` — view-only

Roles map to **permission strings** via the `role_permissions` table (see §6.2 and §10).

---

## 4. URL & routing

### 4.1 URL structure

```
app.xtrusio.com/                       → redirect to /login (no marketing site in scope)
app.xtrusio.com/login                  → email + password / magic link
app.xtrusio.com/auth/callback          → magic link / invite landing
app.xtrusio.com/platform/              → platform team home (requires platform_role)
app.xtrusio.com/platform/clients       → list/create/manage clients
app.xtrusio.com/platform/clients/:slug → manage one client (admin view of their config)
app.xtrusio.com/platform/audit         → platform audit log (super_admin only)
app.xtrusio.com/platform/users         → platform team users (super_admin only)
app.xtrusio.com/clients/:slug/         → tenant home/dashboard
app.xtrusio.com/clients/:slug/users    → tenant user management (tenant admin/owner)
app.xtrusio.com/clients/:slug/activity → tenant activity log
app.xtrusio.com/clients/:slug/settings → tenant settings (theme, etc.)
```

### 4.2 Route guards

- `/platform/*` requires `is_platform_user=true` AND not impersonating. If impersonating, redirected to `/clients/<slug>/...` with the impersonation banner suppressed (per spec — invisible to tenant).
- `/clients/:slug/*` requires either: (a) tenant user whose JWT `tenant_slug === :slug`, OR (b) platform user with active impersonation matching that slug.
- Mismatch between URL slug and JWT → 403 from middleware, frontend redirects to user's correct landing path.

### 4.3 Reserved slug words

The following slugs are reserved and cannot be used as tenant slugs: `platform`, `login`, `signup`, `auth`, `api`, `static`, `assets`, `health`, `_status`, `admin`, `system`. Validation enforced at tenant creation.

---

## 5. Authentication

### 5.1 Mechanism (MVP)

- **Email + password** (Supabase GoTrue default)
- **Magic link** (Supabase native, enabled via config flag)
- **MFA (TOTP)** — mandatory for platform users (enforced by login flow blocking access until enrolled), optional for tenant users (tenant admin can require it per-tenant in v1.1)

### 5.2 Tenant creation flow

1. Platform user (admin or super_admin) opens `/platform/clients` → "Create Client".
2. Form fields: `name`, `slug` (validated against reserved list + uniqueness), `theme_config` JSON, `logo_upload`, `enabled_features[]` (multi-select from features catalog).
3. On submit: create `tenants` row, create features assignments, upload logo to R2.
4. Form prompts for "Owner email". On confirm: create `users` row (tenant user, password=null, must_set_password=true), create `tenant_memberships` row with role=owner, send invite email via Dramatiq.

### 5.3 Invite → set password flow

1. User clicks invite link in email: `app.xtrusio.com/auth/callback?token=<single-use-jwt>`.
2. Token validates → frontend shows "Set your password" form (also: name confirmation, MFA enrollment if platform user).
3. On submit, calls Supabase to set password, issues full session JWT, redirects to user's landing path.

### 5.4 Login flow

1. User visits `/login` → enters email + password (or requests magic link).
2. Supabase GoTrue authenticates; issues JWT.
3. **Session token strategy:** the frontend uses Supabase's GoTrue JWT directly for authentication (sent as `Authorization: Bearer <token>`). On every request, FastAPI middleware validates the token, then enriches the request context by joining the `users`, `tenant_memberships`, `roles`, and `role_permissions` tables to produce the full session payload (tenant_id, tenant_slug, role, permissions[], features[]). This payload is also returned by `/auth/me` for the frontend to cache. We do **not** mint a custom backend JWT in spec #1 — Supabase JWT + per-request DB enrichment is simpler and the enrichment query is fast (<5ms with proper indexes; Valkey-cached for 60s keyed by user_id). Custom JWT minting is an option if performance demands it later.
4. Frontend redirects:
   - `is_platform_user=true` → `/platform/`
   - else → `/clients/<tenant_slug>/`

### 5.5 Tenant user creation by tenant admin

1. Tenant admin opens `/clients/<slug>/users` → "Invite User".
2. Form: email, role (admin/editor/read_only — owner cannot be created by admin).
3. On submit: create `users` row scoped to this tenant, create `tenant_memberships`, send invite email. Identical flow to §5.3 from there.

---

## 6. Authorization

### 6.1 Two-layer authorization

- **Layer 1 — Postgres RLS:** every tenant-scoped table has RLS policies that read `current_setting('app.current_tenant_id')`. This is the *primary* defense — no SQL query, anywhere, can return cross-tenant data.
- **Layer 2 — Application-level permission checks:** FastAPI route decorators check `user has permission X` for fine-grained gates (e.g., `editor` cannot invite users even though their tenant_id matches).

Both layers run on every request. Either alone is insufficient; together they are defense-in-depth.

### 6.2 Permissions data model

```
roles                    role_permissions               permissions
─────                    ────────────────               ───────────
id, scope, name          role_id, permission_id         id, key, description
                                                        e.g., "users.invite",
                                                              "prompts.read",
                                                              "audit.read"
```

`scope` distinguishes platform roles from tenant roles. Permissions are seeded on app startup; new permission strings are added by writing migrations and updating role mappings.

Frontend reads `permissions[]` from `/auth/me` and renders gated UI:

```tsx
<Can permission="users.invite">
  <Button>Invite User</Button>
</Can>
```

Backend enforces with FastAPI dependency:

```python
@router.post("/users/invite")
async def invite_user(_=Depends(require_permission("users.invite")), ...):
    ...
```

### 6.3 RLS strategy

Every tenant-scoped table has the following two policies:

```sql
-- Read policy
CREATE POLICY tenant_isolation_read ON <table>
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Write policy
CREATE POLICY tenant_isolation_write ON <table>
  FOR ALL
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

Platform users in non-impersonation mode bypass tenant scoping by setting `app.current_tenant_id = NULL` and using a separate `platform_bypass` policy that checks `current_setting('app.is_platform_user')::boolean = true`.

### 6.4 Mandatory RLS test suite

A pytest module that, for *every* tenant-scoped table, asserts:
1. Tenant A query returns only tenant A rows.
2. Tenant A query for a tenant B row by ID returns 0 rows.
3. Tenant A insert with `tenant_id = B` is rejected.
4. Tenant A update of a tenant B row is rejected.
5. Platform user with `app.current_tenant_id = NULL` can read across tenants.

CI fails if any new table is added without corresponding RLS tests (enforced by a linter that checks coverage).

---

## 7. Impersonation & platform audit

### 7.1 Who can impersonate

`super_admin` and `admin` platform roles only. `editor` cannot impersonate.

### 7.2 Flow

1. Platform user (admin+) opens `/platform/clients/<slug>` → "Enter Tenant" → modal asks: which role to mimic? (admin/editor/read_only/specific user) + reason field (free text, required).
2. Backend creates an active `impersonation_sessions` row with: platform_user_id, target_tenant_id, mimic_role, reason, started_at, ended_at=null. At most one active session per platform user (enforced by partial unique index on `WHERE ended_at IS NULL`).
3. The session enrichment middleware now sees the active row and produces the impersonation context for every subsequent request from that user — no JWT swap needed.
4. Frontend calls `/auth/me`, sees `is_impersonating=true` and `tenant_slug=<target>`, redirects to `/clients/<slug>/`. UI renders identically to how the mimicked role would see it. **No banner, no indicator** — invisible to tenant per requirement.
5. Platform user clicks "Exit Tenant" (visible only in their platform user menu) → backend marks session `ended_at=now()`, redirects to `/platform/`. Subsequent requests fall back to normal platform context.

### 7.3 What's allowed during impersonation

- All read operations the mimicked role can do.
- All non-destructive writes the mimicked role can do.
- **Blocked:** destructive actions — delete tenant, delete user, hard-delete data, change billing, change tenant slug. These actions return 403 with `error.code=DESTRUCTIVE_ACTION_DURING_IMPERSONATION` and must be performed from `/platform/...` UI explicitly.

### 7.4 Audit logging during impersonation

Every request during impersonation writes to `platform_audit_log`:
- impersonation_session_id, platform_user_id, target_tenant_id, mimic_role
- HTTP method, path, request_body_summary (PII-redacted)
- DB mutations (table, row_id, diff before→after)
- timestamp

Critically: these requests **do NOT write to `tenant_activity_log`**. The tenant sees nothing.

### 7.5 Visibility of audit log

- `super_admin`: read access to all of `platform_audit_log`
- `admin`: read access to their own impersonation sessions only
- `editor`: no access
- All tenant users: no access (table excluded from any RLS that tenants can hit)

---

## 8. Feature flags & tenant config

### 8.1 Data model

**`features` (catalog table)** — defines what features exist:
```
id          uuid pk
key         text unique  -- e.g., "vector_search", "exports", "prompts_v2"
name        text         -- display name
description text
category    text         -- "ai", "data", "ui", "integrations"
default_enabled bool
created_at  timestamptz
```

**`tenants.features` (JSONB column)** — per-tenant flag values:
```json
{
  "vector_search": true,
  "exports": false,
  "prompts_v2": true
}
```

### 8.2 Evaluation

- On login, backend reads `tenants.features` and merges with `features` catalog defaults to produce `effective_features[]`.
- `/auth/me` returns `effective_features[]` to frontend.
- Backend route decorator `require_feature("vector_search")` checks the same.

Adding a new feature: write migration to INSERT into `features`, then platform admin can enable/disable per tenant via UI without code changes.

### 8.3 Tenant config (theme, logo, branding)

Stored on `tenants` row:
- `theme_config` JSONB — `{"primary_color": "#...", "accent_color": "#...", "font_family": "..."}`
- `logo_url` text — Cloudflare R2 URL
- `display_name` text

Frontend reads these from `/auth/me` payload on login and applies them via:
- CSS variables injected at React root for theme colors
- `<img src={logoUrl}>` in the app shell
- Page title uses `display_name`

---

## 9. Logging & observability

Three separate Postgres tables, three separate use cases.

### 9.1 `tenant_activity_log`

User-facing activity inside a tenant. Visible to that tenant's `admin`/`owner` UI.

```
id              uuid pk
tenant_id       uuid fk → tenants
actor_user_id   uuid fk → users  (the tenant user who did this; NULL for system)
action          text             -- "user.invited", "settings.updated", etc.
resource_type   text             -- "user", "settings", "document"
resource_id     uuid
metadata        jsonb            -- action-specific details (PII-redacted)
created_at      timestamptz
```

- Written by service-layer hooks (not middleware) so the action context is rich.
- **Excludes** any action where `is_impersonating=true` — those go to platform_audit_log.
- RLS: tenant users can read only their tenant's rows. Tenant `admin`/`owner` can view; `editor`/`read_only` cannot.
- Retention: 90 days, then archived to R2.

### 9.2 `platform_audit_log`

Platform team's accountability log. **Only `super_admin` can read** (and `admin` for their own actions). Note: this table is excluded from the generic `platform_bypass` RLS policy described in §6.3 — it has its own restrictive policy that checks `current_setting('app.platform_role')` is `super_admin`, OR the row's `platform_user_id` matches the current user when their role is `admin`. No tenant user has any access to this table at the RLS level.

```
id                       uuid pk
platform_user_id         uuid fk → users
event_type               text   -- "platform.login", "impersonation.start",
                                --  "impersonation.action", "tenant.created", etc.
target_tenant_id         uuid   -- nullable (e.g., login event has no tenant)
impersonation_session_id uuid   -- nullable; populated for impersonation events
mimic_role               text   -- nullable
http_method              text
http_path                text
request_summary          jsonb  -- PII-redacted
db_diff                  jsonb  -- before→after for mutations
ip_address               inet
user_agent               text
reason                   text   -- from impersonation modal
created_at               timestamptz
```

- Written by middleware (uniformly captures everything).
- RLS: super_admin sees all; admin sees only `platform_user_id = current_user_id`; everyone else: no access.
- Retention: 7 years (compliance baseline).

### 9.3 `worker_log`

Dramatiq + Prefect job execution traces.

```
id                uuid pk
job_id            text          -- Dramatiq message id
job_kind          text          -- "send_invite_email", "import_csv", etc.
tenant_id         uuid          -- nullable for system jobs
queue             text
status            text          -- "queued", "running", "succeeded", "failed", "retrying"
attempt           int
started_at        timestamptz
finished_at       timestamptz
error_class       text
error_message     text
payload_summary   jsonb         -- PII-redacted args
created_at        timestamptz
```

- Written by Dramatiq middleware hooks.
- RLS: tenant users see jobs scoped to their tenant_id; platform users see all.
- Retention: 30 days.

### 9.4 Sentry (separate from DB logs)

Application errors, stack traces, performance traces sent to Sentry via `sentry-sdk`. DB logs are for *what happened*; Sentry is for *what broke*.

---

## 10. Data model — tables in spec #1

```
-- IDENTITY
tenants(id, slug, name, display_name, theme_config jsonb, logo_url, features jsonb, status, created_at, updated_at)
users(id, email, password_hash, name, is_platform_user bool, must_set_password bool, mfa_enabled bool, mfa_secret, last_login_at, created_at)
tenant_memberships(id, tenant_id, user_id, role, status, invited_at, joined_at)
                  -- UNIQUE(tenant_id, user_id), FK to roles.id

-- AUTHORIZATION
roles(id, scope, name)                                 -- scope: 'platform' | 'tenant'
permissions(id, key, description)
role_permissions(role_id, permission_id)               -- many-to-many

-- FEATURES
features(id, key, name, description, category, default_enabled, created_at)

-- IMPERSONATION
impersonation_sessions(id, platform_user_id, target_tenant_id, mimic_role, reason, started_at, ended_at, ip_address, user_agent)

-- LOGS (see §9 for full columns)
tenant_activity_log(...)
platform_audit_log(...)
worker_log(...)

-- AUTH HELPERS
invite_tokens(id, user_id, token_hash, expires_at, used_at)
```

All tables have `created_at` and `updated_at timestamptz NOT NULL DEFAULT now()`. Updated_at maintained by Postgres trigger.

Indexes:
- `tenants(slug)` UNIQUE
- `users(email)` UNIQUE (case-insensitive via citext)
- `tenant_memberships(tenant_id, user_id)` UNIQUE
- `tenant_activity_log(tenant_id, created_at DESC)`
- `platform_audit_log(platform_user_id, created_at DESC)` and `(target_tenant_id, created_at DESC)`
- `worker_log(tenant_id, created_at DESC)` and `(status, created_at DESC)`

---

## 11. Frontend architecture

### 11.1 Routing (TanStack Router)

File-based or code-based routes. Top level:

```
/_layout
  /login
  /auth/callback
  /platform/_layout            (requires is_platform_user)
    /                          (dashboard)
    /clients
    /clients/:slug
    /clients/:slug/audit
    /audit                     (super_admin only)
    /users                     (super_admin only)
  /clients/:slug/_layout       (requires tenant match OR impersonation)
    /                          (tenant dashboard)
    /users                     (admin/owner)
    /activity
    /settings
```

Layout routes apply theme, logo, and the route guards (TanStack `beforeLoad` checks).

### 11.2 State & data

- **Server state:** TanStack Query for all backend calls. Mutations invalidate by query key.
- **Auth state:** Zustand store holds the current session payload (user, tenant, role, permissions, features, theme). Hydrated on app boot from `/auth/me`.
- **Forms:** React Hook Form + Zod schemas. For spec #1, Zod schemas are **hand-written** in `packages/api-types/src/schemas/` and kept in sync with Pydantic models manually (small surface area in spec #1 makes this practical). Auto-generation from Pydantic via a script is a follow-up — tracked as a v1.1 chore, not blocking spec #1.
- **Tables:** TanStack Table v8 for all admin lists.

### 11.3 Shared UI

`packages/ui` exports shadcn-based components customized to the project's design tokens. Both `/platform/*` and `/clients/<slug>/*` consume them. Theming via CSS variables means the same components render in tenant brand colors automatically.

### 11.4 OpenAPI codegen

CI step: `apps/api` exports `/openapi.json` → `openapi-typescript` generates types into `packages/api-types/src/api.d.ts`. Frontend imports types directly. Type drift between backend and frontend fails CI.

---

## 12. Backend architecture

### 12.1 FastAPI app layout

```
apps/api/
├── pyproject.toml
├── src/xtrusio_api/
│   ├── main.py                  # FastAPI app factory
│   ├── config.py                # pydantic-settings
│   ├── db/
│   │   ├── session.py           # SQLAlchemy 2.0 async engine
│   │   └── models/              # ORM models per domain
│   ├── auth/
│   │   ├── jwt.py               # python-jose + Supabase JWKS
│   │   ├── middleware.py        # JWT + tenant resolution + RLS session vars
│   │   ├── permissions.py       # require_permission decorator
│   │   └── service.py           # login, invite, mfa
│   ├── tenants/
│   │   ├── routes.py
│   │   └── service.py
│   ├── users/
│   │   ├── routes.py
│   │   └── service.py
│   ├── impersonation/
│   │   ├── routes.py
│   │   └── service.py
│   ├── features/
│   │   ├── routes.py
│   │   └── service.py
│   ├── logging/
│   │   ├── activity.py          # tenant_activity_log writer
│   │   ├── audit.py             # platform_audit_log writer
│   │   └── worker.py            # worker_log writer
│   └── workers/
│       ├── __init__.py
│       └── tasks/               # Dramatiq actors
│           ├── email.py         # send invite, send notification
│           └── log_archive.py   # 90-day archival
├── alembic/
│   └── versions/
└── tests/
    ├── unit/
    ├── integration/
    └── rls/                     # RLS test suite
```

### 12.2 Middleware order

```
1. CORS
2. Sentry capture
3. Request ID + structured logging
4. JWT validation
5. Tenant resolution (slug + JWT match)
6. RLS session var setter (sets current_tenant_id, etc.)
7. Activity log capture (post-response)
```

### 12.3 Workers

Dramatiq actors live in `apps/api/src/xtrusio_api/workers/tasks/`. Same Python package as the API; same DB session abstractions; same models. Worker process started via `dramatiq xtrusio_api.workers`. Valkey is the broker.

MVP actors:
- `send_invite_email(user_id)` — generates token, renders email, sends via SMTP/SES.
- `archive_activity_log(cutoff_date)` — moves rows older than 90 days to R2 as Parquet.

---

## 13. Testing strategy

| Test type | Framework | What it covers |
|---|---|---|
| Backend unit | pytest + hypothesis | Pure functions, services |
| Backend integration | pytest + testcontainers (Postgres) | Routes hitting real DB |
| **RLS** | pytest, custom harness | Cross-tenant isolation for every table |
| Frontend unit | Vitest | Hooks, utilities, Zod schemas |
| Frontend component | Vitest + React Testing Library | Components in isolation |
| E2E | Playwright | Login flow, invite flow, impersonation flow, role-based UI gating |

CI gates: all tests must pass; RLS coverage linter must pass; type check must pass; lint must pass.

---

## 14. CI/CD (GitHub Actions)

Workflows:
- `on: pull_request` — lint (ruff, eslint, prettier), type-check (mypy, tsc), unit + integration tests, RLS suite, build frontend, build backend image. All must pass to merge.
- `on: push to main` — same as above + deploy preview.
- `on: tag v*` — production deploy.

Turborepo cache is restored across runs (Cloudflare R2 cache backend).

---

## 15. Local development

`docker-compose.yml` brings up: Postgres 16 + pgvector, Valkey, Supabase Studio (optional), MinIO (R2 stand-in for local). One-shot `make dev` script: starts containers, runs migrations, seeds dev data (1 platform super_admin, 2 example tenants with sample users), starts `apps/api` and `apps/web` dev servers in parallel.

`*.localhost` dev URLs (browser-native) eliminate `/etc/hosts` editing if needed in future, though spec #1 uses path-based URLs so this is moot.

---

## 16. Open questions for follow-up specs

These are flagged as decisions deferred, *not* missed:

1. **Prompt orchestration engine** — table design for prompts, versioning, A/B testing, model routing. Spec #2.
2. **Notification system** — in-app inbox table, real-time push via Supabase Realtime, email digest workers, user notification preferences. Spec #3.
3. **Prefect integration** — when do we use Prefect over Dramatiq? Long-running flows with retries vs short jobs. Spec #4.
4. **Custom domains** — when first enterprise asks. Probably Cloudflare for SaaS or per-tenant CNAME validation.
5. **OAuth / SAML SSO** — Supabase supports both; UI work + per-provider configuration table.
6. **Billing & usage metering** — Stripe integration, usage events, plan limits.
7. **Data residency** — if a regulated tenant requires their data in EU/specific region, escape hatch is dedicated Supabase project per such tenant. Architecture supports this since tenant config can include a connection string override (out of scope for spec #1).

---

## 17. Success criteria (acceptance)

Spec #1 is complete when:

1. A platform super_admin can log in at `/login`, land on `/platform/`, create a new client, configure features and theme, and invite the first owner — without writing any code.
2. The owner receives an email, clicks the link, sets a password, lands on `/clients/<slug>/`, sees the configured theme/logo, and only the enabled features.
3. The owner invites an editor; the editor logs in and cannot see admin-only features.
4. A platform admin clicks "Enter Tenant", chooses to mimic owner, lands on `/clients/<slug>/`, can perform owner actions, and the tenant sees nothing in their activity log. The platform audit log shows the impersonation with full diffs.
5. Tenant A user attempting any cross-tenant access (URL tampering, API request with crafted tenant_id) gets 403 or 0 rows.
6. RLS test suite passes for every tenant-scoped table.
7. CI is green: lint, type-check, all test suites, build, RLS coverage lint.
8. Local `make dev` brings the entire stack up in under 90 seconds.

---

## 18. Estimated scope

3-5 weeks for one or two engineers working full-time. Risks: RLS policy edge cases (mitigated by test suite), Supabase JWT customization for adding tenant claims (well-documented but the first time always takes longer), invite email deliverability setup.
