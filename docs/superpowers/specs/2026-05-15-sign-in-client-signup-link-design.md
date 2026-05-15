# Spec — Conditional "Client sign up" link on the sign-in page

**Date:** 2026-05-15
**Branch:** `plan-2-settings-signup-invites`
**Status:** Approved (design), pending spec review

## Problem

The sign-in page has no path to self-serve signup. New **client organizations**
have no discoverable entry point unless they already know the `/sign-up` URL.

## Core invariant (non-negotiable)

Self-serve signup is **client-only**. It creates a Supabase auth user and, via
onboarding, a **new tenant (organization)** with the signer as `TenantRole.OWNER`.
It can **never** create a `platform_user` / grant any `PlatformRole`.

Platform users (super_admin / platform staff) are created **only** by:
- the bootstrap CLI (first owner), or
- a super_admin invite/create (Plan 2B).

Verified true in the backend today:
- `services/signup.py::create_signup_user` → Supabase auth user only; gated by
  `is_signups_enabled(db)`. No `platform_users` write.
- `services/onboarding.py::create_tenant_with_owner` → `Tenant` +
  `TenantMembership(role=OWNER)` only. No `platform_users` write.

This spec must not weaken that. The link is a surface for the **existing**
client path; it introduces no new account-creation capability.

## Behavior

1. `sign-in` queries signup status via the existing
   `useQuery({ queryKey: ["signup-status"], queryFn: fetchSignupStatus })`
   (same key as the sign-up page → shared cache, one request).
2. Render the link **only when `status.signups_enabled === true`**.
   - Loading, `false`, or query error → render nothing (sign-in unchanged;
     invite-only). **Fail-closed**: never show the link on an unconfirmed status.
3. When shown: one quiet line directly under the "Sign in" button, inside the
   card:

   > New organization? **Client sign up** → `/sign-up`

   Wording is **organization/client-oriented** on purpose so no platform user
   ever mistakes it for their entry point. Not a bare "Create account".
4. Link uses TanStack `<Link to="/sign-up">`. `/sign-up` keeps its own
   `signups_enabled` gate (defense in depth — the link is a convenience, not
   the access control).

## Enable/disable ownership

Only a **platform super_admin** flips `signups_enabled` in `/settings`. The
link's visibility is a pure function of that platform-controlled flag. Default
is **off** → no link → invite-only platform.

## Styling

Matches the existing dark card vocabulary: `text-sm text-muted-foreground`,
"Client sign up" as a `text-foreground` link with hover underline. No new
shadcn components, no layout/spacing changes, no aurora. Keep auth page simple.

## Component structure & testing

`sign-in` is currently a direct route file (`routes/sign-in.tsx`) with no test.
Follow the established split pattern (HANDOFF gotcha #4, as used by
`sign-up-page`):

- `components/sign-in-page.tsx` — the real component.
- `routes/sign-in.tsx` — 3-line wrapper:
  `createFileRoute("/sign-in")({ component: SignInPage })`.
- `components/sign-in-page.test.tsx` — mirror `sign-up-page.test.tsx`:
  - `signups_enabled: true` → "Client sign up" link present, points to `/sign-up`.
  - `signups_enabled: false` → link absent.
  - (optional) query error → link absent (fail-closed).

## Out of scope (YAGNI)

Forgot-password, SSO, social login, any platform-user self-registration,
any change to the signup/onboarding backend.

## Acceptance

- Backend unchanged; invariant above still verifiably true.
- `make check` green (50 backend / frontend tests + new sign-in-page tests),
  zero new mypy/ruff/eslint errors over baseline.
- Manual: signups OFF → no link on `/sign-in`; super_admin enables in
  `/settings` → link appears → leads to client `/sign-up` → org onboarding.
