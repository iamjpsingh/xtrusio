# Platform Settings, Self-Serve Signup, and Invites — Design Spec

**Project:** Xtrusio AI SaaS Platform
**Spec ID:** 2026-05-14-platform-settings-signup-and-invites
**Status:** Draft (pending user review)
**Builds on:** Plan 1B (auth + super_admin login MVP — done)
**Scope:** Two related capabilities — (1) runtime-toggled self-serve signup creating tenant owners, (2) email-based invites for both platform users (by super_admin) and tenant users (by owner/admin).

---

## 1. Overview

Plan 1B shipped a hardcoded-policy auth scaffold: signups disabled, email confirmation off, only a CLI-bootstrapped super_admin could log in. This spec moves the policy out of config and into the database: the super_admin toggles signup at runtime from a Settings UI, and the system gains two real flows — public self-serve signup (creates new tenants) and email invites (platform and tenant scoped).

### 1.1 Goals

- The super_admin can toggle "self-serve signup enabled" from the platform Settings UI; the change takes effect immediately.
- When signup is enabled, any visitor can sign up at `/sign-up` with email + password, confirm via email, complete an `/onboarding` step (workspace name), and land in their newly-created tenant as its owner.
- The super_admin can invite other platform users (admin, editor) from `/users`; the invitee receives an email, sets a password, and joins as a platform user.
- A tenant owner or admin can invite users into their tenant (admin, editor, read_only) from `/clients/$slug/users`; same email-driven mechanism, scoped to the tenant.
- Database constraints + RLS enforce the policy as defense-in-depth so API bugs cannot create invalid state.
- All tests for new endpoints and RLS policies pass under `make check`.

### 1.2 Non-goals (deferred to later specs)

- Custom domain setup (`app.xtrusio.com`). Default Supabase URLs + Vite localhost for now; production URLs added when domain is set up.
- Multi-tenant URL routing under `/clients/$slug/*` beyond the single `/users` page. The full tenant URL space is the multi-tenant foundation spec.
- Per-tenant feature flags, plan management, billing.
- Audit log / impersonation (multi-tenant foundation spec).
- Ownership transfer between users in a tenant.
- Custom email templates with Xtrusio branding (uses Supabase defaults).
- Rate limiting beyond Supabase's built-in auth limits.
- Orphan cleanup job for confirmed-but-never-onboarded auth users (flagged as a follow-up).
- Real-time Realtime subscriptions (later spec).
- Tenant role granularity beyond what's required for invites; the four-role enum exists but `admin`/`editor`/`read_only` get no special UI permissions yet beyond invite rules.

---

## 2. Architecture overview

### 2.1 Three identity flows

| Flow | Created via | First action |
|---|---|---|
| **First super_admin** | `make create-platform-owner` CLI (Plan 1B) | Sign in at `/sign-in` |
| **Additional platform user** (admin / editor) | super_admin invites from `/users` → Supabase email → `/accept-invite` | Sign in, manage platform |
| **Tenant user** | Self-serve `/sign-up` (signups must be enabled) **OR** invite from `/clients/$slug/users` | Sign in to their tenant |

Self-serve signup always produces a tenant **owner**. Tenant **admin / editor / read_only** rows only exist via invite. Platform users are never created by self-serve.

### 2.2 Application-gated signup

The `signups_enabled` flag is a row in our `platform_settings` table. The `POST /signup` endpoint reads this flag before calling Supabase. Supabase project-level signup stays **on**; the gate is in our code. This gives:

- Instant toggle (no Supabase Management API push)
- No Supabase PAT in env
- Room to extend the gate with per-domain blocklist, rate limits, captcha later
- Single source of truth in our DB (super_admin sees what they set)

Trade-off: if anyone calls `supabase.auth.signUp()` directly from a browser/script, they bypass the gate and create an unconfirmed Supabase auth user. Mitigation: the frontend never imports `signUp` — it only calls `/signup` (our API). A nightly cleanup job (out of scope) sweeps orphans.

### 2.3 Invites use `auth.admin.invite_user_by_email`

