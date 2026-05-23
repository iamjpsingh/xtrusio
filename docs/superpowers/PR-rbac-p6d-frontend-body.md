# P6d frontend — platform users + workspace members list + settings + shared grant-manager

> Stacked on **#21** (P6d backend). Merge #21 first; GitHub will auto-retarget this PR's base to `main`.

The consumer half of P6d. Surfaces the three new backend endpoints from #21 through real admin UIs, plus a shared grant-manager Sheet used by both platform and workspace scopes. After this lands, the admin surface is complete: super_admins and workspace owners can do every admin action through the UI (list, view, rename, grant/revoke roles).

## Summary

- **Shared `<RolePicker>`** — single-role chooser scoped to `platform` or `workspace` via a discriminated union. Wraps shadcn `<Select>`, fetches the role list via existing P4/P5 endpoints with `staleTime: 60_000`. Used by `<GrantManagerDialog>` (and reusable elsewhere).
- **Shared `<GrantManagerDialog>`** — Sheet that opens on `[Manage roles]`. Lists existing grants with per-row revoke, plus an "Add grant" row with `<RolePicker>` + grant button. Inline footer error via `lib/error-messages`. Invalidates the relevant `qk.*` keys on grant/revoke success so list views show updated `granted_role_count` without a reload. Same component drives both platform and workspace scopes (no `if (scope === ...)` accumulation in pages).
- **`<PlatformUsersPage>`** at `/platform/users` — table `[email | role | grants | last sign in | actions]`. Gate: `platform.users.read` (renders `<Forbidden />` if missing). `[Manage roles]` per row → `<GrantManagerDialog scope="platform" />`. Cursor pagination via the existing Slice-2 `<LoadMoreButton>`. Replaces the placeholder route.
- **`<WorkspaceMembersListPage>`** embedded under Slice-3's invite UI in `<WorkspaceMembersPage>`, separated by `<Separator>`. Gate: `workspace.members.read`. Same table shape. `[Manage roles]` per row → `<GrantManagerDialog scope="workspace" />` (additionally gated by `workspace.members.manage`).
- **`<WorkspaceSettingsPage>`** at `/workspace/$wid/settings` — name editor + read-only slug + created_at. Gate: `workspace.settings.read` for view, `workspace.settings.manage` for edit. `[Save]` disabled when name is unchanged or empty (no-op submit prevention). Inline form error on 422/403 via `lib/error-messages`. Toast on success.
- **`apps/web/src/lib/api.ts`** — 4 new P6d fetchers (`fetchPlatformUsers`, `fetchWorkspaceMembers`, `fetchWorkspaceSettings`, `updateWorkspaceSettings`) + 6 P4/P5 grant fetchers added (the existing api.ts didn't expose them as standalone fetchers yet — needed for `<GrantManagerDialog>`).
- **`apps/web/src/lib/query-keys.ts`** — 7 new `qk.*` entries (alphabetical with the rest).
- **`apps/web/src/lib/error-messages.ts`** — 3 new mappings (`workspace_not_found`, `role_not_found`, `grant_not_found`).

## Architecture choices

- **Discriminated unions for scope**, not boolean flags. `<RolePicker>` and `<GrantManagerDialog>` props are `{ scope: "platform"; ... } | { scope: "workspace"; workspaceId: string; ... }`. TS narrows correctly inside each branch; no `if (workspaceId)` guards needed at the use site.
- **Shared components, per-scope pages.** No scope-parameterised page components (would accumulate `if (scope === "workspace")` over time). Follows the Slice-1 / Slice-2 reuse model.
- **Cache invalidation strategy:** `<GrantManagerDialog>` invalidates `platformRoleGrants(userId)` (or `workspaceRoleGrants(wid, userId)`) AND `platformUsers()` / `workspaceMembers(wid)` on grant/revoke. The grant count badge in the parent table re-renders automatically; no manual state plumbing.
- **`<WorkspaceSettingsPage>` save button disabled when clean** — simpler UX than enabling-but-silently-no-op'ing. If the user wants to save the same name, they don't.
- **Legacy `users-page.tsx` (platform invites UI) left in place but orphaned from the route.** Platform-invite UI wasn't in P6d scope; deleting the file is a separate cleanup. It still compiles and its own tests still pass.

## Test plan

- [x] `pnpm --filter @xtrusio/api-types typecheck` — clean
- [x] `pnpm --filter @xtrusio/web typecheck` — clean
- [x] Focused `eslint` over all 11 slice files + 6 test files — clean (no warnings/errors)
- [x] `pnpm --filter @xtrusio/web exec vitest run` — **39 test files, 178 tests, all passing**
- [ ] Full `STARTUP_RECONCILE_TOLERANT=false make check` — **deferred to a single end-of-P6d gate** by the controller after both #21 and this PR merge.
- [ ] Manual: super_admin lists platform users at `/platform/users`; sees grant count per row; opens `<GrantManagerDialog>` and grants/revokes a role; counts update without reload.
- [ ] Manual: workspace owner sees the LIST section under invite UI at `/workspace/<wid>/members`; same grant flow works for workspace scope.
- [ ] Manual: workspace owner renames the workspace at `/workspace/<wid>/settings`; audit log row appears; Save disabled when name is unchanged.
- [ ] Manual: an editor (without `workspace.settings.manage`) can view settings but inputs are disabled / save absent.
- [ ] Manual: privilege-escalation guard surfaces a friendly error when trying to grant a perm you don't have (already covered by service-layer P4/P5; this is just the UI mapping).

## Deviations from the plan

1. **Legacy `users-page.tsx` not deleted.** The plan said "replace the route" — it didn't say to delete the legacy file. Platform-invite UI isn't in P6d scope; cleanup is out.
2. **Save-button disabled-when-clean.** The plan offered "no-op submit (button stays enabled / disabled — pick simpler)". Disabled is the simpler UX; the rest of the project's forms use it.
3. **Re-staged after prettier reformat.** Per project rules (no `--amend`), I re-staged + re-committed after the pre-commit hook reformatted the working tree. One clean commit `c49ded2` ended up on the branch.

## What's NOT in this PR

- Backend endpoint implementations — **#21**.
- Workspace slug change / deletion — explicitly out of scope.
- ETag/If-Match concurrency on settings — explicitly out of scope.
- Audit-log filters or search — explicitly out of scope.
- Realtime push of grant/revoke events — explicitly out of scope.
- Cleanup of legacy `users-page.tsx` (platform invites UI) — out of scope; future polish.

## Next

End-of-night controller-run full `make check` once #21 + this PR both merge, then HANDOFF.md update pivoting NEXT to **"first product feature"**. The admin surface is now complete.
