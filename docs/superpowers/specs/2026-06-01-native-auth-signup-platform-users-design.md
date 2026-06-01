# Design — Native signup + platform-user provisioning

**Date:** 2026-06-01
**Status:** APPROVED (user-confirmed)
**Branch:** `native-auth-signup-platform-users`

## Problem

Signup sent no verification email — `services/signup.py` used `admin.create_user(email_confirm=False)`, which provisions an unconfirmed `auth.users` row but **sends nothing**. Fixing it surfaced a broader auth-model decision, now settled.

## Confirmed model

| Actor | How they get in | Lane |
|---|---|---|
| **Client (self-service)** | Public signup → confirm email → onboarding creates THEIR tenant/workspace, they're OWNER | only when the `signups_enabled` toggle is ON |
| **Client's org users** | Tenant invite from a workspace owner/admin (exists) | invite only |
| **Platform user (staff)** | super_admin **invite** OR super_admin **direct-create (id+password)** OR CLI bootstrap | NO public signup, ever |

**Hard rule:** public signup can NEVER create a `platform_users` row. (Already true — `platform_users` is written only by `invite_acceptance._accept_platform`, the new direct-create, and the CLI. Signup only creates `auth.users` → onboarding → client.)

## Changes

### 1. Signup → native `sign_up`, hard-gated by the toggle (`services/signup.py`)
- The route stays a **thin backend gate** (a browser-only `signUp` can't be hard-disabled by an app DB toggle).
- `create_signup_user`: if `is_signups_enabled(db)` is **False → raise `SignupsDisabledError` (403)** — no signup at all.
- If True → create an **anon-key** Supabase client (`supabase_anon_key`) and call `sb.auth.sign_up({"email", "password"})`. This is the native flow: it creates the unconfirmed user AND triggers Supabase's confirmation email, and **obfuscates already-registered emails** (non-enumeration) natively.
- **Remove** the `admin.create_user` call, the `EmailTakenError` detection, and the `_send_password_reset` fallback — `sign_up` covers non-enumeration. Keep the route's SlowAPI rate-limit (5/IP/hr) and the always-202 `confirm_email_sent` response.
- Map a `sign_up` transport/timeout failure → `EmailProviderUnavailableError` (502), as today.
- **Delivery caveat:** this fixes the CODE (an email is now actually requested). Whether it lands still depends on the Supabase project having **"Confirm email" enabled + a working email sender** (built-in is rate-limited; prod needs SMTP) — operator config, documented in HANDOFF.

### 2. NEW — super_admin direct-create platform user
- **Route** `POST /api/platform/users` (super_admin-gated via `require_permission(..., "platform.users.manage")` — and pin to super_admin where the existing invite route does). Body: `email`, `password`, `role` (`admin` only — `super_admin` stays CLI/seed-pinned per the 0010 single-super_admin invariant). **Service-role** `admin.create_user({email, password, email_confirm: True})` (mirror `scripts/bootstrap.py:84`) → insert `platform_users` row → `grant_role(scope="platform", key="admin")`. Caller-owns-tx; handle the email-exists / already-provisioned conflict as a typed 409.
- **Schema** `PlatformUserCreate` (in/out). Regenerate api-types.

### 3. Surface BOTH paths in the UI (platform users page)
- An **"Add platform user"** affordance with two actions: **Invite** (existing `postPlatformInvite` + the `scoped-invite-dialog` or a platform variant) and **Create directly** (new endpoint — email + password + role). Both gated behind `platform.users.manage` (super_admin in practice). Monochrome, tokens only, the pass-1 states.

### Unchanged (already native/correct)
Login / logout / session (frontend `signInWithPassword`), password reset, tenant + platform invites' send mechanism (`invite_user_by_email`). Identity linking: NOT added (only needed if/when OAuth providers are added).

## Tests
- Backend: signup gated off → 403; gated on → `sign_up` invoked (mock the Supabase client, assert `sign_up` called, NOT `admin.create_user`); direct-create → creates platform_users + grant, super_admin-gated (403 for non-super_admin), 409 on duplicate email. `@example.com` hygiene, no test creates a real super_admin.
- Frontend: the add-platform-user dialog (invite + create paths) renders/validates/submits; signup form unchanged.

## Constraints
mypy --strict, ruff (+format), no hardcoded config/colors, TS only, service-role key server-only, 500 LoC/file, no co-author trailer. Lean cadence: backend dispatch (signup + direct-create + api-types + backend tests) → frontend dispatch (UI + tests); controller gates each.