For both platform and tenant invites, our API:

1. Inserts a row into `platform_invites` or `tenant_invites` (our record of intent).
2. Calls `supabase.auth.admin.invite_user_by_email(email, data={...invite_id, role, tenant_id?})`. Supabase creates an unconfirmed auth user and sends a real email with a magic link.
3. The invitee clicks → Supabase confirms the email + opens a set-password page → returns to `/accept-invite` with a session.
4. The frontend calls `POST /invites/accept`. The API reads `user_metadata` from the JWT, validates the invite row, and inserts the matching `platform_users` or `tenant_memberships` row.

The Supabase invite link is the bearer secret; we don't store or generate tokens.

### 2.4 Request flow — self-serve signup

```
1. Visitor opens /sign-up.
   GET /platform/signup-status (public)
   ├─ signups_enabled=false → render "Signups disabled" message
   └─ true → render email + password form

2. Visitor submits.
   POST /signup {email, password} (public)
   ├─ re-check platform_settings.signups_enabled (race-safe)
   ├─ false → 403 signups_disabled
   └─ true → supabase.auth.admin.create_user(email, password, email_confirm=false)
            → Supabase sends confirmation email
            → 202 {state: "confirm_email_sent"}

3. Visitor clicks email link → Supabase confirms → redirect to app with session.

4. AuthGuard fetches GET /me:
   {platform: null, tenants: [], pending_invite: null}
   → redirect to /onboarding

5. POST /onboarding/tenants {workspace_name}
   ├─ slugify + uniqueness check (collisions get -2, -3, …)
   ├─ INSERT tenants (..., created_by=auth.uid())
   ├─ INSERT tenant_memberships (tenant_id, user_id=auth.uid(), role='owner')
   └─ 201 {tenant: {id, slug, name, role: "owner"}}

6. Frontend invalidates /me → AuthGuard re-routes → / (tenant UI).
```

### 2.5 Request flow — invite (platform OR tenant, same shape)

```
1. Authorized inviter submits invite form.
   POST /platform/users/invites OR POST /tenants/{id}/invites

2. API:
   ├─ authorize (super_admin / tenant owner / tenant admin per rules)
   ├─ check email isn't already a member or pending invite
   ├─ INSERT platform_invites or tenant_invites (expires_at = now() + 7d)
   ├─ supabase.auth.admin.invite_user_by_email(
   │    email,
   │    data={
   │      platform_invite_id OR tenant_invite_id,
   │      tenant_id (tenant only),
   │      role
   │    },
   │    redirect_to=/accept-invite
   │  )
   └─ 201 {invite: {...}}

3. Invitee clicks email → Supabase confirms + set-password → /accept-invite with session.

4. Frontend on /accept-invite mount:
   POST /invites/accept (authenticated)
   ├─ extract platform_invite_id or tenant_invite_id from user_metadata claim
   ├─ validate invite row: not revoked, not expired, not accepted, email matches
   ├─ INSERT platform_users OR tenant_memberships (atomic with invite UPDATE)
   ├─ UPDATE invite SET accepted_at = now()
   └─ 200 {me: ...}

5. Frontend invalidates /me → AuthGuard re-routes.
```

---

## 3. Data model

One Alembic migration: `apps/api/migrations/versions/0002_platform_settings_signup_invites.py`. Depends on `0001`.

### 3.1 New enum

```sql
CREATE TYPE tenant_role AS ENUM ('owner', 'admin', 'editor', 'read_only');
```

### 3.2 `platform_settings` — singleton

```sql
CREATE TABLE platform_settings (
    id                smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    signups_enabled   boolean NOT NULL DEFAULT false,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    updated_by        uuid REFERENCES auth.users(id) ON DELETE SET NULL
);

INSERT INTO platform_settings (id, signups_enabled) VALUES (1, false);
```

`CHECK (id = 1)` enforces singleton at the DB layer. Default `signups_enabled = false` — super_admin must explicitly opt in.

### 3.3 `tenant_memberships`

