## PAR-E — Frontend correctness

Closes the frontend half of the 2026-05-26 production audit (spec `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` §8). Addresses **H1, H2, H3, H4, M10, M11, M12, M23, M24, L8, L9, L10, L11** — 13 findings. All work is in `apps/web`; zero backend / `.env` changes; no new env vars.

### What changed (by finding)

| ID | Fix |
|---|---|
| **H1 / M23** (E.1) | `lib/auth.tsx`: `onAuthStateChange` clears the whole TanStack cache + the last-workspace pin on `SIGNED_OUT` (and on a *different-user* `SIGNED_IN`) so no prior user's `me`/lists survive. `getSession()` gains a `.catch` that treats corrupted Supabase localStorage as signed-out instead of hanging on "Loading…" forever. |
| **H2 / L8 / L10** (E.2) | `lib/api.ts` rewrite: per-call `AbortController` + 20s timeout (overridable). On 401 → `refreshSession()` → retry once; if refresh fails → `signOut()` + `SessionExpiredError` (`retried` guard prevents loops). `ApiError` now carries a structured `code` (the `detail` body key), never a stringified body; `.message` is the code or `API <status>`. Dedicated `apiFetchVoid` for 204/DELETE — no more `undefined as T`. New `lib/session-cache.ts` caches the session via a single `onAuthStateChange` subscription; `apiFetch` reads the token from memory (with a one-time `getSession()` fallback in the pre-first-event window) instead of 4–8× per page. |
| **H3** (E.3) | `platform-audit-log-page`, `workspace-audit-log-page`, `platform-users-page`, `workspace-members-list-page` migrate the useState-accumulator anti-pattern to `useInfiniteQuery` (`getNextPageParam: lastPage.next_cursor ?? undefined`); `<LoadMoreButton>` calls `fetchNextPage()`. Pages stay cached across nav-away/back. |
| **H4** (E.4 / E.5) | `lib/query-keys.ts` gains the 5 missing factories (`me`, `tenants`, `tenantInvites(id)`, `platformSettings`, `signupStatus`); ~14 inline-key call-sites across 9 files migrated. Platform-tenant invites key renamed to `qk.tenantInvites = ["tenant", id, "invites"]` for parity with the distinct `qk.workspaceInvites`. New ESLint `no-restricted-syntax` rule bans inline `queryKey:` array literals (verified it errors on a violation). |
| **M10** (E.6) | Every `_app.{platform,workspace}.*` route gains a `beforeLoad` perm gate (`ensureQueryData(qk.me())` → `redirect` to the default landing path when the perm is absent). Component-body `if (!hasPerm) return <Forbidden/>` checks kept only as the deep-link fallback. Loaders import the `queryClient` singleton directly (router has no typed context — contained blast radius, matches existing pattern). |
| **M11** (E.7) | New `hooks/use-scoped-role-crud.ts` + `components/scoped-roles-page.tsx`, `scoped-invite-dialog.tsx`, `scoped-grant-manager-body.tsx` drain the platform/workspace duplication. `platform-roles-page.tsx` and `workspace-roles-page.tsx` are now 12-LoC wrappers (≤30 acceptance met); the invite-dialog and grant-manager pairs likewise thinned. |
| **M12** (E.8) | `accept-invite` uses a TanStack Router `loader`; the `useEffect` + `useRef` guard + `eslint-disable` are gone. |
| **M24** (E.9) | `<Toaster>` moved out of `<AuthGuard>` in `__root.tsx` so toasts survive redirects. |
| **L9** (E.10) | `route-resolver.ts` is now pure — takes `lastWorkspace` as an argument; `auth-guard` reads `readLastWorkspace()` once and passes it. |
| **L11** (E.11) | `eslint.config.ts` ignores `src/routeTree.gen.ts` (generated code, no more `as any` lint noise). |

### New artifacts
`hooks/use-scoped-role-crud.ts`, `components/scoped-roles-page.tsx`, `components/scoped-invite-dialog.tsx`, `components/scoped-grant-manager-body.tsx`, `lib/session-cache.ts`, plus colocated tests `lib/api.test.ts`, `lib/auth.test.tsx`, `components/scoped-roles-page.test.tsx`.

### Verification
`pnpm exec turbo run lint typecheck test` — **9/9 tasks green**: ESLint 0 errors (5 pre-existing `react-refresh` warnings, out of scope), `tsc -b --noEmit` clean, **vitest 193 passed (41 files)**. No backend files touched; no `.env`. Roles-page wrappers are 12 LoC each. ESLint queryKey ban confirmed to error on an inline-literal probe.

### Deviations from spec
- Tests are **colocated** (project convention) rather than under `src/__tests__/`.
- Route loaders import the `queryClient` singleton instead of `context.queryClient` (the router has no typed context; avoids rippling into every component test's local `createRouter`).
- `qk.acceptInvite()` omits the `session.user.id` suffix — the loader removes the cached entry on error and E.1's `queryClient.clear()` already handles the cross-user concern.

PAR-C slice 2 (reconciler role) remains blocked on operator provisioning; PAR-F lands last.
