# Auth pages UX — secure-but-helpful signup, resend verification, password reset, switch links, polish

Closes the small auth UX gaps on the sign-in / sign-up pages **without weakening the
non-enumeration hardening** (audit C2 / PAR-A #25, reinforced by #63). Design +
plan: `docs/superpowers/specs/2026-06-02-auth-pages-ux-secure-signup-design.md`.

## What & why

User picked the **GitHub/Slack pattern**: the UI never reveals inline whether an email
exists; the *email the person receives* differs instead.

### Backend (`apps/api`)
- **Existence-aware signup, identical response.** `services/signup.create_signup_user`
  looks up the email in `auth.users` (owner session, parameterized, case-insensitive)
  and branches: **new** → `auth.sign_up` ("Confirm signup"), **exists+unconfirmed** →
  `auth.resend(type=signup)` (re-send confirm), **exists+confirmed** →
  `auth.reset_password_email` ("Reset password" = the *you-already-have-an-account*
  nudge, landing on `/reset-password`). Returns `None` in **every** branch; the route
  always answers `202 confirm_email_sent`. No client/API oracle — the only difference is
  which email Supabase sends. (Deliberately re-adds server-side existence detection that
  #63 removed, but keeps the response identical; documented in the module docstring.)
- **`POST /api/signup/resend`** (SlowAPI 5/IP/hr, `signups_enabled`-gated) powers the
  resend buttons.
- **Uniform GoTrue error handling (review fix, `a87bdf9`).** `_send_via_supabase` now
  catches `AuthApiError`/`AuthError`, not just transport errors. The blind resend path
  **swallows** 4xx (e.g. already-confirmed → identical 202); every other path collapses
  to `502 email_provider_unavailable`. Without this, a 4xx escaped as a **500**, which on
  the unauthenticated resend endpoint was a real **500-vs-202 enumeration oracle**.

### Frontend (`apps/web`)
- **Sign-up:** "Already have an account? Sign in" link; success screen Resend button
  (15s cooldown) + honest copy; errors mapped (502/429/network/weak-password).
- **Sign-in:** distinguishes invalid-creds vs `email_not_confirmed` (→ inline **Resend
  verification email**); rate-limit/network messages; **Forgot password?** link; fixed
  the awkward sign-up link.
- **`/forgot-password`** → `resetPasswordForEmail` (origin-derived redirect, no
  enumeration). **`/reset-password`** → parses the recovery hash locally (does **not**
  flip the global `detectSessionInUrl:false`), `setSession` → new-password form →
  `updateUser` → sign-out → `/sign-in`; expired/invalid link → "request a new one".
- Switch links everywhere; token-only UI/UX polish on both pages.

## Security review

Reviewed by a security-focused Opus pass (verdict: FIX-THEN-SHIP → fix applied). Confirmed
clean: the `auth.users` lookup (parameterized, owner-role, leaks nothing to the client),
recovery-token handling (no token logging, no open redirect, expired handled), CLAUDE.md
compliance (TS-only, design tokens, env-driven config, mypy-strict, LoC ceiling), and no
regression to existing sign-in / `signups_enabled` gate / accept-invite / route-resolver.

## Testing

- Backend (targeted, vs managed Supabase): `tests/services/test_signup.py` +
  `tests/routes/test_signup.py` — **17 passed**. Covers all three signup branches return
  identical `None`/202, resend swallows 4xx (already-confirmed → 202), confirmed-branch
  4xx → 502 (not 500), transport → 502. `ruff` + `ruff format` + `mypy --strict` clean.
- Frontend: `turbo run lint typecheck test --filter=@xtrusio/web` green (47 files, 247
  tests).
- Full backend suite not run end-to-end (managed-Supabase slowness; same targeted method
  as PAR-A…F).

## 🔴 Operator action required for this to work end-to-end

In the Supabase project (Authentication → URL Configuration):
1. **Redirect URLs** → add `http://localhost:5173/**` (and the prod origin). GoTrue
   ignores `email_redirect_to`/reset `redirect_to` unless allow-listed.
2. **Site URL** → set to `http://localhost:5173` (currently a stale `:3000`).
3. **Custom SMTP** (Authentication → Emails) — the built-in mailer is rate-limited and
   times out; required for reliable confirm/reset delivery.