```sql
CREATE TABLE tenant_memberships (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role        tenant_role NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id)
);
CREATE INDEX tenant_memberships_user_id_idx ON tenant_memberships(user_id);
CREATE INDEX tenant_memberships_tenant_id_idx ON tenant_memberships(tenant_id);

-- Exactly one owner per tenant (partial unique index).
CREATE UNIQUE INDEX tenant_memberships_one_owner_per_tenant
    ON tenant_memberships(tenant_id) WHERE role = 'owner';
```

### 3.4 `platform_invites`

```sql
CREATE TABLE platform_invites (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email        citext NOT NULL,
    role         platform_role NOT NULL CHECK (role IN ('admin', 'editor')),
    invited_by   uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    expires_at   timestamptz NOT NULL,
    accepted_at  timestamptz,
    revoked_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX platform_invites_email_pending_uq
    ON platform_invites(email)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;
```

CHECK clause: super_admin can be created **only** via CLI; no one (not even super_admin from the UI) can invite another super_admin. This is intentional friction — it forces a human-on-the-machine action to add a new super_admin.

### 3.5 `tenant_invites`

```sql
CREATE TABLE tenant_invites (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email        citext NOT NULL,
    role         tenant_role NOT NULL CHECK (role IN ('admin', 'editor', 'read_only')),
    invited_by   uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    expires_at   timestamptz NOT NULL,
    accepted_at  timestamptz,
    revoked_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tenant_invites_tenant_id_idx ON tenant_invites(tenant_id);
CREATE UNIQUE INDEX tenant_invites_email_pending_uq
    ON tenant_invites(tenant_id, email)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;
```

CHECK clause: nobody can create an `owner` invite via this table. Owners come from self-serve signup only.

### 3.6 RLS policies

All four new tables have RLS enabled. FastAPI's `require_*` deps are the primary gate; RLS is defense-in-depth.

