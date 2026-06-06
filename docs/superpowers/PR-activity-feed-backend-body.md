# feat(audit) — Activity=Audit feed backend: coverage backfill + event catalog + category filter + role_name

Slice A of the unified **Activity = Audit feed** (plan: `docs/superpowers/plans/2026-06-06-activity-feed.md`). The existing `rbac_audit_log` + the two cursor-paginated viewers ARE the feed; this slice makes them cover the whole mutation surface, adds human-readable labels + categories, and lets the UI filter by category. **No migration** — the table already accepts arbitrary `action`/`target_type`/`target_id` strings; `category` (with reserved `auth`/`system` keys) carries the future GoTrue/worker source distinction, so those land later with zero schema churn.

## What landed

**1. Coverage backfill** — every previously-unlogged mutation now writes an audit row in its own transaction (`write_audit_event` never commits — the row can't outlive a rolled-back mutation):
- `platform_invite.create` / `.revoke` / `.accept`
- `tenant_invite.create` / `.revoke` / `.accept`
- `tenant.create` (onboarding)
- `platform_user.create` (direct provision)
- `platform.settings.updated`

tx-ownership respected: the two self-committing `revoke_*_invite` functions write the audit row (capturing the `before` payload) **before** `db.commit()`; the caller-owns-tx functions write before returning. `revoke_platform_invite` gained a required `actor_id` kwarg, threaded from the route.

**2. `role_name` in grant/revoke payloads** — the 4 grant/revoke services now record the human role **name** alongside the machine `role_key` in `before`/`after` (so the UI Role column reads "Auditor", not `auditor`).

**3. Event catalog** (`core/audit_catalog.py`) — single source of truth mapping each `action → (label, category)`; `describe_action()` (unknown → title-cased + `other`), `categories()` for the filter dropdown. Categories: `roles, grants, invites, members(reserved), workspaces, users, settings, auth(reserved), system(reserved), other`.

**4. `AuditEventOut` enrichment** — two Pydantic `@computed_field`s, `action_label` + `category`, derived from `action` (no service change; robust for legacy/unknown actions).

**5. Catalog endpoint** — `GET /api/audit/catalog` → `{categories, actions}`, authed-only (non-secret metadata, mirrors `/api/permissions/catalog`).

**6. Category filter** — `?category=` on both `GET /api/platform/audit-log` and `GET /api/workspaces/{wid}/audit-log`; resolved to an action-set via the catalog and `AND action = ANY(:actions)` threaded into the existing HMAC-signed cursor SELECT (pagination preserved; `None`/unknown → no filter; empty category → zero rows).

**7. api-types** — `openapi.d.ts` regenerated (idempotent — two consecutive regens byte-identical), `AuditCatalog` types re-exported. Existing `apps/web` `AuditEventOut` test fixtures updated for the two new required fields (the only `apps/web` touch this slice; the table/filter/drawer UI is Slice B).

## Security / scope
No signup/auth-enumeration path touched. No new PII surfaced (invite emails were already stored; `actor_email` is already LEFT-JOINed into the viewer). Audit reads stay permission-gated (`platform.audit.read` / `workspace.audit.read`); only the label catalog is authed-only.

## Gate
`ruff check` + `ruff format --check` clean (apps/api); `mypy apps/api` (`--strict`) clean (214 files); `turbo run typecheck` 3/3 + `turbo run lint` green; api-types regen idempotent; backend targeted tests green (catalog unit 9, platform-audit-log+catalog-route 15, workspace-audit-log 8, audit-coverage 9, grants+audit-log-routes 33); web audit vitest 15/15. Full managed-DB suite not run per the per-slice bar (shared-state fragility — documented in HANDOFF).

## Follow-ups
Slice B (frontend normalize: Time/Actor/Action-label/Role columns + category filter UI + structured before→after drawer). Slice C (worker/system log → `system` category). GoTrue login/logout → `auth` category stays a flagged operator-decision follow-up.
