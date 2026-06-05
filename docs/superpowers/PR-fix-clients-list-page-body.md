# fix(web) — Clients page renders (paginated /api/tenants) + drill-in to client detail

Closes the CRITICAL audit finding `tenants-list-shape-mismatch` — the user's #1 complaint: "we can't see the clients and their info."

## The bug

`GET /api/tenants` returns a cursor-paginated envelope `TenantsPage { items, next_cursor }`, but the Clients page typed it as a bare `Tenant[]` and did `data.length` / `data.map(...)`. At runtime `data` is the envelope object → `data.length` is `undefined` (empty-state never fires) and `data.map` **throws** → the clients table was always empty/broken even when tenants existed.

## Fixes

- **Typed helper:** added `fetchTenants(cursor): Promise<TenantsPage>` to `lib/api.ts` (mirrors `fetchPlatformUsers`); re-exported the generated `TenantsPage`/`TenantOut` from `@xtrusio/api-types` (they existed in the generated OpenAPI but weren't surfaced). Removed the hand-rolled local `Tenant` types in the clients route and `create-client-dialog.tsx`.
- **List page:** extracted to `components/clients-page.tsx` (route = thin wrapper + perm gate, matching `platform-users-page.tsx`); consumes the envelope via `useInfiniteQuery` (`items` flattened, `next_cursor` → `LoadMoreButton`), with the standard skeleton/empty/error states. Query key via `qk.tenants()` (no inline keys).
- **Drill-in:** each client Name cell is now a TanStack `<Link to="/platform/clients/$slug/users">` — the per-client route existed but was previously unreachable from the UI.
- **Per-client detail:** `tenant-users-page.tsx` no longer renders a blank `return null` for a platform admin who isn't a member of the client tenant — it shows a clear "Limited view" state (+ loading skeleton). **Follow-up:** full per-client info for a non-member platform admin needs a new platform-scoped endpoint (e.g. `GET /api/platform/clients/{slug}` → tenant + members, gated by `platform.clients.read`); tracked, not in this slice.

## Tests

- `clients-page.test.tsx` — renders rows from the envelope's `items` (regression: fails against the old `Tenant[]`/`data.map` assumption), row→detail link, empty state, error+retry, load-more pagination.
- `tenant-users-page.test.tsx` — non-member shows "Limited view" and never fetches invites.
- MSW `GET /api/tenants` handler + typed `TenantOut` fixtures.

Gate: `make lint` + `make typecheck` clean; full web vitest **230/230** green. No backend change (api-types re-export + apps/web only).
