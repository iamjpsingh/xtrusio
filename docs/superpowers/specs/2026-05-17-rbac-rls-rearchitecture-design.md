# Design — RBAC + RLS Re-architecture

**Date:** 2026-05-17
**Status:** Approved (all sections) — ready for phased implementation planning
**Supersedes:** the enum-role model (`platform_users.role`, `tenant_memberships.role`) and the
`is_super_admin` / `is_tenant_owner_or_admin` / `is_tenant_member` SECURITY DEFINER helpers
introduced in migration `0003`.
**Builds on:** `main` @ `21477b3` (Plan 2A + 2B merged; Alembic head `0005`; backend 82 / frontend 29 tests green).

---

## 1. Purpose & goals

Replace the hardcoded enum-role authorization with a **dynamic, data-driven RBAC** system that is
enterprise-grade and fully multi-tenant SaaS:

- Roles are **data**; permission primitives are **code-defined**.
- **Platform** and **workspace (client)** are two fully separate authorization domains that share
  only one Supabase `auth.users` login id and never reference each other beyond it.
- Authorization is **DB-enforced** (RLS) and **backend-enforced** through the *same* resolver
  functions, so a revoked role takes effect on the next request (instant revocation).
- Self-service: platform `super_admin` governs platform RBAC; each client `owner` governs RBAC
  **within their own workspace** without platform involvement.

### Non-goals (explicitly deferred)

- Time-bound / expiring role grants.
- Admin-defined permission primitives (permissions are always code-defined).
- Any piecemeal UI fix outside the phased plan below.

---

## 2. Locked decisions (authoritative)

1. **Permission catalog is code-defined.** Developers add `scope.resource.action` permission keys
   in code as features ship. `super_admin` composes those keys into roles but cannot invent
   permission primitives. A permission key is only ever meaningful because backend code and an RLS
   policy actually check it.
2. **Role creation is split by scope.** Platform-scoped roles: only `super_admin` creates/edits.
   Workspace-scoped roles: each client `owner` creates/edits custom roles **within their own
   workspace** (sees only `workspace.*` permissions; cannot touch platform or other workspaces).
3. **super_admin owns RBAC, admins operate.** `super_admin` (exactly 1, bootstrap-only) is the
   only one who creates/edits platform roles, composes permissions, and grants the platform-`admin`
   role. Platform `admin` (many) has full operational power (manage clients, platform users,
   settings, assign non-privileged roles) but cannot create/edit roles or self-escalate.
4. **Workspace hierarchy:** seed roles `owner`, `admin`, `editor`, `read_only`. `owner` is the
   workspace's governance authority (create/edit custom roles, assign any workspace role, manage
   members + settings). `admin` operates (invite/manage members, settings, assign non-privileged
   roles) but cannot create/edit roles. `editor` = content write. `read_only` = view. The user who
   signs up / completes onboarding becomes that workspace's first `owner`.
5. **Multiple roles per user; effective permissions = union.**
6. **Enterprise extras included now:** audit log (recorded **and** read-only UI), permission
   grouping/categories. **Non-negotiable and baked in:** privilege-escalation guard,
   single-`super_admin` DB invariant, immutable system roles, instant DB-enforced revocation.
7. **"platform editor"** (from the old nav-visibility matrix) is **not** a hardcoded seed role — it
   becomes a custom platform role `super_admin` may create. The nav matrix becomes
   permission-driven, not role-name-driven.

---

## 3. Domain model & schema

### 3.1 Identity tables (existing, retained)

- `platform_users` — the platform identity table. Its `role` enum column is **retired
  post-migration** (kept during migration so nothing breaks mid-flight).
- `tenant_memberships` — the workspace membership table. Its `role` enum column is likewise retired
  post-migration.

An account belongs to **one domain**. The two domains share only `auth.users.id`.

### 3.2 RBAC core tables (new, scope-tagged)

| Table | Columns (essential) | Notes |
|---|---|---|
| `permissions` | `id, scope, key, category, description, is_deprecated` | scope ∈ {`platform`,`workspace`}. `key` e.g. `workspace.members.invite`. Unique `(scope, key)`. **Code-seeded**, never user-writable. `is_deprecated` set by the reconciler when a key leaves the code catalog. |
| `roles` | `id, scope, workspace_id, key, name, description, is_system, created_by, created_at, updated_at` | `workspace_id` NULL for platform roles, NOT NULL for workspace roles. Unique `(scope, workspace_id, key)`. `is_system=true` ⇒ immutable. |
| `role_permissions` | `role_id, permission_id` | M:N. Scope of role and permission must match (DB check/trigger). |
| `user_roles` | `id, auth_user_id, role_id, workspace_id, granted_by, granted_at` | Multiple per user. `workspace_id` mirrors the role's scope (NULL for platform). |
| `rbac_audit_log` | `id, actor_auth_user_id, action, target_type, target_id, scope, workspace_id, before jsonb, after jsonb, created_at` | Append-only. |