```sql
-- platform_settings ------------------------------------------------------
ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY platform_settings_authenticated_read ON platform_settings
    FOR SELECT TO authenticated USING (true);

CREATE POLICY platform_settings_super_admin_write ON platform_settings
    FOR UPDATE TO authenticated
    USING (EXISTS (SELECT 1 FROM platform_users pu
                   WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
    WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                        WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active));

-- tenant_memberships -----------------------------------------------------
ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_memberships_self_read ON tenant_memberships
    FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY tenant_memberships_super_admin_all ON tenant_memberships
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM platform_users pu
                   WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
    WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                        WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active));

CREATE POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM tenant_memberships m
                   WHERE m.tenant_id = tenant_memberships.tenant_id
                     AND m.user_id = auth.uid()
                     AND m.role IN ('owner','admin')))
    WITH CHECK (EXISTS (SELECT 1 FROM tenant_memberships m
                        WHERE m.tenant_id = tenant_memberships.tenant_id
                          AND m.user_id = auth.uid()
                          AND m.role IN ('owner','admin')));

-- tenants: add member read on top of existing super_admin policy --------
CREATE POLICY tenants_member_read ON tenants
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM tenant_memberships m
                   WHERE m.tenant_id = tenants.id AND m.user_id = auth.uid()));

-- platform_invites -------------------------------------------------------
ALTER TABLE platform_invites ENABLE ROW LEVEL SECURITY;

CREATE POLICY platform_invites_super_admin_all ON platform_invites
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM platform_users pu
                   WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
    WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                        WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active));

-- tenant_invites ---------------------------------------------------------
ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_invites_super_admin_all ON tenant_invites
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM platform_users pu
                   WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
    WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                        WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active));

CREATE POLICY tenant_invites_owner_admin_all ON tenant_invites
    FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM tenant_memberships m
                   WHERE m.tenant_id = tenant_invites.tenant_id
                     AND m.user_id = auth.uid()
                     AND m.role IN ('owner','admin')))
    WITH CHECK (EXISTS (SELECT 1 FROM tenant_memberships m
                        WHERE m.tenant_id = tenant_invites.tenant_id
                          AND m.user_id = auth.uid()
                          AND m.role IN ('owner','admin')));

-- Triggers: set_updated_at on tenant_memberships -----------------------
CREATE TRIGGER tenant_memberships_set_updated_at
    BEFORE UPDATE ON tenant_memberships
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

The `set_updated_at()` function was created in migration `0001`; we reuse it.

---

## 4. API surface

All routes are async. All Supabase Admin calls wrapped in `asyncio.wait_for(call, timeout=10.0)`. All Pydantic request/response models live in `apps/api/src/xtrusio_api/schemas/`.

### 4.1 Public (no auth)

#### `GET /platform/signup-status`

```json
// 200
{ "signups_enabled": true }
```

#### `POST /signup`

```json
// request
{ "email": "jane@acme.com", "password": "MinLen8Pls" }
// 202
{ "state": "confirm_email_sent" }
```

Errors:
- `400 invalid_email` / `400 weak_password`
- `403 signups_disabled`
- `409 email_taken`

### 4.2 Authenticated, any signed-in user

#### `GET /me`

```json
// 200
{
  "user_id": "uuid",
  "email": "jane@acme.com",
  "platform": { "role": "super_admin" | "admin" | "editor", "is_active": true } | null,
  "tenants": [
    { "id": "uuid", "slug": "acme-corp", "name": "Acme Corp", "role": "owner" }
  ],
  "pending_invite": {
    "kind": "platform" | "tenant",
    "id": "uuid",
    "tenant_id": "uuid" | null,
    "role": "admin" | "editor" | "read_only"
  } | null
}
```

`pending_invite` is non-null when the JWT carries `user_metadata.platform_invite_id` or `user_metadata.tenant_invite_id` AND the matching row exists and is valid (not accepted, not expired, not revoked). If invalid (expired/revoked/already accepted/email mismatch), `pending_invite` is null; AuthGuard then routes by the remaining `platform` / `tenants` fields (typically → `/onboarding`).

#### `POST /onboarding/tenants`

```json
// request
{ "workspace_name": "Acme Corp" }
// 201
{ "tenant": { "id": "uuid", "slug": "acme-corp", "name": "Acme Corp", "role": "owner" } }
```

Errors:
- `409 already_has_membership`
- `422 workspace_name_invalid` with `reason: min_length | max_length | no_letters`

#### `POST /invites/accept`

Empty request body; reads identity + invite from JWT.

```json
// 200 — same shape as GET /me, updated state
```

Errors:
- `403 no_invite | invite_revoked | invite_expired | email_mismatch`
- `409 invite_already_accepted`

### 4.3 Super_admin only

#### `GET /platform/settings`
```json
// 200
{ "signups_enabled": true, "updated_at": "...", "updated_by_email": "owner@x.com" | null }
```

#### `PUT /platform/settings`
```json
// request
{ "signups_enabled": true }
// 200 — same shape as GET
```

#### `GET /platform/users`
```json
// 200 — paginated; default limit=50, max=200
{
  "items": [
    { "id": "uuid", "email": "...", "role": "admin", "is_active": true,
      "last_sign_in_at": "...", "created_at": "..." }
  ],
  "next_cursor": null
}
```

#### `POST /platform/users/invites`
```json
// request
{ "email": "alice@example.com", "role": "admin" | "editor" }
// 201
{ "invite": { "id": "uuid", "email": "...", "role": "...", "expires_at": "...", "created_at": "..." } }
```

Errors:
- `409 user_exists | invite_pending`
- `400 invalid_email`
- `502 email_provider_unavailable`

#### `GET /platform/users/invites`
Paginated list of platform invites (open + accepted + revoked, filterable by status query param).

#### `DELETE /platform/users/invites/{id}`
Sets `revoked_at`. Also calls `supabase.auth.admin.delete_user(...)` to drop the unconfirmed Supabase user. Cannot revoke an accepted invite (`409 invite_already_accepted`).

### 4.4 Tenant owner / admin

#### `POST /tenants/{tenant_id}/invites`

Authorization (service layer, in this order):
1. Caller must have `tenant_memberships` row for `tenant_id` (else `403 not_a_member`).
2. Caller's role must be `owner` or `admin` (else `403 not_owner_or_admin`).
3. Role-of-inviter vs role-being-invited rule:
   - `owner` → may invite `admin`, `editor`, `read_only`
   - `admin` → may invite `editor`, `read_only` (not other admins)
   - Else → `403 forbidden_role`
4. `role == 'owner'` is rejected by CHECK constraint regardless of caller.

```json
// request
{ "email": "alice@example.com", "role": "admin" | "editor" | "read_only" }
// 201
{ "invite": { "id": "uuid", "tenant_id": "uuid", "email": "...", "role": "...", "expires_at": "...", "created_at": "..." } }
```

Errors:
- `403 not_a_member | not_owner_or_admin | forbidden_role`
- `409 user_already_member | invite_pending`
- `400 invalid_email`
- `502 email_provider_unavailable`

#### `GET /tenants/{tenant_id}/invites`
Paginated. Same role rules: owner/admin or super_admin.

#### `DELETE /tenants/{tenant_id}/invites/{id}`
Revoke + delete unconfirmed Supabase user.

### 4.5 Modified existing endpoints

#### `GET /tenants`
- Super_admin: all tenants (existing).
- Tenant_member: tenants they're a member of, joined with their role.
- Unprovisioned: empty list.
- Paginated (default 50, max 200).

#### `POST /tenants`
Unchanged: super_admin manually creates a tenant with no membership. Out of scope: assigning an owner via this path.

### 4.6 Error envelope (cross-cutting)

```json
{ "detail": "<machine_code>", "message": "<human readable>" }
```

`detail` is the only field the frontend switches on. `message` is for display fallback. Codes listed per endpoint above; full table maintained in `apps/web/src/lib/error-messages.ts`.

---

## 5. Frontend routes + AuthGuard

### 5.1 Routes

| Path | Access | Status | Purpose |
|---|---|---|---|
| `/sign-in` | public | existing | password sign-in |
| `/sign-up` | public | **new** | conditional on `signups_enabled` |
| `/accept-invite` | authed | **new** | auto-POSTs `/invites/accept` on mount |
| `/onboarding` | authed (no identity) | **new** | workspace name form |
| `/` | authed | existing | routing hub (AuthGuard decides) |
| `/settings` | super_admin | shell expanded | signups toggle UI |
| `/users` | super_admin | shell expanded | platform user list + invite dialog |
| `/clients` | authed | shell expanded | super_admin: all; tenant_member: their own |
| `/clients/$slug/users` | tenant owner/admin | **new** | tenant invite UI |

### 5.2 AuthGuard state machine

In `apps/web/src/components/auth-guard.tsx`. Wraps everything inside `__root.tsx` after `AuthProvider`.

```
on every navigation:
  if (auth.loading)                       → render <Spinner/>
  if (!auth.session)
      if (path == /sign-in || /sign-up)   → render route
      else                                → redirect /sign-in?next=<path>
  // session exists → fetch /me via TanStack Query (cached, no refetch on focus)
  if (me.loading)                         → render <Spinner/>
  if (me.pending_invite)
      if (path == /accept-invite)         → render route (auto-POSTs accept)
      else                                → redirect /accept-invite
  if (me.platform)
      if (path starts with /clients/$slug)→ allow (super_admin can navigate)
      else                                → render route (platform UI)
  if (me.tenants.length > 0)
      if (path == /settings || /users)    → redirect /  (platform-only)
      else                                → render route (tenant UI)
  // platform=null, tenants=[], pending_invite=null
  if (path == /onboarding)                → render route
  else                                    → redirect /onboarding
