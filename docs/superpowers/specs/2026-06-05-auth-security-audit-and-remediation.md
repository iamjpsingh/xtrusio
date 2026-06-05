# 2026-06-05 — Auth + UX deep audit and remediation plan

Two deep read-only audits were run (18 Opus agents total, adversarial exploitability verification on every High finding). This is the durable record; remediation ships as one branch+PR per slice.

## Audit 1 — UX / auth-session / surfaces (6 investigators + 2 verifiers)

| Area | Worst finding | Severity |
|---|---|---|
| 401-after-login storm | `resolveSession()` returns the store token with **no expiry check/refresh** once `status==='authenticated'`; near/just-expired token is sent → 401. Paired 401s = `performFetch` single refresh-and-retry (not React Query). Data queries have **no `enabled: session-ready` guard**; route `beforeLoad` calls `fetchMe` outside the AuthGuard render gate (+ on intent-preload). Backend `get_current_user` returns **401 "user not provisioned"** for a valid JWT lacking a `platform_users` row (should be 403) — bites onboarding users ("feels like it checks signup stage"). | critical |
| Clients page | `GET /api/tenants` returns paginated `{items,next_cursor}` but the page types it as `Tenant[]` → `data.map is not a function` → **always empty**. No row→detail link. Per-client page resolves tenant from `me.tenants` → blank for a non-member platform admin. | critical |
| Audit-log UI/data | Raw tokens (`platform_role.grant`), **no Role column**, raw `toLocaleString`, actor em-dash fallback. grant/revoke store only `role_key`, not the human name. | high |
| Activity coverage | Only 11 RBAC actions logged; ~75% of mutations (invites, onboarding, provisioning, settings) unlogged; no auth events (GoTrue owns them); no nav telemetry. | high |
| Create-role modal | No `max-height`/scroll; flat unstructured list; machine key shown as primary label; add-only "Select all". Tokens are clean (no hardcoded colors). | critical (UX) |
| Broad | 403 rendered as a forever-looping "Try again"; 429 body shape inconsistent (`{error}` vs `{detail,request_id}`); `useMe` no enabled guard; breadcrumb full-page reload; search "Plan 1E" placeholder shipped. | high |

**Decided product direction:** Activity log + Audit log = ONE feed with filters (security/auth/activity categories). Keep infra/server logs (the terminal `INFO:` lines) and a **worker/system log** as separate operational layers. Worker/system log to grow into AI-scan / scheduling / job-queue (~70% foundation already exists: structlog + `invite_email_outbox` state table).

## Audit 2 — Auth security deep audit (6 investigators + 2 research + exploitability verification)

**🟢 Cross-tenant data separation is SOLID — no IDOR.** Every workspace route binds `require_permission(..., workspace_id=<path>)` → `has_workspace_perm(uid, tid, key)` with `WHERE ur.workspace_id = tid`. Tenant-A user → 403 on tenant-B data. RLS is correct defense-in-depth.

**Signup "existing email → reset link" is CORRECT and intentional** (non-enumeration; WorkOS/Clerk/Supabase/OWASP-endorsed). No duplicate account is created (confirmed branch calls `reset_password_email`, not `sign_up`). Legitimate gripe is UX clarity only.

| Finding | Cat | Severity | Status |
|---|---|---|---|
| **Role-edit privilege escalation** — create/update role had no "you-cannot-grant-what-you-lack" check; grant path did. Verified **exploitable**. | vuln | HIGH | ✅ **FIXED #65 (`b3ec633`)** |
| **Invite flow dead** — `detectSessionInUrl:false` + `invite_user_by_email` with no `redirect_to` + no hash consumption on accept-invite → invitee never gets a session. Verified real (fails closed, not a vuln). | bug | HIGH (functional) | ▶ slice 2 |
| Weak `CURSOR_HMAC_KEY` (`dev-only-change-me…`) shipped in live `.env` → forgeable cursors | vuln | MEDIUM | planned |
| Tokens (access+refresh) in `localStorage` → XSS = full takeover | design | MEDIUM | **DECISION PENDING** (cookie migration vs CSP/HSTS/short-TTL mitigation) |
| No security headers (HSTS/CSP/nosniff/X-Frame/Referrer) | bpg | MEDIUM | planned |
| Sign-in / forgot-password have NO app-layer rate limit (browser→GoTrue direct) | warning | MEDIUM | planned |
| Rate limiter keyed by raw IP → proxy collapse (self-DoS) or XFF spoof behind CF | warning | MEDIUM | planned |
| Signup timing side-channel (3 branches, different latency) partially re-opens enumeration | vuln | MEDIUM | planned |
| `require_super_admin` reads `platform_users.role` enum; authz reads `user_roles` (divergent SoT) | design | MEDIUM | planned |
| `app.bypass_priv_escalation` GUC honored by 0009/0010 triggers from any role | design | MEDIUM | tied to deferred reconciler-role rework |
| Auth-page footer flicker ("Have an invite?"→"Create an account") — loading race on **sign-in** page | bug | LOW | slice (UX) |
| Confirmed-signup no auto-login; sign-in `email_not_confirmed` enumeration oracle; verbose 401 leak; dead `AUTHED_CATCHALL_RATE` | mixed | LOW | planned |

**SaaS research takeaways:** keep secure-but-helpful signup; app-layer-primary + RLS defense-in-depth is correct; JWKS verification is correct. Biggest real gaps = localStorage tokens (move to httpOnly cookies), enforce you-cannot-grant-what-you-lack (now fixed), keep access-token TTL short, invite tokens single-use/email-bound, add per-email rate limit + CAPTCHA + leaked-password (HIBP) protection.

## Remediation slices (branch + PR each, off `main`)

1. ✅ **#65** — role-edit priv-esc (service-layer actor-holds-resulting-perms check + sanitized 403 + tests). DB-trigger defense-in-depth deferred (entangled with reconciler-role rework).
2. ▶ **Invite flow repair** — hash-consumption shim on accept-invite (mirror reset-password) + `redirect_to` on `invite_user_by_email` + e2e test.
3. 401-after-login race — `resolveSession` expiry-refresh + `enabled` guards + `beforeLoad` + 401→403 backend semantics + suppress error-flash.
4. Hygiene batch — rotate HMAC key + boot assertion; security-headers middleware; opaque 401 codes.
5. Rate-limit hardening — proxy-trust/XFF pinning, app-layer limits on sensitive flows, per-email limit, wire authed catch-all.
6. Signup/sign-in UX — flicker fix, clearer "already registered" copy, collapse `email_not_confirmed` oracle.
7. Clients page; 8. Create-role modal; 9. Unified Activity=Audit feed (+coverage +GoTrue auth-event hook); 10. Worker/system log; 11. Broad UI cleanup.

**Open decision:** localStorage → httpOnly-cookie session (highest-leverage hardening; touches the whole auth client). In scope now, or deferred with CSP+HSTS+short-TTL mitigation?

## Process note

The full managed-Supabase backend suite is **impractical per-slice** (network round-trips + per-test reconcile; shared-state pollution makes mid-run failures that **pass in isolation**). PAR-F's ephemeral-PG CI was built to remove this but its `xtrusio-ci` secrets aren't wired. Per-slice bar until then: blast-radius tests green + independent review + `make lint`/`make typecheck` green + full-suite failures attributed (re-run the failing modules in isolation to confirm pre-existing).