All new tables get `GRANT SELECT/INSERT/UPDATE/DELETE TO authenticated` (Plan-2 gotcha #3 — Alembic
tables don't inherit Supabase auto-grants; RLS tests fail with "permission denied" otherwise).

### 3.3 Seed system roles (`is_system=true`, immutable)

- **Platform scope:** `super_admin`, `admin`.
- **Workspace scope:** `owner`, `admin`, `editor`, `read_only` — **instantiated per workspace**
  (each workspace gets its own `roles` rows with `is_system=true`, satisfying the
  `unique (scope, workspace_id, key)` constraint and letting custom roles layer alongside them).
  Creation/seeding of these rows happens at workspace-creation time (onboarding) and is
  backfilled for existing workspaces by migration `0006`.

Each seed role's `role_permissions` set is defined by the code catalog at seed time.

---

## 4. Permission catalog (code-defined)

A code module declares the canonical catalog: a list of `(scope, key, category, description)`.
Devs add entries here as features ship. A reconciler runs on migrate/startup:

- Inserts new catalog entries into `permissions`.
- **Soft-deprecates** entries no longer in code (sets an `is_deprecated` flag; never hard-deletes
  and never cascades into `role_permissions` — existing grants are preserved and a deprecated
  permission is simply hidden from the role-builder UI and treated as inert by resolvers).

`category` drives the **permission grouping/categories** UI in the role builder.

Permission keys follow `scope.resource.action`, e.g.:
`platform.users.invite`, `platform.clients.create`, `platform.roles.manage`,
`workspace.members.invite`, `workspace.settings.edit`, `workspace.roles.manage`.

---

## 5. Enforcement — single source of truth

Two `SECURITY DEFINER` SQL functions resolve `user → user_roles → role_permissions → permissions`
live from the tables:

- `has_platform_perm(uid uuid, perm_key text) → boolean`
- `has_workspace_perm(uid uuid, tid uuid, perm_key text) → boolean`

**Both RLS policies and the backend call these exact functions.**

- **RLS:** every platform/tenant-scoped table's policies call the relevant function instead of
  inlining `EXISTS … FROM platform_users/tenant_memberships` (Plan-2 gotcha #2 — inlining
  reintroduces RLS recursion; `SECURITY DEFINER` bypasses RLS internally so the resolver itself
  does not recurse).
- **Backend:** a `require_permission("<key>")` FastAPI dependency (and a
  `require_workspace_permission("<key>")` variant taking the path workspace id) queries the same
  function. The backend uses the owner DB connection (RLS does not constrain it — Plan-2 gotcha
  #7), so backend authz must be **explicit** via these dependencies, never "rely on RLS".

Because resolution reads live tables (nothing baked into the JWT), revoking a role takes effect on
the **next request** — instant revocation.

The migration-`0003` helpers `is_super_admin` / `is_tenant_owner_or_admin` / `is_tenant_member` are
**superseded by rewriting their bodies to delegate to the new resolvers** (e.g.
`is_super_admin(uid)` → `has_platform_perm(uid, 'platform.roles.manage')`). Rewriting bodies rather
than dropping them keeps every existing RLS policy's SQL untouched, minimizes blast radius, keeps a
single Alembic head, and stays reversible. New/updated policies call the resolvers directly.

---

## 6. Governance rules (enterprise, baked in)

1. **Privilege-escalation guard.** To grant role `R` to a user, the actor must already hold every
   permission contained in `R`, within the same scope/workspace. Enforced in the backend service
   **and** a DB trigger (defense-in-depth). Prevents "can assign roles" becoming self-escalation.
2. **Single super_admin invariant.** A DB-level constraint (partial unique index or trigger on
   `user_roles` filtered to the `super_admin` system role) guarantees ≤1 active `super_admin`
   grant. Bootstrap-only. Only `super_admin` may grant the platform-`admin` role.
3. **Immutable system roles.** `is_system=true` roles cannot have permissions edited or be deleted
   (DB trigger + backend guard). Prevents lockout.
4. **Scope isolation.** A workspace `owner` governs RBAC only within their `workspace_id`. The
   resolver functions and RLS structurally prevent cross-workspace or workspace→platform reach.
5. **Audit log.** Every role / permission-assignment / role-grant mutation writes
   `rbac_audit_log` (actor, action, target, scope, workspace, before/after). Read-only viewer UI:
   `super_admin` sees platform-scope entries; workspace `owner` sees their workspace's entries.

---

## 7. Migration strategy (zero-break, reversible)

Migration `0006_rbac_foundation` (`down_revision = "0005"`; single Alembic head):

1. Create all RBAC tables + grants to `authenticated`.
2. Seed `permissions` from the code catalog; seed system roles and their `role_permissions`.
3. Backfill `user_roles` from existing `platform_users.role` and `tenant_memberships.role` enum
   rows → matching system roles (the lone `admin@xtrusio.com` super_admin → `super_admin` grant).
4. Convert `platform_invites.role` / `tenant_invites.role` enum columns to `role_id` FKs
   (scope-correct role); pending invites map to the equivalent system role.
5. **Enum columns on identity/membership tables are kept** during this migration — nothing reads
   the new model exclusively until P3. A **later** migration drops `platform_users.role` /
   `tenant_memberships.role` once no code path reads them.

`downgrade()` restores the enum-reading path (drops RBAC tables, restores invite enum columns).
Every step reversible. Managed DB stays pristine; no `@example.com` test rows; test-data hygiene
per `feedback_test_data_hygiene`.

---

## 8. `/me` & invites reconciliation

This deliberately touches already-merged Plan 2 code:

- `/me` returns **effective permission keys**: a platform set + a per-workspace map of sets,
  resolved via the same functions. The enum `role` field is removed once frontend no longer reads
  it (P3 + P6).
- Invite acceptance (`/invites/accept`) creates a `user_roles` grant instead of writing an enum
  role. `platform_invites` / `tenant_invites` carry `role_id` (P7-style invite tables already
  exist from Plan 2B; the migration in §7.4 adapts them).
- `pending_invite` population logic in `/me` is preserved; only the role representation changes.

---

## 9. Frontend (P6) + folded UI fixes

- **Two physically separate shells:** `PlatformShell` and `WorkspaceShell`. Route tree is split so
  a **pathless app-shell layout route wraps only in-app pages**; `/sign-in`, `/sign-up`,
  `/onboarding`, `/accept-invite` live **outside** any shell. This **structurally fixes the
  shell-bleed bug** (currently `apps/web/src/routes/__root.tsx` only exempts `/sign-in`, so
  `/sign-up`, `/onboarding`, `/accept-invite` wrongly render inside the dashboard sidebar).
- **Permission-driven nav:** nav items render from effective permissions in `/me`, not role names.
  Replaces the old role-name nav-visibility matrix.
- **Signup-status rename** (user-approved scope): public `GET /api/signup-status` meaning "is
  public client signup open"; relabel the `/settings` toggle + disabled message + sign-in link to
  **"Public client signup"**; the super_admin-managed setting stays at `/api/platform/settings`.
  There is **no** "platform signup" concept — platform users are bootstrap/invite only.
- **Auth-page polish:** shared `AuthLayout` matching the `/sign-in` dark shadcn card; shadcn +
  Tailwind only, no raw CSS, no hardcoded colors. Fixes deferred `ApiError.message` misuse on
  sign-up/onboarding (`project_apierror_message_debt`) while those pages are reworked.
- **RBAC management UIs:** platform role/permission management (`super_admin`), workspace
  role/permission management (`owner`), audit-log viewers (both scopes), permission grouping by
  `category` in the role builder. Route files stay thin wrappers; real components + tests live in
  `src/components/` (Plan-2 gotcha #4 — `autoCodeSplitting` strips non-`Route` exports).

---

## 10. Phase decomposition

Each phase = its own plan file under `docs/superpowers/plans/`, executed via
`superpowers:subagent-driven-development` (one subagent per task → spec-compliance review subagent
→ code-quality review subagent → fix loop → commit). `make check` is the merge contract for every
phase. No `Co-Authored-By` trailer on commits (`feedback_no_claude_coauthor`).

| Phase | Scope | Key deliverables |
|---|---|---|
| **P1** | Schema + migration foundation | `0006` migration (tables, grants, seeds, backfill, invite-enum→role_id, reversible); code permission catalog + reconciler; system-role seeds; model classes; migration/seed tests |
| **P2** | RLS engine | `has_platform_perm` / `has_workspace_perm` SECURITY DEFINER fns; rewrite all RLS policies to call them; supersede 0003 helpers; full RLS test matrix (platform + every tenant-scoped table) |
| **P3** | Backend enforcement | `require_permission()` / `require_workspace_permission()` deps replace **all** enum checks; `/me` returns effective perms; invites create `user_roles`; audit-log writes on every RBAC mutation; privilege-escalation guard (service + trigger); single-super_admin invariant |
| **P4** | Platform RBAC admin | Platform role/permission CRUD API + UI (`super_admin`); platform audit-log viewer; signup-status rename (public `GET /api/signup-status` + relabels) |
| **P5** | Workspace RBAC admin | Workspace role/permission CRUD API + UI (`owner`, scope-isolated); workspace audit-log viewer; permission category grouping UI |
| **P6** | Frontend re-architecture | Two-shell split (`PlatformShell`/`WorkspaceShell`); pathless app-shell layout route; shell-bleed structural fix; permission-driven nav; shared `AuthLayout` + auth-page polish; enum `role` removed from frontend; later migration drops identity enum columns |

**After P6:** whole-branch code review → `superpowers:finishing-a-development-branch`.

---

## 11. Engineering rules still in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`: TS-only frontend, no hardcoded colors, no demo data,
`mypy --strict`, no `any`, 500 LoC/file ceiling, every list endpoint paginated, every
tenant-scoped table has RLS + RLS tests, every external call has a timeout, every migration
reversible, single Alembic head. Accepted lint/type baseline: 1 pre-existing `jose` stub error in
`core/auth.py` — zero NEW. Test-data hygiene: tests never create a `super_admin`; no `@example.com`
rows; managed DB stays pristine.

## 12. User-driven items (never auto-run)

Manual browser smokes (real `.env`, `make dev`/OrbStack, bootstrapped owner, real inboxes) remain
user-driven and are scheduled at the end of the relevant phase(s), never executed by an agent.