```

Decision logic is extracted into a **pure function** `resolveRoute(me, path)` for testability (see §7.1).

### 5.3 Route component responsibilities

- **`/sign-up`** — on mount: `GET /platform/signup-status`. Render form vs disabled message. On submit: `POST /signup` → "Check your email" screen.
- **`/accept-invite`** — on mount: `POST /invites/accept`. Success → invalidate `/me` → redirect `/`. 4xx → render explanation + Sign Out.
- **`/onboarding`** — single field. On submit: `POST /onboarding/tenants` → invalidate `/me` → redirect `/`.
- **`/settings`** — switch wired to `GET/PUT /platform/settings`. TanStack Query optimistic update.
- **`/users`** — Tabs: "Members" / "Pending invites". Invite dialog: email + role (admin/editor). Revoke action on pending rows.
- **`/clients`** — super_admin: full list + Create Tenant CTA (existing); tenant_member: their own tenants. Each row links to `/clients/$slug/users`.
- **`/clients/$slug/users`** — tenant members table + invite dialog (admin/editor/read_only). Visible only to owner/admin per AuthGuard.

### 5.4 Component edits

- `app-sidebar.tsx` — show platform nav (Users/Settings/Clients) when `me.platform`; tenant nav (Members) when `me.tenants.length > 0`.
- `app-topbar.tsx` — email + role badge. Tenant switcher placeholder when `me.tenants.length > 1` (multi-tenancy not exercised in this spec).
- `user-menu.tsx` — role badge.
- `auth-guard.tsx` — full rewrite from "logged in?" check to the state machine.
- `lib/api.ts` — wrappers for every new endpoint via `apiFetch`.

---

## 6. Emails + error handling

### 6.1 Emails — three flows, all sent by Supabase

| Email | Trigger | Template | Redirect |
|---|---|---|---|
| Confirm signup | `auth.admin.create_user(email_confirm=false)` | "Confirm signup" | `https://<APP>/?next=/onboarding` |
| Platform invite | `auth.admin.invite_user_by_email(data={platform_invite_id, role})` | "Invite user" | `https://<APP>/accept-invite` |
| Tenant invite | `auth.admin.invite_user_by_email(data={tenant_invite_id, tenant_id, role})` | "Invite user" | `https://<APP>/accept-invite` |

