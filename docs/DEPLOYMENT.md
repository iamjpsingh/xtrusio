# Deployment & Operator Runbook

Single source of truth for every **config/operator action** needed to run Xtrusio
in production (and to fully activate a few features in any hosted environment).
Every step is copy-paste. Steps tagged **[DEV-OK]** also matter for a *hosted*
dev environment; pure-local dev (API on `127.0.0.1`) doesn't need them.

**Architecture recap:** host FastAPI API + workers · managed Supabase (Postgres +
Auth + Realtime) · Cloudflare Pages (web) · Valkey (rate-limit + perm cache —
**required**, no in-memory fallback). See `docs/superpowers/ENGINEERING_PRINCIPLES.md`.

> All values below go in the **prod environment** (systemd/Docker/host env), never
> committed. The app **fails to boot** in prod on a weak/placeholder `CURSOR_HMAC_KEY`
> or `AUTH_WEBHOOK_SECRET` (`XTRUSIO_ENV=prod` enforces this).

---

## 0. Prerequisites

- A managed Supabase **prod** project (separate from dev). Note its **ref** and
  connection strings (Settings → Database).
- API + workers deployed to a host with a **public HTTPS URL**, behind a proxy/CDN.
- Valkey reachable from the API (`VALKEY_URL`).
- `XTRUSIO_ENV=prod`, `STARTUP_RECONCILE_TOLERANT=false` set in the prod env.
- `gh` CLI authed with repo admin — only needed for section 7 (CI), which is deferred.

---

## 1. Generate prod secrets

```bash
# CURSOR_HMAC_KEY  — signs pagination cursors (rotate from the dev value)
python -c "import secrets; print('CURSOR_HMAC_KEY=' + secrets.token_hex(32))"

# AUTH_WEBHOOK_SECRET — the only gate on the auth-event ingest endpoint (section 5)
python -c "import secrets; print('AUTH_WEBHOOK_SECRET=' + secrets.token_hex(32))"
```

Put both in the prod env. (Local dev keeps its placeholders — the weak-secret
check only fires when `XTRUSIO_ENV=prod`.)

---

## 2. Run database migrations

Point the env at the **prod** `DATABASE_URL`, then:

```bash
make migrate          # alembic upgrade head  → head is 0014 (job_runs)
```

Idempotent; safe to re-run on every deploy. Verify with
`uv run --directory apps/api alembic current` → `0014`.

---

## 3. Rate-limiting behind a proxy/CDN  [DEV-OK if hosted]

SlowAPI keys limits by client IP. Behind N trusted proxy hops, set:

```bash
# in the prod env — number of trusted proxies in front of the app
RATE_LIMIT_TRUSTED_PROXY_HOPS=<N>
```

And start uvicorn so it only honours `X-Forwarded-For` from your proxy's egress
IP(s) (otherwise an attacker can forge XFF to mint unlimited buckets):

```bash
uvicorn xtrusio_api.main:app --host 0.0.0.0 --port 8000 \
  --app-dir apps/api/src \
  --forwarded-allow-ips="<proxy egress IP(s), comma-separated>"
```

Directly exposed (no proxy) → leave `RATE_LIMIT_TRUSTED_PROXY_HOPS=0` and omit
the flag.

---

## 4. Supabase auth configuration  [DEV-OK]

Dashboard → **Authentication**. (Management-API equivalents in the callout below
for IaC.)

1. **URL Configuration → Redirect URLs** — add both, else invite/reset links
   fall back to the Site URL:
   - `<WEB_APP_URL>/accept-invite`
   - `<WEB_APP_URL>/reset-password`
2. **Providers → Email** — enable **Confirm email**, and configure **custom SMTP**
   (the built-in sender is rate-limited/unreliable). Without this, signup/confirm
   emails never arrive even though the code requests them.
3. **Attack Protection** — enable **CAPTCHA** (hCaptcha/Turnstile) and
   **leaked-password protection** (HaveIBeenPwned).
4. **Rate Limits** — set GoTrue's project-level auth rate limits (sign-in,
   sign-up, token, recovery). FastAPI can't rate-limit sign-in/forgot-password —
   those go browser→GoTrue directly — so this is the only control for them.

> **IaC alternative (needs a Supabase personal access token):**
> ```bash
> curl -X PATCH "https://api.supabase.com/v1/projects/<PROJECT_REF>/config/auth" \
>   -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
>   -H "Content-Type: application/json" \
>   -d '{
>     "uri_allow_list": "<WEB_APP_URL>/accept-invite,<WEB_APP_URL>/reset-password",
>     "mailer_autoconfirm": false,
>     "external_email_enabled": true,
>     "smtp_host": "...", "smtp_port": 465, "smtp_user": "...",
>     "smtp_pass": "...", "smtp_sender_name": "Xtrusio",
>     "smtp_admin_email": "noreply@xtrusio.org",
>     "security_captcha_enabled": true,
>     "password_hibp_enabled": true
>   }'
> ```
> Field names vary by Management-API version — if a field 422s, set it in the
> Dashboard instead. (See memory: SMTP via GoTrue, sender `noreply@xtrusio.org`,
> port 465, app password kept WITH spaces.)

