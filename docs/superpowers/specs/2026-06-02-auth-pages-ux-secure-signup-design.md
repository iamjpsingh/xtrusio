# Auth pages UX — secure-but-helpful signup, resend verification, password reset, switch links, polish

**Date:** 2026-06-02
**Branch:** `auth-ux-secure-signup-resend-reset`
**Status:** design + plan (approved by user 2026-06-02)

## Goal

Close the small auth UX gaps on the sign-in / sign-up pages **without** weakening the
non-enumeration hardening (audit C2 / PAR-A #25, reinforced by #63). User picked the
**GitHub/Slack pattern**: the UI never reveals inline whether an email exists; instead
the *email the person receives* differs.

## Decisions (locked)

1. **No inline enumeration oracle.** `POST /api/signup` returns the **identical**
   `202 confirm_email_sent` for new / existing-unconfirmed / existing-confirmed emails.
2. **Differentiated emails** (all sent via Supabase using the project's SMTP):
   - new email → `auth.sign_up` → "Confirm signup"
   - exists & unconfirmed → `auth.resend({type:"signup"})` → re-send confirm
   - exists & confirmed → `auth.reset_password_email(...)` → "Reset password" (= the
     "you already have an account" nudge)
3. **Reset email must land somewhere** → build a `/reset-password` page; this also gives
   a real **Forgot password** flow (fills a genuine gap).
4. Client-side auth keeps the existing split: signup + resend go through the **backend**
   (gated + SlowAPI rate-limited + non-enumeration). Forgot-password + reset-password use
   **supabase-js directly** on the client (recovery is not gated by `signups_enabled`),
   consistent with sign-in already using supabase-js.

> **Security note (must be in the signup.py docstring):** this deliberately re-adds
> server-side existence detection that #63 removed, BUT the client/API response stays
> identical across all branches, so the non-enumeration property C2 closed is preserved.
> The only observable difference is which email Supabase sends — not visible to an
> unauthenticated probe of the API.

## Backend (`apps/api`)

### B1. `services/signup.py` — existence-aware branching
- Add a small helper to look up the email in `auth.users` via the owner DB session:
  `SELECT id, email_confirmed_at FROM auth.users WHERE lower(email) = lower(:email) LIMIT 1`
  returning `(exists: bool, confirmed: bool)`. **Factor it into its own function** so tests
  can patch it (mirrors how `is_signups_enabled` is patched today).
- `create_signup_user` keeps the hard `signups_enabled` gate, then branches as in Decision 2.
  - new-email branch keeps the current `sign_up({..., "options": {"email_redirect_to": cfg.web_app_url}})`.
  - resend branch: `auth.resend({"type": "signup", "email": email, "options": {"email_redirect_to": cfg.web_app_url}})`.
  - reset branch: `auth.reset_password_email(email, {"redirect_to": <cfg.web_app_url>/reset-password})`.
    Verify the exact gotrue method name against the installed package (`reset_password_email`
    vs `reset_password_for_email`) before using.
- **All** Supabase calls wrapped in the existing
  `asyncio.wait_for(asyncio.to_thread(...), timeout)` → `EmailProviderUnavailableError` (→ 502).
- Returns `None` (identical response shape preserved).

### B2. `routes/signup.py` + `schemas/signup.py` — resend endpoint
- `POST /api/signup/resend` body `{ "email": EmailStr }` → calls
  `auth.resend({type:"signup", ...})` (own service fn). Always `202`. SlowAPI rate-limit
  mirroring the existing `/signup` limit (5/IP/hr). Gate behind `signups_enabled` like signup.

## Frontend (`apps/web`)

### F1. `lib/api.ts` — `postSignupResend(email)` (→ `POST /api/signup/resend`, void/202).
### F2. `lib/error-messages.ts` — add codes: `email_provider_unavailable`, `rate_limited`,
  `email_not_confirmed`, network/timeout, weak-password — friendly copy.
### F3. Sign-up page (`components/sign-up-page.tsx`)
- "Already have an account? **Sign in**" link (always).
- Success "Check your email" screen: **Resend** button (15s cooldown) + honest copy
  ("If you already have an account, we've emailed you a sign-in/reset link instead").
- Map mutation errors via the registry (502 / 429 / network / weak password).
### F4. Sign-in page (`components/sign-in-page.tsx`)
- Distinguish errors: invalid-creds vs **`email_not_confirmed`** → inline
  "**Resend verification email**" button (calls `postSignupResend`).
- Rate-limit / network messages.
- "**Forgot password?**" link → `/forgot-password`.
- Fix the awkward sign-up link (label "Create an account"; when signups disabled show
  "Have an invite?" copy instead).
### F5. `/forgot-password` route + page
- Email input → `supabase.auth.resetPasswordForEmail(email, { redirectTo: \`${origin}/reset-password\` })`
  → always show "check your email" (no enumeration). Link back to sign-in.
### F6. `/reset-password` route + page
- On mount, read the URL hash (implicit flow — client has no `flowType`, so default is
  implicit). If `type=recovery` with `access_token`/`refresh_token` → `supabase.auth.setSession(...)`.
  If the hash carries `error`/`error_code` (e.g. `otp_expired`) → show a clear "link expired,
  request a new one" state linking back to `/forgot-password`.
- New-password form (min 8, show/hide, confirm field) → `supabase.auth.updateUser({ password })`
  → success → redirect to `/sign-in` with a success note.
- Verify supabase-js recovery handling against the installed `@supabase/supabase-js`;
  do NOT flip the global `detectSessionInUrl` (handle the token locally on this route only).
### F7. Switch links everywhere (sign-in ⇄ sign-up ⇄ forgot-password) + token-only UI polish
  on both auth pages (spacing, alignment, button/focus states). Reuse `AuthLayout`.

## Tests

- **Backend** `tests/services/test_signup.py`: patch the gate + the auth-user-lookup helper;
  assert each branch (new→`sign_up`, unconfirmed→`resend`, confirmed→`reset_password_email`)
  and that `create_signup_user` returns `None` in all three (identical outcome). Keep the
  existing new-email `email_redirect_to` assertion. `tests/routes/test_signup.py`: resend
  endpoint happy path (202) + transport failure → 502.
- **Frontend** (colocated): sign-up resend button + cooldown; sign-in unconfirmed→resend;
  switch links render; `/forgot-password` submit; `/reset-password` success + expired-token states.

## Acceptance gate

- `STARTUP_RECONCILE_TOLERANT=false make check` is the authoritative gate. Because the full
  managed-Supabase backend suite is slow, the controller runs **targeted** backend tests
  (signup service + routes) + the full frontend `turbo lint typecheck test`, then an
  auth-focused code review (non-enumeration property preserved; no secrets; owner-conn
  lookup safe). mypy --strict + ruff + ruff format clean.

## Out of scope (YAGNI)

MFA/TOTP, OAuth/SAML, magic-link login, custom email-template HTML, account lockout.