**Supabase project config (one-time, dashboard):**
- Authentication → Sign In / Up → Email: **Email provider on**, **Confirm email on**, **Project-level signups on** (we gate at our API).
- Authentication → URL Configuration:
  - **Site URL:** `http://localhost:5173` (dev)
  - **Redirect URLs:** `http://localhost:5173/**` (dev). Production URL added when domain is set up.

Template customization (branded copy) — out of scope. Supabase defaults.

### 6.2 Error contract

```json
{ "detail": "<machine_code>", "message": "<human>" }
```

Frontend switches on `detail`. Unknown codes fall back to a generic toast. 5xx falls back to "We're having trouble reaching the server."

### 6.3 Failure walkthroughs

**Email already exists at signup.** Supabase Admin returns 422; we translate to `409 email_taken`. (Future privacy posture: silently swallow → always 202. One-line change; not in scope.)

**Expired/revoked invite link.** Supabase confirms the user (gives them a session) regardless of our invite state. `/accept-invite` calls `POST /invites/accept` → API returns `403 invite_expired` or `invite_revoked` → frontend shows explanation + Sign Out. Orphan auth user remains; nightly cleanup job (out of scope) sweeps.

**Supabase Admin API timeout during invite.** Our invite row was inserted; Supabase call timed out. Return `502 email_provider_unavailable`. Retry hits unique constraint → super_admin must revoke + retry. Right fix is a `sent_at` flag + Dramatiq retry — flagged as follow-up.

### 6.4 Logging

INFO on every state-changing request with `{user_id, route, status_code, duration_ms}`. WARNING for 4xx with `{detail}`. ERROR with stack trace for 5xx. Email addresses are logged on auth endpoints (debugging requirement; accept the PII trade-off).

---

## 7. Testing strategy

Project rules §8, §9.

### 7.1 Unit tests (pure)

Backend (pytest):
- `slugify()` — known inputs, collisions (`acme`, `acme-2`, …), edge cases.
- `can_invite(inviter_role, target_role)` — table-driven across owner/admin × admin/editor/read_only.
- `extract_invite_from_jwt(claims)` — picks platform_invite_id vs tenant_invite_id.

