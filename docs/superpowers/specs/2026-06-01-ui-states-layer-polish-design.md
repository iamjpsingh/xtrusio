# Design — UI States-Layer Polish (pass 1)

**Date:** 2026-06-01
**Status:** APPROVED — first UI/UX polish pass (not part of the PAR security audit; product work)
**Branch:** `ui-states-layer-polish`

## Goal

Take the post-login interior from "engineering demo" to genuine enterprise-SaaS quality by fixing the **states layer** — the loading / error / empty moments that currently read as cheap (bare `Loading…` text, silent `return null`, ad-hoc one-off markup). App-wide, **monochrome** (no new colors), design-tokens only.

The bones are already good: two structurally-identical shells (platform + workspace) with a sidebar + sticky topbar, a shared `EmptyState` + `Forbidden`, 24 shadcn/Radix primitives, Tailwind v4 semantic tokens, `motion` already wired (used on auth). The interior reads flat only because its transient states are unpolished.

## Scope IN

1. **Shaped skeleton loaders** — content matches what it's loading:
   - `TableSkeleton` (configurable rows/columns) for the data tables.
   - `PageSkeleton` / section skeletons (header block + content) for forms and detail pages.
   - Reuses the existing `components/ui/skeleton.tsx` (shadcn pulse).
2. **`ErrorState` (+ retry)** — shared component in the same dashed-card idiom as `EmptyState`/`Forbidden`, with a **Retry** button wired to the query's `refetch`. Plus a TanStack Router `defaultErrorComponent` so a thrown query renders this instead of blanking.
3. **`EmptyState` standardization** — replace the hand-rolled duplicates so every empty surface is identical.
4. **Two dashboards** (`/platform` index, `/workspace/$id` index) → intentional, polished empty/zero states (NO demo data — real metrics are a later pass).
5. **Light craft pass** local to the states: one consistent spacing rhythm, subtle surface depth so tables/cards don't read flat, restrained skeleton motion. Tokens only.

## Target inventory (every post-login surface gets all 4 states: loading · error · empty · data)

| Surface | File | Current loading | Target |
|---|---|---|---|
| AuthGuard (full-screen) | `components/auth-guard.tsx:43` | bare `Loading…` | branded full-screen loader/skeleton |
| Platform Clients | `routes/_app.platform.clients.tsx` | partial skeleton | `TableSkeleton` + `ErrorState` |
| Platform Users | `components/platform-users-page.tsx` | renders empty during fetch | `TableSkeleton` + `ErrorState`; use shared `EmptyState` |
| Platform Roles | `routes/_app.platform.roles.tsx` | — | `TableSkeleton` + states |
| Platform Audit log | `routes/_app.platform.audit-log.tsx` | — | `TableSkeleton` + states |
| Platform Dashboard | `routes/_app.platform.index.tsx` | placeholder | polished empty/zero state |
| Platform Settings | `routes/_app.platform.settings.tsx` | — | `PageSkeleton` + `ErrorState` |
| Workspace Members | `components/workspace-members-page.tsx` | ad-hoc "No invitations yet" | `TableSkeleton` + shared `EmptyState` + `ErrorState` |
| Workspace Roles | `routes/_app.workspace.$workspaceId.roles.tsx` | — | `TableSkeleton` + states |
| Workspace Audit log | `routes/_app.workspace.$workspaceId.audit-log.tsx` | — | `TableSkeleton` + states |
| Workspace Overview | `routes/_app.workspace.$workspaceId.index.tsx` | placeholder | polished empty/zero state |
| Workspace Settings | `components/workspace-settings-page.tsx:68,75` | bare `Loading…` / "couldn't load" | `PageSkeleton` + `ErrorState` (retry) |
| role-picker combobox | `components/grants/role-picker.tsx:131` | bare `Loading roles…` | inline skeleton rows |

## Quality bar (testable in the live app)

- **Zero** bare `Loading…` / silent `null` on any post-login surface.
- Every list/table/form page handles **all four states**.
- One spacing rhythm; subtle depth; no flat-on-flat surfaces.
- Monochrome only · design tokens only · forced-theme routes stay full-bleed · TypeScript only · no hardcoded colors.

## Scope OUT (explicit)

No new/brand colors · no real dashboard metrics · no sidebar/topbar redesign · no new features · no backend or data-model changes · auth pages untouched (already the most polished) · mutation button-label loaders stay as-is (already consistent).

## Rollout order (test in chunks)

1. Primitives: `TableSkeleton`, `PageSkeleton`, `ErrorState` + router error boundary; standardize `EmptyState`.
2. Platform pages (Clients, Users, Roles, Audit log, Dashboard, Settings).
3. Workspace pages (Members, Roles, Audit log, Overview, Settings).
4. `AuthGuard` full-screen loader + `role-picker`.

## Constraints / facts

- Tailwind v4, shadcn/Radix, lucide icons, `motion` (Motion for React), TanStack Router + Query, sonner toasts. **No new dependencies** → no `make dev` restart needed.
- Cadence per CLAUDE.md: one Opus subagent for the whole slice + ship it; controller runs the typecheck/lint gate once at the end; no vitest run (user tests the live UI first, then I verify by code).
