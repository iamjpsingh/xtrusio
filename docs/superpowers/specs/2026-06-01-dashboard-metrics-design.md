# Design — Dashboard Metrics

**Date:** 2026-06-01
**Status:** APPROVED — first real product feature on the dashboards (replaces the `StatCard` "—/Not yet available" zero-states)
**Branch:** `dashboard-metrics`

## Goal

Put REAL numbers on the platform dashboard (`/platform`) and workspace overview (`/workspace/$id`) — the counts that already have `StatCard` placeholders. No demo data; live queries only.

## Endpoints (one round-trip per dashboard)

- `GET /api/platform/stats` → `PlatformStats`
- `GET /api/workspaces/{workspace_id}/stats` → `WorkspaceStats`

Each returns ONLY the metrics the caller is authorized to see (per-metric permission gating). A metric the caller can't read is `null` in the response, and the frontend **omits that card entirely**.

## Metrics

| Endpoint | Field | Query | Gate |
|---|---|---|---|
| platform | `client_tenants` | `SELECT count(*) FROM tenants` | `platform.clients.read` |
| platform | `active_platform_users` | `count(*) FROM platform_users WHERE is_active` | `platform.users.read` |
| platform | `recent_activity` | `count(*) FROM rbac_audit_log WHERE scope='platform' AND created_at > now() - interval '7 days'` | `platform.audit.read` |
| workspace | `members` | `count(*) FROM tenant_memberships WHERE tenant_id = :wid` | `workspace.members.read` |
| workspace | `pending_invites` | `count(*) FROM tenant_invites WHERE tenant_id = :wid AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now()` | `workspace.members.read` |
| workspace | `recent_activity` | `count(*) FROM rbac_audit_log WHERE scope='workspace' AND workspace_id = :wid AND created_at > now() - interval '7 days'` | `workspace.audit.read` |

- **Activity window:** 7 days (fixed).
- **Base reachability gate:** platform endpoint requires `platform.users.read`; workspace endpoint requires `workspace.members.read` (matches the dashboards' nav perms). 403 otherwise. Per-metric gates layer on top.
- **RLS:** the backend runs as the table owner (bypasses RLS), so the explicit `WHERE` filters (`tenant_id`, `workspace_id`, `scope`) ARE the data fence — every workspace-scoped count MUST filter by `:wid`. Uses the 0011 audit indexes (`(scope, workspace_id, created_at DESC)`).
- **Effect of gating:** a `read_only` / `editor` workspace member (has `members.read`, lacks `audit.read`) sees Members + Pending invites but NOT Recent activity.

## Shape

- **Schemas** (`schemas/`): `PlatformStats` / `WorkspaceStats`, `BaseModel` with `int | None` fields (`None` = not authorized). No pagination.
- **Services** (`services/platform_stats.py`, `services/workspace_stats.py`): plain `SELECT count(*)` via `text()` + `.scalar_one()`, one per authorized metric (skip the query when the caller lacks the gate — don't compute then hide). Caller-owns-tx convention (read-only, no commit).
- **Routes** (`routes/platform_stats.py`, `routes/workspace_stats.py`): base `require_permission`, then `has_permission(...)` per metric to decide inclusion. Registered in `main.py` alongside the sibling platform/workspace routers.
- **No cache** (YAGNI — indexed counts are cheap; add short-TTL Valkey later only if a dashboard gets hot).

## Frontend

- Regenerate `packages/api-types/generated/openapi.d.ts` via `pnpm api-types:generate` (imports the app; no DB/boot); add `src/platform-stats.ts` + `src/workspace-stats.ts` re-exports + `index.ts`.
- `lib/api.ts`: `fetchPlatformStats()`, `fetchWorkspaceStats(workspaceId)`. `lib/query-keys.ts`: `platformStats()`, `workspaceStats(id)`.
- Dashboards (`routes/_app.platform.index.tsx`, `routes/_app.workspace.$workspaceId.index.tsx`): `useQuery` the stats; render a `StatCard` per metric **only when the field is non-null**; while loading show a value skeleton (reuse pass-1 primitives); on error show a graceful `ErrorState` or keep the cards as "—". Format numbers with `tabular-nums`; activity hint = "last 7 days", users hint = "active".

## Tests

- **Backend** (write + run TARGETED, not the full suite — managed-DB is slow): count correctness (seed N rows under `@example.com` hygiene, assert the count) and the **gating matrix** (super_admin sees all platform metrics; a `read_only` workspace member sees members+invites but `recent_activity` is `null`). Crash-proof teardown per test-data hygiene.
- **Frontend** (vitest, authorized): renders values from a mocked stats response; omits the card when a field is `null`; loading + error states.

## Constraints

- `mypy --strict`, ruff (incl. format), no hardcoded config. TypeScript only. Monochrome, design tokens only. No demo data. 500 LoC/file. No co-author trailer.
- Cadence per CLAUDE.md: one Opus subagent owns backend → api-types regen → frontend (cohesive, internal sequential dependency); controller runs the gate; full backend suite NOT run from the subagent.