Frontend (Vitest):
- `error-messages.ts` — known + unknown code fallback.
- `resolveRoute(me, path)` — table-driven across the 5 user kinds × ~6 paths.

### 7.2 API tests (Postgres testcontainer)

Per-endpoint, covering: unauthenticated → 401, wrong role → 403, validation → 400/422, not found → 404, success → 2xx.

Files:
- `tests/routes/test_signup.py`
- `tests/routes/test_platform_settings.py`
- `tests/routes/test_onboarding.py`
- `tests/routes/test_invites_platform.py`
- `tests/routes/test_invites_tenant.py`
- `tests/routes/test_invites_accept.py`
- `tests/routes/test_me.py`

Supabase Admin client is replaced by a fixture that records calls.

### 7.3 RLS tests

Same DB; tests run as different roles via `SET request.jwt.claims`:
- `tests/rls/test_platform_settings_rls.py`
- `tests/rls/test_tenant_memberships_rls.py`
- `tests/rls/test_tenant_invites_rls.py`
- `tests/rls/test_platform_invites_rls.py`
- `tests/rls/test_tenants_rls.py` (regression on Plan 1B + new member-read policy)

### 7.4 Integration test (one)

`tests/integration/test_signup_to_invite_full_flow.py` — super_admin enables signup → anon signup → confirm → onboarding → owner invites admin → admin accepts → both see correct `/me`.

### 7.5 Frontend tests (Vitest + RTL + MSW)

- `auth-guard.test.tsx`
- `sign-up.test.tsx`
- `onboarding.test.tsx`
- `accept-invite.test.tsx`
- `settings.test.tsx`
- `users.test.tsx`
- `clients/$slug/users.test.tsx`

### 7.6 Coverage

80% on new code (rule §9). Migrations excluded.

### 7.7 Explicitly not tested

- Supabase auth flow internals (their contract).
- Email template rendering (defaults; no customization).
- Real SMTP delivery (mocked Supabase client records calls).

---

## 8. Implementation plan suggestion

This spec is large enough to ship as **two implementation plans**.

**Plan 2A — Public chain (priority)**
- Schema: `0002` migration with `platform_settings`, `tenant_role` enum, `tenant_memberships`, RLS, tenants RLS extension.
- Backend: `/platform/signup-status`, `/signup`, `/onboarding/tenants`, `/platform/settings` (GET/PUT), `/me` extended response.
- Frontend: `/sign-up`, `/onboarding`, `/settings` toggle UI, AuthGuard rewrite.
- Tests: corresponding routes + RLS + the integration test (signup half only).
- Outcome: Self-serve signup works end-to-end, super_admin controls the toggle.

**Plan 2B — Invites**
- Schema: extend `0002` (or new `0003`) with `platform_invites`, `tenant_invites`, RLS.
- Backend: `/platform/users/invites` (CRUD), `/tenants/{id}/invites` (CRUD), `/invites/accept`.
- Frontend: `/users` invite UI, `/clients/$slug/users` page, `/accept-invite` callback.
- Tests: invites routes + RLS + the integration test (invite half).
- Outcome: Platform + tenant invites work end-to-end.

The split is optional. If we want one big PR, we ship as one plan — but the cognitive load benefits from the split.

---

## 9. Out of scope (recap) + follow-ups

**Out of scope:**
- Custom domain
- Multi-tenant URL routing beyond `/clients/$slug/users`
- Per-tenant features / plans / billing
- Audit log table + impersonation
- Ownership transfer
- Custom email templates
- Rate limiting
- Orphan cleanup job (confirmed-but-no-row auth users)
- Real-time subscriptions

**Follow-up tasks to file as issues after this lands:**
- Orphan cleanup nightly Dramatiq job (sweep auth.users with no platform_users + no tenant_memberships + created_at > 7d ago)
- Email-template branding pass
- `sent_at` flag on invite tables + retry job for Supabase email delivery failures
- Privacy posture flip: signup with existing email returns 202 silently instead of 409
