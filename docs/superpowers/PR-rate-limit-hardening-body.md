# feat(security) — rate-limit hardening: per-email signup throttle + authed catch-all + proxy-trust key

Closes the audit's rate-limit findings: `ip-keyed-ratelimit-bypass-and-email-bombing` (MEDIUM), `authed-catchall-dead` (LOW), `ratelimit-ip-key-spoof` (MEDIUM), `signin-no-app-rate-limit` (MEDIUM, doc-only).

## 1. Per-email signup throttle (email-bombing)
The only signup limit was IP-keyed (5/hr), so an attacker rotating IPs could email-bomb a known victim (secure-signup always sends mail). Added a Valkey-backed per-normalized-email throttle (`core/email_throttle.py`, mirroring `perm_cache`'s aioredis client): `INCR` on `signup_email:<sha256(normalized email)>` with a fixed TTL window (env `SIGNUP_EMAIL_WINDOW_SEC`=3600, `SIGNUP_EMAIL_MAX_PER_WINDOW`=5), checked on `/api/signup` + `/api/signup/resend` **before** the account-state branch. Fail-open on Valkey outage (the IP limit still applies). The existing IP-keyed limit is kept (per-IP AND per-email).
- **Non-enumeration preserved:** the throttle only touches the email-keyed counter — it never reads `auth.users`, never knows account state, and runs before any existence lookup. The over-limit response is a uniform `429 rate_limited` that fires purely on request count, identically for existing / unconfirmed / non-existent emails — not an oracle. A test forces the existence-lookup to "does not exist" and confirms the same 429 at the same count, with the request never reaching Supabase.

## 2. Wire the dead authed catch-all
`AUTHED_CATCHALL_RATE` was defined but never applied (slowapi only enforces `default_limits` when `SlowAPIMiddleware` is installed — it wasn't). Installed the middleware and set `default_limits=[AUTHED_CATCHALL_RATE]` (env, default `120/minute`) with a **user-keyed** main `key_func` (derives the bucket from the unverified JWT `sub` — safe, it only selects a counting bucket; a forged token still 401s at the auth gate, and the per-IP layer bounds bucket-spreading). Health probes exempted; explicit per-route limits not clobbered. Generous ceiling so legitimate dashboard bursts/reloads don't trip it.

## 3. Proxy-trust key derivation (env-configurable, safe default)
`RATE_LIMIT_TRUSTED_PROXY_HOPS` (default **0** = socket peer, XFF ignored → dev/tests unchanged). At `N>0`, the client IP is the `(N+1)`-th `X-Forwarded-For` entry counted from the **right** (what the outermost trusted proxy saw) — never the forgeable leftmost value; missing/short XFF falls back to the socket peer. **Operator:** pin uvicorn `--forwarded-allow-ips=<proxy egress>` so a direct attacker can't inject a forged XFF.

## 4. Sign-in / forgot-password posture (doc-only)
These go browser→GoTrue directly and never hit FastAPI, so slowapi can't limit them. Documented the prod requirement: Supabase GoTrue project-level auth limits + enable CAPTCHA + leaked-password protection in the dashboard. Fronting via a FastAPI proxy is out of scope.

## Operator follow-ups
Enable Supabase CAPTCHA + leaked-password protection + auth rate limits; set `RATE_LIMIT_TRUSTED_PROXY_HOPS` + `--forwarded-allow-ips` when deploying behind a CDN/proxy.

Gate: `make lint` + `make typecheck` clean; `mypy --strict` clean (208 files); 65 targeted tests green (rate-limit hardening + email-throttle + signup + me + roles). Catch-all real-world behavior covered by dedicated throwaway-app tests; the suite's autouse `_disable_rate_limiter` keeps it from tripping other tests.