---

## 5. Auth-event capture webhook  (feature #77)  [DEV-OK if hosted]

Lights up the activity feed's `auth` category. Needs the API reachable at a
public URL (Supabase cloud POSTs to it).

1. Ensure `AUTH_WEBHOOK_SECRET` (from section 1) is set in the API env and the API is
   restarted.
2. **Dashboard → Database → Webhooks → Create a new hook:**
   - Table: `auth.audit_log_entries` · Events: **Insert**
   - Type: **HTTP Request** · Method: **POST**
   - URL: `<API_BASE_URL>/api/internal/auth-events`
   - HTTP Header: `X-Webhook-Secret` = `<the AUTH_WEBHOOK_SECRET value>`

   *IaC alternative:* edit + run `scripts/deploy/auth-event-webhook.sql` (same
   trigger, for repeatable setup).
3. **Verify:** sign in via the web app, then as an operator
   `GET /api/platform/audit-log?category=auth` — you should see a `auth.login`
   row (`action_label = "Signed in"`). A curl smoke-test of the endpoint itself
   is in `.env.example`.

> **Decision still open:** GoTrue fires `token_refreshed` ~hourly per active user.
> It's captured for completeness and will make the feed noisy. To drop it, skip
> it at ingest in `apps/api/src/xtrusio_api/routes/internal_auth_events.py` (one
> line, optionally env-driven). Decide before going live if a noisy feed bothers you.

---

## 6. PAR-C reconciler role  (prod hardening — optional, gated on a smoke-test)

The boot/seed reconcile can run as a least-privilege role instead of the owner
connection. **Until smoke-tested, leave `RECONCILE_DATABASE_URL` unset** — the
default (request-engine) fallback is safe and correct.

1. Give the role a login (migration `0013` created it `NOLOGIN`, no credential).
   Edit + run `scripts/deploy/reconciler-role.sql` (replace the password).
2. Set in the prod env:
   ```bash
   RECONCILE_DATABASE_URL=postgresql+asyncpg://xtrusio_reconciler:<PW>@db.<PROJECT_REF>.supabase.co:5432/postgres
   ```
3. **Smoke-test live** (this path can't be validated in dev — there reconcile
   runs as owner and the `TO xtrusio_reconciler` RLS policies are inert): boot
   with `RECONCILE_DATABASE_URL` set and confirm the reconcile **reads non-zero
   rows and its writes succeed** (logs: `rbac_reconcile_*`). If anything reads 0
   rows or fails a write → unset the var and fall back. Supavisor custom-role
   connectivity is unverified, so test before relying on it.

---

## 7. CI / Dependabot  (⚠️ DEFERRED by policy — do last)

> Standing rule (`feedback_ci_cd_after_local.md`): **defer all CI/CD until local
> dev is fully working.** Skip this section until you choose to un-defer it.

The workflows exist (`.github/workflows/*`) but Actions is paused. To turn them
on you need the `xtrusio-ci` managed-Supabase test-project secrets:

```bash
gh secret set CI_DATABASE_URL          --body "<...>"
gh secret set CI_SUPABASE_URL          --body "<...>"
gh secret set CI_SUPABASE_ANON_KEY     --body "<...>"
gh secret set CI_SUPABASE_SERVICE_ROLE_KEY --body "<...>"
gh secret set CI_SUPABASE_JWKS_URL     --body "<...>"
```

Then re-enable Actions (repo **Settings → Actions → General → Allow all**, or
`gh api -X PUT repos/iamjpsingh/xtrusio/actions/permissions -f enabled=true`).
The ephemeral-Postgres CI job + the `api-types-drift` gate run without secrets;
the managed-Supabase, e2e, and security jobs stay advisory until the secrets land.

---

## Quick checklist

```
[ ] 1. CURSOR_HMAC_KEY + AUTH_WEBHOOK_SECRET generated & set in prod env
[ ] 2. make migrate  (→ alembic head 0014)
[ ] 3. RATE_LIMIT_TRUSTED_PROXY_HOPS + uvicorn --forwarded-allow-ips (if proxied)
[ ] 4. Redirect URLs + Confirm-email + SMTP + CAPTCHA + leaked-pw + GoTrue rate limits
[ ] 5. Auth-event webhook wired + verified in ?category=auth   (decide on token_refreshed)
[ ] 6. Reconciler role smoke-tested  (optional; leave RECONCILE_DATABASE_URL unset until then)
[ ] 7. CI secrets + re-enable Actions   (only when un-deferring CI)
```
