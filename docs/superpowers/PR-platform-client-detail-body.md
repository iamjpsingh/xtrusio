# feat(platform) — client-detail endpoint (tenant + members), finishing "see clients and their info"

Completes the audit's clients follow-up (`tenant-users-blank-for-nonmember-admin`): the Clients list now renders (prior slice), but the per-client detail page resolved the tenant from the viewer's own `me.tenants`, so a platform admin who provisioned but never *joined* a client saw a "Limited view" with no members.

## Backend
- `GET /api/platform/clients/{slug}` (own `/api/platform/clients` prefix so `{slug}` can't collide with the static `/api/platform/{settings,users,roles,...}` sub-paths), gated by `require_permission(db, user.user_id, "platform.clients.read")` — **platform scope, no `workspace_id`** — so a non-member platform operator can read **any** client tenant. The gate runs before any data access; a caller without the perm gets `403 permission_denied`; unknown slug → sanitized `404 client not found` (no slug echo).
- Returns `PlatformClientDetail`: `id/slug/name/created_at`, `owner_email` (first owner-role member, nullable), `member_count`, and an inline `members[]` (`auth_user_id`, `email` via `auth.users` LEFT JOIN, `role`, `joined_at`). Members are loaded for the tenant regardless of caller membership. Inline (uncapped) chosen because a client tenant holds a small bounded member set; documented fallback to the cursor-paginated workspace-members shape if a tenant ever grows large.
- `api-types` regenerated (idempotent — drift gate passes); `PlatformClientDetail`/`PlatformClientMember` re-exported.

## Frontend
- `fetchPlatformClient(slug)` + `qk.platformClient(slug)`; `tenant-users-page.tsx` now fetches the client from the new endpoint instead of `me.tenants`, rendering the client's info + members table for a non-member platform admin (the `return null` "Limited view" dead-end is gone). The invites section stays but only for a viewer who is actually a member (invites are workspace-scoped).

## Security
Cross-tenant read is **intended** for platform operators and gated solely by `platform.clients.read`. It does not leak to non-platform users: backend 403s without the perm, and the `$slug/users` route redirects without it. Tests prove: 401 unauth, 403 without the perm, 404 unknown slug (sanitized), and 200 cross-tenant read (a platform admin who is NOT a member reads the tenant + both members + owner_email).

Gate: `make lint` + `make typecheck` clean; `mypy --strict` clean (204 files); backend `test_platform_clients` 4/4; full web vitest 305. (`tenant_memberships` is filtered by `tenant_id` — flagging that the existing per-tenant index should cover it; no speculative migration added.)
