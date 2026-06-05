# fix(invite) — repair the dead invite-acceptance flow

Closes audit finding `invite-flow-broken-no-session` (HIGH, functional). Invite-based onboarding — the only path when public signups are off — was completely dead.

## The bug
`supabase.ts` sets `detectSessionInUrl: false`, and `invite_outbox.py` called `invite_user_by_email(email)` with no `redirect_to`. So GoTrue's invite link returned a token in the URL hash that nothing consumed → the invitee got no session → the auth gate bounced them to `/sign-in` → they could never reach an authenticated `/accept-invite` to POST acceptance.

## Fix
- **Consume the invite hash before accepting** (`routes/accept-invite.tsx`): the loader now parses `#access_token&refresh_token&type=invite|signup`, calls `supabase.auth.setSession(...)`, scrubs the hash, THEN runs the existing accept POST — mirroring the already-shipped reset-password recovery-hash handler, without flipping the global `detectSessionInUrl`. An `error_code`/missing-token/`setSession`-failure hash routes to the existing "couldn't accept your invite" surface (`invite_expired`). The accept-fires-exactly-once property (M12) is preserved by keeping it in the loader.
- **Make `/accept-invite` reachable sessionless** (`lib/route-resolver.ts`): added to the `PUBLIC` set (like `/reset-password`) so the invitee isn't redirected before the hash is consumed; once `setSession` lands, `UNGATED_AUTHED` keeps it renderable.
- **Land the invite on the right route** (`invite_outbox.py`): `invite_user_by_email(email, options={"redirect_to": f"{web_app_url}/accept-invite"})` (verified gotrue-py `InviteUserByEmailOptions.redirect_to`).

## Operator step (required)
Add `<WEB_APP_URL>/accept-invite` to Supabase → Authentication → URL Configuration → **Redirect URLs**, else GoTrue ignores `redirect_to` and falls back to the Site URL (re-breaking the flow). Same constraint already noted for `/reset-password`.

## Tests
8 loader tests (valid invite/signup hash → setSession + scrub + POST + redirect; error_code → no POST; setSession failure → error; no-hash → POST directly; already_provisioned → redirect) + a route-resolver sessionless-renders test + a backend test asserting the `redirect_to` kwarg.

Gate: `make lint` + `make typecheck` clean; `mypy --strict` clean; full web vitest **304**; `test_invite_outbox` 4/4. True end-to-end (real inbox → hash → session → accept) is user-driven.
