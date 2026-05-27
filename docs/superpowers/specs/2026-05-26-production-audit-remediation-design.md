# Design — Production Audit Remediation (PAR)

**Date:** 2026-05-26
**Status:** DRAFT — pending user approval
**Builds on:** `main` @ `d046ab2` (RBAC admin surface COMPLETE; HANDOFF says "NEXT: first product feature").
**Pivots from HANDOFF "NEXT":** before the first product feature, close the production-readiness gaps the 2026-05-26 audit surfaced. The product feature backlog is deferred until PAR-A and PAR-B (the two day-one blockers) ship.

---

## 1. Purpose & goals

The 2026-05-26 production audit identified **60 distinct findings** (5 Critical, 15 High, 24 Medium, 16 Low) and independent verification against the live `main` confirmed **~96% accuracy** — every Critical, every High, every Low except one (L14, redundant with M5), and 21 of 23 surviving Mediums are real bugs. One finding (M7) was incorrect against current code and is dropped from scope.

The audit's bottom line: *"Not production-ready today — but closer than most repos at this phase. The combination of (a) JWT looseness + shared audience, (b) unbounded DB pool, (c) `user_metadata`-based invite acceptance, and (d) absence of rate limiting is enough that a real launch would produce one or more incidents in the first month."*

PAR closes those gaps in six phases (A–F), ordered by risk-if-not-fixed-before-launch. The goal is **a shippable v1 perimeter + ops + RBAC integrity** before the first product feature lands on top of `main`.

### What PAR is

- Defense-in-depth hardening of perimeter (JWT, rate limit, body size, CORS, signup enumeration).
- Operational hardening (DB pool, JWKS rotation, global exception handler, structured logging, request IDs, health probes).
- RBAC integrity hardening (owner floor, super_admin pin, trigger bypass role separation, IntegrityError catching, GUC reset on connection checkin).
- Correctness fixes (cache-on-signout, pagination accumulator → useInfiniteQuery, /me N+1, IntegrityError mapping, cursor row-comparator).
- CI/testing/migration hardening (ephemeral Postgres, OpenAPI codegen, dep-audit, secret-scan, coverage gate, online-migration patterns).

### What PAR is NOT

- A re-architecture. The monorepo, FastAPI/asyncpg/Alembic/React/TanStack Router/Supabase stack stays.
- A product-feature phase. Zero new user-facing capabilities.
- A frontend redesign. Design tokens, shell layout, and component library are untouched.
- A workspace tenancy model change. RLS-as-defense-in-depth + service-layer-as-primary stays.
- A Supabase replacement. Managed Supabase + GoTrue stays.
- Inclusion of the deferred `gotrue → supabase_auth` + `pydantic 2.9 → 2.10` upgrade — HANDOFF tracks that separately as its own PR.

---

## 2. Locked decisions (cross-phase foundational)

These decisions span multiple phases and must be settled before any plan-writing.

1. **Transaction ownership: caller-owns everywhere.** Five services currently self-commit (`invite_acceptance`, `tenant_invites`, `onboarding`, `platform_invites`, `platform_settings`); the rest are caller-owns. PAR-D migrates the five to caller-owns. Routes (and only routes) call `await db.commit()` after the service returns. Audit-log writers stay caller-owns by virtue of being called from within an existing service tx.

2. **`_set_actor` lifts to a request-scoped FastAPI dependency.** The current per-service `_set_actor(...)` call is asymmetric — different services do it at different points. PAR-C lifts it into `Depends(require_auth)` so every authenticated request sets the actor exactly once. Combined with `pool_reset_on_return="rollback"` + a SQLAlchemy `checkin` listener that runs `RESET app.actor_id; RESET app.bypass_priv_escalation`, the cross-request contamination risk in H9 is closed structurally.

3. **Separate DB role `xtrusio_reconciler` for the bypass GUC.** PAR-C migration 0010 creates a new Postgres role with permission to set `app.bypass_priv_escalation`. The privilege-escalation trigger checks `current_user = 'xtrusio_reconciler'` before honoring the GUC — i.e. the GUC is only effective when set on the reconciler connection. A new env var `RECONCILE_DATABASE_URL` connects the reconciler as this role; the request path stays on `postgres`. Even with the GUC set, the trigger refuses the bypass on the wrong role.

4. **TanStack Router `beforeLoad` for permission gating.** PAR-E moves perm checks from component bodies into route loaders. The `<Forbidden />` component stays as the fallback UI; the route loader returns a redirect / forbidden state before the page renders. Eliminates "perm flash" on deep links and centralizes the gate.

5. **OpenAPI-generated TypeScript types replace the hand-written mirror.** PAR-F replaces `packages/api-types/src/*.ts` (which today start with `"Mirror of …schemas/*.py"`) with `packages/api-types/generated/` produced by `openapi-typescript` against FastAPI's `/openapi.json`. The manual mirror is brittle and was the structural backdrop for H13.

6. **One PR per phase, on its own branch, following the existing PAR-naming convention** (`par-a-auth-perimeter`, `par-b-pool-jwks-ops`, `par-c-rbac-integrity`, `par-d-services-perf`, `par-e-frontend-correctness`, `par-f-ci-testing-migrations`). PR bodies in `docs/superpowers/PR-par-<phase>-body.md`. Each merged via `gh pr merge --squash` per CLAUDE.md. HANDOFF.md updated post-merge.

7. **Plans use the same lean-controller cadence as RBAC slices.** Per CLAUDE.md (refined 2026-05-23): **default = ONE Opus subagent for the whole phase + "ship it" instruction.** Skip per-task review ceremony. Only PAR-C and PAR-F have genuine internal sequencing (migrations → services → routes for C; CI changes are independent for F) — those may use 2–3 dispatches. End-of-phase controller gate: `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check`.

8. **Findings explicitly dropped from scope:**
   - **M7** (`slugify` O(n) on hot prefix) — INCORRECT against current code; the function takes a pre-loaded `set[str]`, not a SQL `LIKE` query. No fix needed.
   - **L14** (cursor plaintext JSON) — redundant with **M5**; handled in PAR-D.
   - **`gotrue → supabase_auth` migration** — deferred per HANDOFF; bigger than polish (requires coordinated `supabase + pydantic` upgrade).

---

## 3. Phase scope map

| Phase | Findings | Risk if not fixed before launch | Effort |
|---|---|---|---|
| **A — Auth/security perimeter** | C1, C2, H8, M22 | Cross-tenant token replay; invite UUID + email = takeover; enumeration; RBAC graph leak via 403 body | 2-3 days |
| **B — DB pool + JWKS + observability** | C3, H7, M13, M14, L1, L2, L16 | Connection-exhaustion outage on first traffic; total auth-outage window on key rotation; no debuggability when things break | 2-3 days |
| **C — RBAC defense-in-depth** | C4, C5, H9, H10, M3, M15, M17 | Silent owner-floor bypass → unrecoverable tenant lockout; super_admin invariant lie; reconcile-as-postgres footgun | 3-4 days |
| **D — Backend services + perf** | H5, H6, H11, M1, M2, M4, M5, M6, M8, M9, M16, M18, L3, L4, L5, L6, L7 | /me N+1 on every page load for power users; invite-email phantom on commit fail; audit log table-scan; onboarding double-tenant race; permission re-walk on every request | 4-5 days |
| **E — Frontend correctness** | H1, H2, H3, H4, M10, M11, M12, M24, L8, L9, L10, L11 | Cross-account cache leak on sign-out; broken pagination accumulator on nav-away; queryKey divergence cache-miss; perm flash on deep links; missing toasts | 3-4 days |
| **F — CI/testing/migrations** | H12, H13, H14, H15, M19, M20, M21, L12, L13, L15 | Serial CI throttle at any contributor velocity; cross-layer regressions invisible; bootstrap untested; no dep audit, no secret scan, no coverage gate; production-scale migration locks | 3-4 days |

**Estimated total:** 17–23 engineering days. With the lean-controller cadence (CLAUDE.md §"one subagent for whole slice + ship it"), realistically 2–3 calendar weeks.

**Sequencing (§13 below):** A + B can run in parallel; C must follow B; D depends on C (for the perm-cache invalidation seams); E can run in parallel with D; F lands last.

---

## 4. Phase A — Auth/security perimeter

### 4.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **C1** | JWT loose: alg from JWKS, no iss, default audience | `_ALLOWED_ALGS` = {RS256, RS384, RS512, ES256, ES384}; alg pulled from JWKS doc; no `iss` check; `aud = "authenticated"` (Supabase default) |
| **C2** | Invite ids in `user_metadata` (user-writable) | `services/{platform,tenant}_invites.py` passes invite id via `data={...}` to `invite_user_by_email`; `services/invite_acceptance.py` reads back from `user_metadata` |
| **H8** | Signup enumeration + no rate limit | `/signup` returns 409 `email_taken` vs 202; zero SlowAPI / fastapi-limiter usage anywhere |
| **M22** | `PrivilegeEscalationError` leaks missing perm key | 403 body = `f"privilege_escalation: {e.missing_perm_key}"` |

### 4.2 Locked decisions

**A.1 JWT verification (C1).** `core/auth.py` is rewritten to:
- Pin `algorithms=["RS256"]` (drop ES family — Supabase issues RS256).
- Validate `header.alg == "RS256"` before key lookup; reject otherwise.
- Pass `options={"require": ["exp", "iat", "aud", "iss", "sub"]}` to `jwt.decode()`.
- Pass `issuer=f"{settings.supabase_url}/auth/v1"` (Supabase canonical iss claim).
- Audience pinned to `"authenticated"` (we keep the Supabase default — narrowing requires custom JWT claims which is out of scope).
- All four claims (`alg`, `iss`, `aud`, `kid`) MUST match expectations or 401.

**A.2 Invite claims migration (C2).** Move invite-id claim from `user_metadata` → `app_metadata`:
- `services/platform_invites.py:75-103` and `services/tenant_invites.py:127-152`: stop passing `data={...}` to `invite_user_by_email`. Instead, after the `invite_user_by_email` call returns the created user, call `sb.auth.admin.update_user_by_id(user.id, attributes={"app_metadata": {...}})`. `app_metadata` is service-role-only writable — the invitee cannot forge it.
- `services/invite_acceptance.py:122-138`: read from `app_metadata` not `user_metadata`. `core/auth.py` already extracts the full payload; add `app_metadata` to the dict surfaced to routes/services.
- A migration of in-flight invites is NOT needed: PAR ships before any real invite traffic; legacy `user_metadata` invites become unaccepted after PAR-A. (If real users exist at launch, add a one-time admin migration script.)

**A.3 Rate limiting (H8).** Adopt SlowAPI (`slowapi`):
- `/signup`: 5 req / IP / hour (legitimate users sign up once; brute force needs orders of magnitude more).
- `/invites/accept`: 10 req / IP / hour.
- `/onboarding/tenants`: 5 req / authed user / hour.
- Authenticated routes: 60 req / authed user / minute (cap on the verifier work H7 makes expensive).
- Storage backend: in-memory for dev, Valkey (already in settings) for prod. Adds a real consumer for the previously-unused Valkey client (closes M16's "config without consumer" smell partway).

**A.4 Signup enumeration (H8).** `/signup` always returns 202 `state="confirm_email_sent"` regardless of whether the email exists. If the email already has a `platform_users` row, send a different Supabase email (password reset / sign-in link) instead of an invite — same UX surface, no oracle. The `EmailTakenError` path is removed from the public API; remains an internal signal for choosing the branch.

**A.5 RBAC graph leak (M22).** Route handlers in `routes/platform_role_grants.py` and `routes/workspace_role_grants.py` change `f"privilege_escalation: {e.missing_perm_key}"` → constant `"privilege_escalation"`. The `missing_perm_key` field stays on the exception (for server-side logging) but never leaves the API.

### 4.3 New artifacts

- `apps/api/src/xtrusio_api/core/rate_limit.py` — SlowAPI limiter wired to Valkey.
- `apps/api/src/xtrusio_api/core/auth.py` — rewritten verification.
- `tests/routes/test_jwt_verification.py` — adversarial tests: wrong alg, missing iss, cross-tenant aud, expired, future-nbf.
- `tests/routes/test_invite_app_metadata.py` — confirms acceptance fails for invite-id forged via `user_metadata`.
- `tests/routes/test_rate_limit.py` — confirms 429 after limit.

### 4.4 Acceptance

- `make test-clean && make check` green.
- New adversarial JWT tests cover: RS256 forced, ES256 rejected, missing iss rejected, wrong iss rejected, missing aud rejected, expired rejected.
- `/signup` returns 202 for both new and existing emails (no enumeration).
- 6th call to `/signup` within an hour from one IP returns 429.
- `PrivilegeEscalationError` 403 body does not contain the perm key (regex test).

### 4.5 Risk

- SlowAPI in-memory limiter resets on worker restart — acceptable for dev; Valkey backed in prod.
- Rewriting `core/auth.py` while changing JWT semantics could break every authenticated test. Mitigation: keep the `_AUDIENCE`/`_ALLOWED_ALGS` constants in the new shape; existing fixtures produce tokens that should still pass.

---

## 5. Phase B — DB pool + JWKS + observability

### 5.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **C3** | No pool sizing, no recycle, no statement_timeout | `create_async_engine(url, pool_pre_ping=True, future=True)` only; direct port 5432 in `.env.example` |
| **H7** | JWKS: no rotation, no negative cache, per-call AsyncClient | `_fetch_jwks_uncached` creates fresh `httpx.AsyncClient` per miss; no kid-miss refresh; no stale-grace |
| **M13** | No global exception handler, basicConfig never called, no request-ID | `main.py` has only CORSMiddleware; `log_level` config field unused |
| **M14** | CORS double-wildcard, no max_age | `allow_methods=["*"]`, `allow_headers=["*"]`, no max_age |
| **L1** | `/health` unauth'd, no DB check, no live/ready split | `main.py:88-90`: returns `{"status": "ok"}` |
| **L2** | `engine` and `cors_allow_origins` at module-import time | Resolved at import; settings errors become ImportError |
| **L16** | No request body size cap | Starlette default: full body read before Pydantic |

### 5.2 Locked decisions

**B.1 DB pool configuration (C3).** `core/db.py` is rewritten:
```python
engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,        # 30 min — Supabase Pro idle timeout is 5 min, keep below
    pool_timeout=10,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",  # H9 partial mitigation
    connect_args={
        "server_settings": {
            "statement_timeout": "5000",                     # 5s per statement
            "idle_in_transaction_session_timeout": "10000",  # 10s
            "application_name": "xtrusio-api",
        }
    },
    future=True,
)
```
Plus a SQLAlchemy `event.listens_for(engine.sync_engine, "checkin")` callback that runs `RESET app.actor_id; RESET app.bypass_priv_escalation` before the connection returns to the pool.

**B.2 Supavisor pooler URL (C3).** `.env.example` updates `DATABASE_URL` to the Supavisor pooler endpoint (`*.pooler.supabase.com:6543`, transaction mode). On Supavisor we use `poolclass=NullPool` because the connection pool lives in Supavisor, not the app. The app-side pool config above applies to the direct-connection fallback (dev). Startup assertion in `main.py`: if `settings.environment == "prod"` and the DB host doesn't endswith `pooler.supabase.com`, log a loud warning (config drift). The pooler vs direct choice is operator-driven; the app supports both.

**B.3 JWKS hardening (H7).** `core/auth.py` adds:
- Module-level `httpx.AsyncClient` singleton (created lazily on first use, closed in lifespan shutdown).
- On `kid` not in cache → invalidate cache entry, refetch ONCE, retry decode. If still missing kid, 401.
- On JWKS fetch failure → if a stale cache exists with `expires_at` within `JWKS_STALE_GRACE_SEC` (new setting, default 600s), serve stale and return a `Sec-Warning` header (or just log). If no stale, 503.
- Existing `_JWKS_LOCKS` coalescing stays (the partial mitigation the audit missed).

**B.4 Global exception handler (M13).** `main.py` adds:
```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.state.request_id
    log.exception("unhandled_exception", request_id=request_id, exc_info=exc)
    return JSONResponse({"detail": "internal_server_error", "request_id": request_id}, status_code=500)
```
Plus a `HTTPException` handler that adds `request_id` to every error body.

**B.5 Structured logging + request IDs (M13).** Adopt `structlog`:
- `core/logging.py` — `structlog.configure(...)` with `JSONRenderer`. Called once in lifespan.
- `logging.basicConfig(level=settings.log_level)` finally wired.
- `core/middleware.py:RequestIdMiddleware` — reads `X-Request-ID` header or generates `uuid4()`. Stores on `request.state.request_id`. Adds to response headers.
- Bind `request_id` + `actor_id` to structlog context per request.

**B.6 CORS hardening (M14).** `main.py`:
- `allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]` (explicit list).
- `allow_headers=["Authorization", "Content-Type", "X-Request-ID"]` (explicit list).
- `max_age=600` (10 min preflight cache).
- `expose_headers=["X-Request-ID"]`.

**B.7 Health probes (L1).** Split:
- `GET /health/live` — returns `{"status": "ok"}`, no auth, no DB. K8s liveness probe shape.
- `GET /health/ready` — runs `SELECT 1` against the DB pool, returns 503 if it fails. K8s readiness probe shape.
- Existing `/health` stays as alias for `/health/live` (backward compat — if anyone is hitting it).

**B.8 Lazy engine + cors origins (L2).** `db.py` and `main.py` resolve settings inside lifespan, not at module import. `engine` becomes a lazy singleton via `get_engine()` so import-time errors become startup-time errors (visible in logs, not Python tracebacks during dev-server reload).

**B.9 Body size cap (L16).** `main.py` adds:
```python
class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int = 1_048_576):  # 1MB
        ...
```
Configurable via `MAX_REQUEST_BODY_BYTES` env var. 413 on overflow before Pydantic.

### 5.3 New artifacts

- `core/logging.py`, `core/middleware.py`, `core/health.py`
- `tests/routes/test_health.py` — live + ready paths.
- `tests/integration/test_db_pool_config.py` — asserts `statement_timeout` is set on the connection.
- `tests/routes/test_request_id.py` — confirms `X-Request-ID` round-trip.
- `tests/integration/test_jwks_rotation.py` — simulates kid rotation, asserts refetch-on-miss.

### 5.4 Acceptance

- `make check` green.
- `curl /health/live` returns 200 without DB connectivity.
- `curl /health/ready` returns 503 when DB is unreachable.
- Every error response includes `request_id`.
- `SHOW statement_timeout;` from app connection returns `5000`.
- Manual JWKS rotation drill (rotate the test JWKS, kid changes) → first request after rotation 401s once but subsequent requests succeed within one cache TTL window (versus current behavior: 401s for full TTL).

### 5.5 Risk

- Switching to Supavisor pooler changes transaction semantics in subtle ways (transaction-mode pooler does NOT support session-level features like `LISTEN/NOTIFY`, advisory locks across statements). Audit M9 + M6 use advisory locks within a single transaction — these still work in transaction mode. PAR-C also uses advisory locks for reconciler; still single-tx. No `LISTEN/NOTIFY` usage in the codebase.
- `pool_reset_on_return="rollback"` adds a per-checkin round-trip. Net: ~1-2ms overhead per request. Acceptable.

---

## 6. Phase C — RBAC defense-in-depth

### 6.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **C4** | Trigger bypass branches, INSERT-only, no role gate on GUC | Migration 0009 trigger has GUC short-circuit + NULL-actor short-circuit; INSERT only; backend connects as `postgres` |
| **C5** | super_admin partial index tied to literal UUID; race uncaught | 0006 hardcodes `'…00a1'`; no CHECK constraint on roles; service does count+INSERT without IntegrityError catch |
| **H9** | Backend bypasses RLS as postgres; `_set_actor` asymmetric; no RESET on checkin | Service-level `_set_actor`; `get_db` doesn't `DISCARD ALL`; partial mitigation by `SET LOCAL` |
| **H10** | Owner-floor service-only race; wrong "owner-only" comment | `workspace_admin` holds `workspace.members.manage`; two-admin race → zero owners |
| **M3** | Single-super_admin grant race not caught | Service does count + INSERT; only partial index saves it; service 500s instead of 409 |
| **M15** | Reconcile bypass GUC pattern; same DB role as request path | No separate `RECONCILE_DATABASE_URL` |
| **M17** | `set_updated_at()` trigger has no `SET search_path` | Search_path injection surface |

### 6.2 Locked decisions

**C.1 Migration 0010 `rbac-integrity` — atomic batch:**

```sql
-- 6.2.1 New reconciler role
CREATE ROLE xtrusio_reconciler LOGIN NOSUPERUSER;
GRANT USAGE ON SCHEMA public TO xtrusio_reconciler;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO xtrusio_reconciler;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO xtrusio_reconciler;
GRANT SET ON PARAMETER app.bypass_priv_escalation TO xtrusio_reconciler;

-- 6.2.2 Trigger broadened to INSERT OR UPDATE; bypass GUC role-gated
DROP TRIGGER trg_user_roles_priv_escalation ON user_roles;
CREATE OR REPLACE FUNCTION enforce_priv_escalation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
BEGIN
  IF current_user = 'xtrusio_reconciler'
     AND current_setting('app.bypass_priv_escalation', true) = 'on' THEN
    RETURN NEW;
  END IF;
  IF NEW.granted_by IS NULL THEN
    RAISE EXCEPTION 'granted_by required (no NULL bypass)' USING ERRCODE = 'check_violation';
  END IF;
  -- existing perm-walk logic
  ...
END;
$$;
CREATE TRIGGER trg_user_roles_priv_escalation
  BEFORE INSERT OR UPDATE ON user_roles
  FOR EACH ROW EXECUTE FUNCTION enforce_priv_escalation();

-- 6.2.3 granted_by NOT NULL with sentinel
INSERT INTO platform_users (id, email, role, created_by)
  VALUES ('00000000-0000-0000-0000-0000000000ff', 'system@xtrusio.internal',
          'admin', '00000000-0000-0000-0000-0000000000ff')
  ON CONFLICT DO NOTHING;
UPDATE user_roles SET granted_by = '00000000-0000-0000-0000-0000000000ff'
  WHERE granted_by IS NULL;
ALTER TABLE user_roles ALTER COLUMN granted_by SET NOT NULL;

-- 6.2.4 super_admin role-id CHECK
ALTER TABLE roles ADD CONSTRAINT roles_super_admin_pinned_id
  CHECK (
    (key = 'super_admin' AND scope = 'platform' AND is_system
     AND id = '00000000-0000-0000-0000-0000000000a1')
    OR key != 'super_admin'
    OR scope != 'platform'
  );

-- 6.2.5 workspace-owner floor trigger
CREATE OR REPLACE FUNCTION enforce_workspace_owner_floor() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  remaining_owners int;
  tgt_workspace uuid;
BEGIN
  IF OLD.role_id NOT IN (SELECT id FROM roles WHERE key='owner' AND scope='workspace') THEN
    RETURN OLD;
  END IF;
  tgt_workspace := OLD.workspace_id;
  PERFORM 1 FROM roles WHERE workspace_id = tgt_workspace
    AND key = 'owner' FOR UPDATE;
  SELECT count(*) INTO remaining_owners FROM user_roles ur
    JOIN roles r ON r.id = ur.role_id
    WHERE ur.workspace_id = tgt_workspace AND r.key = 'owner'
    AND ur.id != OLD.id;
  IF remaining_owners = 0 THEN
    RAISE EXCEPTION 'last_owner' USING ERRCODE = 'check_violation';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER trg_user_roles_owner_floor
  BEFORE DELETE ON user_roles
  FOR EACH ROW EXECUTE FUNCTION enforce_workspace_owner_floor();

-- 6.2.6 set_updated_at search_path
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

-- 6.2.7 RLS policy split for tenant_memberships
DROP POLICY tenant_memberships_owner_admin_manage ON tenant_memberships;
CREATE POLICY tenant_memberships_select ON tenant_memberships FOR SELECT
  USING (is_tenant_member(auth.uid(), tenant_id));
CREATE POLICY tenant_memberships_insert ON tenant_memberships FOR INSERT
  WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id));
CREATE POLICY tenant_memberships_update ON tenant_memberships FOR UPDATE
  USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
  WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id));
CREATE POLICY tenant_memberships_delete ON tenant_memberships FOR DELETE
  USING (is_tenant_owner_or_admin(auth.uid(), tenant_id));
```

**C.2 Env + connection plumbing.** New required env var `RECONCILE_DATABASE_URL` (must point to `xtrusio_reconciler` role). `core/db.py` exposes `get_reconciler_engine()` returning a separate engine bound to that role. `rbac/reconcile.py` switches to `get_reconciler_engine().begin()` instead of using the request-path session. Reconciler also wraps its work in `pg_try_advisory_lock(<lock_key>)` (closes **M9** worker-race).

**C.3 `_set_actor` lifts to a FastAPI dependency.** `core/permissions.py:_set_actor` is replaced by `core/auth.py:set_actor_dep`:
```python
async def set_actor_dep(
    identity: Identity = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Identity:
    await db.execute(text("SELECT set_config('app.actor_id', :a, true)"),
                     {"a": str(identity.user_id)})
    return identity
```
Every authenticated route declares `identity: Identity = Depends(set_actor_dep)` (typically inherited via a higher-level dep). All in-service `_set_actor` calls are removed. The `SET LOCAL` semantics stay (transaction-scoped reset). Combined with `pool_reset_on_return="rollback"` (PAR-B) and the SQLAlchemy `checkin` listener that issues `RESET app.actor_id; RESET app.bypass_priv_escalation`, no actor state survives connection checkin.

**C.4 `grant_platform_role` IntegrityError catch (C5, M3).** Wrap the INSERT in `try/except IntegrityError`:
```python
try:
    await db.execute(insert(UserRole).values(...))
except IntegrityError as e:
    if "user_roles_one_super_admin" in str(e.orig):
        raise SingleSuperAdminError() from e
    raise
```
Race-to-500 becomes race-to-409.

**C.5 Service-side workspace owner floor stays, but route maps the new DB exception.** The existing service-side count check stays (friendlier 409). The new `last_owner` DB exception is mapped in route handlers → 409 with `detail="last_owner"`. Two-admin race now: the slower transaction's DELETE fires the trigger, gets `last_owner` from Postgres, rolls back. **Wrong-comment fix**: update the docstring at `workspace_role_grants.py:287-297` to reflect that the DB trigger is the actual safety net.

### 6.3 New artifacts

- `apps/api/migrations/versions/0010_rbac_integrity.py`
- `apps/api/src/xtrusio_api/core/reconciler_db.py` (new module isolating reconciler engine)
- `tests/integration/test_owner_floor_concurrent.py` — uses two real DB sessions, races to revoke, asserts exactly one succeeds.
- `tests/integration/test_super_admin_grant_race.py` — same shape for single-super_admin.
- `tests/integration/test_bypass_guc_role_gated.py` — sets the GUC on a non-reconciler role, asserts the trigger still fires.
- `tests/integration/test_actor_reset_on_checkin.py` — sets actor, returns connection to pool, grabs it again, asserts `app.actor_id` is reset.

### 6.4 Acceptance

- All new tests green.
- `make check` green (including existing RBAC tests).
- Manual: drop bypass GUC on a request-path connection → trigger refuses; same GUC on reconciler connection → bypass works.
- Manual: try two parallel revoke-owner requests → one succeeds, the other 409s.

### 6.5 Risk

- Migration 0010 backfills `granted_by` from NULL to the system sentinel — touches every existing `user_roles` row. On a populated DB this could lock the table briefly. Mitigation: do the UPDATE in batches of 1000 (helper function in migration), or accept the brief lock since launch is pre-real-traffic.
- The new role `xtrusio_reconciler` requires operator setup post-migration (password configured, DSN in env). Document in HANDOFF post-merge.
- The trigger now fires on UPDATE — no service currently updates `role_id`, but if a future "transfer grant" feature is added it'll trip the trigger correctly. No regression today.

---

## 7. Phase D — Backend services + perf

### 7.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **H5** | Supabase call inside open DB tx | `db.add → flush → asyncio.to_thread(_call) → commit` in both invite services |
| **H6** | `/me` O(N tenants) sequential | List-comp of `await effective_workspace_perms(...)` per tenant |
| **H11** | No useful indexes on `rbac_audit_log` | PK only |
| **M1** | Inconsistent transaction ownership | 5 services self-commit; rest are caller-owns |
| **M2** | IntegrityError → 409 collapses all constraints | No `e.orig` inspection |
| **M4** | Cursor predicate disjunctive form, not index-friendly | `or_(a<:t, and_(a=:t, b<:r))` instead of row-comparator |
| **M5** | Cursor unsigned plaintext JSON | base64(`{"t": ..., "i": ...}`) |
| **M6** | Onboarding race creates two tenants | No `UNIQUE(user_id)` on tenant_memberships; no advisory lock |
| **M8** | tenant_invites email case-sensitive | Raw SQL `WHERE u.email = :email` |
| **M9** | Reconcile races N workers | No `pg_try_advisory_lock` |
| **M16** | Valkey in settings, never used | Zero Redis client usage |
| **M18** | Unbounded-list test only matches `*Page` suffix | Misses `list[FooOut]` returns |
| **L3** | Two UPDATEs for name+description | Two `now()` values in one tx |
| **L4** | Invite revoke not race-safe | Has early-return but no SELECT FOR UPDATE |
| **L5** | Editor platform invite silently no-ops | Creates platform_users, skips user_roles |
| **L6** | revoke_platform_invite uses `suppress(Exception)` | Silent Supabase orphans |
| **L7** | `get_settings` name-shadowed | Three definitions across modules |

### 7.2 Locked decisions

**D.1 Caller-owns transaction convention (M1).** Five services lose their `await db.commit()` calls (`invite_acceptance`, `tenant_invites`, `onboarding`, `platform_invites`, `platform_settings`). Their route handlers gain `await db.commit()` after the service returns successfully and `await db.rollback()` on raised typed errors. **The audit's list was slightly off** — `signup.py` was named as self-committing but is actually caller-owns already. Spec-confirmed correction: only the five above migrate.

**D.2 Invite outbox pattern (H5).** New table `invite_email_outbox`:
```sql
CREATE TABLE invite_email_outbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payload jsonb NOT NULL,
  attempts int NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  succeeded_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invite_email_outbox_due_idx ON invite_email_outbox (next_attempt_at)
  WHERE succeeded_at IS NULL;
```
Invite services insert the DB row + outbox row in the same tx, commit, then return. A background task (FastAPI lifespan-launched `asyncio.create_task` initially; can become a real worker later) polls the outbox every 5s and sends emails with exponential backoff. **No external call inside an open DB tx.** Phantom invite emails on commit-fail become impossible.

**D.3 `/me` batched perm query (H6).** Replace the list-comp with a single aggregation:
```sql
SELECT ur.workspace_id, array_agg(DISTINCT p.key) AS perm_keys
FROM user_roles ur
JOIN role_permissions rp ON rp.role_id = ur.role_id
JOIN permissions p ON p.id = rp.permission_id
WHERE ur.auth_user_id = :uid AND ur.workspace_id = ANY(:wids)
GROUP BY ur.workspace_id;
```
50 tenants → 1 roundtrip instead of 50.

**D.4 Audit log indexes (H11).** New migration 0011 (immediately after 0010):
```sql
CREATE INDEX CONCURRENTLY rbac_audit_log_scope_workspace_created_idx
  ON rbac_audit_log (scope, workspace_id, created_at DESC);
CREATE INDEX CONCURRENTLY rbac_audit_log_target_idx
  ON rbac_audit_log (target_type, target_id);
CREATE INDEX CONCURRENTLY rbac_audit_log_actor_created_idx
  ON rbac_audit_log (actor_auth_user_id, created_at DESC);
```
Alembic migrations support `CONCURRENTLY` via `op.execute(...)` + `op.get_bind().execution_options(isolation_level="AUTOCOMMIT")`. Sets the production-migration pattern for M21.

**D.5 IntegrityError inspection (M2).** `services/invite_acceptance.py` wraps the commit in:
```python
try:
    await db.commit()
except IntegrityError as e:
    await db.rollback()
    constraint = getattr(e.orig, "constraint_name", None) or str(e.orig)
    if "platform_users_pkey" in constraint or "platform_users_email_key" in constraint:
        raise AlreadyProvisionedError() from e
    raise  # don't lie about other constraint violations
```

**D.6 Cursor row-comparator (M4).** All cursor-paginated services switch from `or_(...)` form to SQLAlchemy `tuple_()`:
```python
stmt = stmt.where(tuple_(Tenant.created_at, Tenant.id) < tuple_(ts, rid))
```
Postgres can now use a composite `(created_at DESC, id DESC)` index as a single range scan.

**D.7 HMAC-signed cursor (M5, L14).** `core/pagination.py` adds a settings-derived HMAC key:
```python
def encode_cursor(ts, rid) -> str:
    raw = json.dumps({"t": ts.isoformat(), "i": str(rid)}).encode()
    sig = hmac.new(settings.cursor_hmac_key.encode(), raw, hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(raw + b"." + sig.encode()).decode()
```
Decode verifies signature, fails on mismatch. Also caps `ts ≤ now()` on decode.

**D.8 Onboarding advisory lock (M6).** Wrap the existence-check + tenant-create in:
```python
lock_key = abs(hash(f"onboard:{user_id}")) % (2**31)
await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
# existence check + insert
```

**D.9 Reconciler advisory lock (M9).** Same pattern, keyed by a literal constant `RECONCILE_LOCK_KEY = 0x52424143`. If `pg_try_advisory_lock` returns false, the worker logs and skips reconcile — only the lock-holder runs it.

**D.10 Email case-insensitive lookup (M8).** `services/tenant_invites.py` raw SQL changes `u.email = :email` → `lower(u.email) = lower(:email)`. Supabase normalizes on signup but the SQL was case-sensitive against that field. Defensive.

**D.11 Permission cache via Valkey (M16).** New module `core/perm_cache.py`:
- Cache key: `perm:{user_id}:{workspace_id or 'platform'}` → JSON list of perm keys.
- TTL: 30s.
- `effective_workspace_perms` and `effective_platform_perms` consult the cache first; on miss, fall through to DB and SETEX.
- On any `user_roles` mutation (grant / revoke / role-permissions change), the relevant cache key is invalidated. Hooks added to `grant_role`, `revoke_*_role`, role update services.
- Acts as the consumer that closes M16's "config without consumer" complaint AND provides the rate-limiter backend wired in PAR-A.

**D.12 Unbounded-list test broadened (M18).** `tests/integration/test_no_unbounded_lists.py` matcher changes from "endswith Page" to "is `Sequence`-typed return AND not paginated marker". Walks `get_origin(response_model)` and flags `list[...]` without a paginator response model.

**D.13 Polish:**
- `update_*_role` → single `UPDATE` with both fields (L3).
- `revoke_*_invite` → `SELECT … FOR UPDATE NOWAIT` on the invite row (L4).
- Editor platform invite (L5): change from silent no-op to `raise UnsupportedInviteRoleError("editor")` mapped to 400. The "editor" role is genuinely unused; this surfaces the dead path.
- `revoke_platform_invite` Supabase call (L6): replace `contextlib.suppress(Exception)` with a structured try/except that logs to structlog at WARN level. Orphan auth.users get visibility.
- `services/platform_settings.get_settings` (L7) → renamed `get_platform_settings`. Same for `routes/workspace_settings.get_settings` → `get_workspace_settings_route`. `core/config.get_settings` keeps its name (the canonical one).

### 7.3 New artifacts

- Migration `0011_audit_log_indexes_and_invite_outbox.py`
- `core/perm_cache.py`, `core/outbox_worker.py`, `services/invite_outbox.py`
- `tests/integration/test_invite_outbox.py`, `test_me_batched_perms.py`, `test_audit_log_indexes_used.py` (EXPLAIN-based)
- `tests/integration/test_cursor_signature.py`, `test_onboarding_race.py`, `test_reconcile_single_worker.py`
- `tests/services/test_perm_cache.py`

### 7.4 Acceptance

- `/me` for a 50-tenant user returns in ≤ 100ms after warm-up (currently ~50 × ~10ms = 500ms cold).
- `EXPLAIN` on audit-log list query uses the new `(scope, workspace_id, created_at DESC)` index (test asserts via `query plan`).
- Forging a future-timestamp cursor returns 400 `invalid_cursor`.
- Two parallel `/onboarding/tenants` from one user produce exactly one tenant, the second gets 409 `already_provisioned`.
- N=4 workers booting concurrently → only one runs `reconcile_rbac` (verified by log inspection).
- `services/platform_settings.get_settings` no longer exists (rename gate).

### 7.5 Risk

- Outbox worker adds operational complexity. Mitigation: keep it in-process via `lifespan`'s `asyncio.create_task`. Real worker process is a later concern.
- Perm cache TTL of 30s means revoke-then-attempt-action can succeed for up to 30s. The invalidation hooks close most of this; the 30s is a worst-case for races against the cache. Acceptable trade-off vs unbounded DB load.

---

## 8. Phase E — Frontend correctness

### 8.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **H1** | No cache/last-workspace clear on sign-out | `signOut: async () => { await supabase.auth.signOut(); }` only |
| **H2** | `apiFetch` no timeout, no abort, no 401 handler | Raw `fetch(...)`, JSON.stringify body into ApiError.message |
| **H3** | Pagination accumulator in useState mutated inside queryFn | All 4 cited files implement the anti-pattern |
| **H4** | Inline queryKey strings bypass `qk` (5 factories missing) | `tenantInvites`, `platformSettings`, `tenants`, `me`, `signupStatus` not in registry |
| **M10** | Route-level perm gating done in component body | Zero `beforeLoad` usage across routes |
| **M11** | Duplicate near-identical page pairs | RolesPage = 152 LoC each, ~90% identical; same for invite dialog + grant manager |
| **M12** | accept-invite-page useEffect + useRef + eslint-disable dedup | Confirmed at cited lines |
| **M23** | `auth.tsx` `getSession()` has no `.catch` | Corrupted Supabase localStorage hangs app on Loading forever |
| **M24** | Toaster inside AuthGuard | `__root.tsx` wraps Outlet + Toaster inside `<AuthGuard>` |
| **L8** | `apiFetch` returns `undefined as T` for 204 | Type lie |
| **L9** | `route-resolver` reads localStorage per render | Non-pure resolver |
| **L10** | `getSession()` re-read on every apiFetch | 4-8x per page load |
| **L11** | `routeTree.gen.ts` has 19 `as any`, in eslint scope | Eslint only ignores dist/node_modules |

### 8.2 Locked decisions

**E.1 Sign-out cache clear + getSession resilience (H1, M23).** `lib/auth.tsx` rewrite:
```typescript
useEffect(() => {
  let mounted = true;
  supabase.auth.getSession()
    .then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setLoading(false);
    })
    .catch((err) => {
      // M23: corrupted localStorage / decryption failure — don't hang on Loading forever
      log.warn("getSession failed", { err });
      if (!mounted) return;
      setSession(null);
      setLoading(false);
    });
  const { data: { subscription } } = supabase.auth.onAuthStateChange((event, s) => {
    if (event === "SIGNED_OUT") {
      queryClient.clear();
      clearLastWorkspace();
    }
    if (event === "SIGNED_IN" && s?.user.id !== session?.user.id) {
      queryClient.clear();
    }
    setSession(s);
    setLoading(false);
  });
  return () => { mounted = false; subscription.unsubscribe(); };
}, []);
```
The `<AuthProvider>` now consumes `useQueryClient()` and `clearLastWorkspace` from `lib/last-workspace.ts`. M23's `.catch` branch ensures Loading is dismissable even on auth-storage corruption.

**E.2 `apiFetch` hardening (H2, L8, L10).** `lib/api.ts` rewrite:
- `AbortController` per call, 20s timeout (configurable per-call via 4th arg).
- 401 → call `supabase.auth.refreshSession()`. If refresh succeeds, retry once. If refresh fails, call `supabase.auth.signOut()` and reject with `SessionExpiredError`. (`<AuthProvider>`'s SIGNED_OUT branch handles the redirect via cleared cache + auth-state.)
- `ApiError` constructor takes structured `code` (top-level body key) rather than stringifying the whole body. `.message` becomes the `code` or ``API ${status}``.
- Module-scope session cache: subscribe to `onAuthStateChange` and store `currentSession` in a module variable. `apiFetch` reads from the variable instead of calling `getSession()` each time (L10).
- 204 branch returns `Promise<void>` typed correctly: signature changes from `<T>(path) => Promise<T>` to `<T>(path) => Promise<T extends void ? void : T>` — or simpler, a dedicated `apiFetchVoid` helper for DELETE/204-returning endpoints.

**E.3 Pagination → useInfiniteQuery (H3).** All four files migrate:
- `platform-audit-log-page.tsx`, `workspace-audit-log-page.tsx`, `platform-users-page.tsx`, `workspace-members-list-page.tsx`.
- `useInfiniteQuery` with `getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined`.
- `<LoadMoreButton>` calls `fetchNextPage()`; `data.pages.flatMap(p => p.items)` produces the list.
- On nav-away-and-back: TanStack Query keeps pages cached; user resumes where they were.

**E.4 `qk` registry expansion (H4).** `lib/query-keys.ts` adds 5 factories:
```typescript
me: () => ["me"] as const,
tenants: () => ["tenants"] as const,
tenantInvites: (tenantId: string) => ["tenant", tenantId, "invites"] as const,
platformSettings: () => ["platform", "settings"] as const,
signupStatus: () => ["signup-status"] as const,
```
- Migrate 14 call-sites across 9 files.
- **Tuple-shape reconciliation**: today `["tenant-invites", tenantId]` (used by tenant-users-page) and `qk.workspaceInvites = ["workspace", id, "invites"]` (used by workspace-members-page) target different backend resources. KEEP both shapes (they're different resources), but rename the platform-tenant one to `qk.tenantInvites = ["tenant", id, "invites"]` for parallel structure with workspaceInvites. This unifies the convention without forcing one resource into the other's tuple.

**E.5 ESLint rule banning inline queryKey literals (H4).** `apps/web/eslint.config.ts` adds a custom rule (or `no-restricted-syntax` selector) banning array-literal expressions as `queryKey:` values. Forces use of `qk.*`.

**E.6 Route-level perm gating (M10).** Every `_app.{platform,workspace}.*.tsx` route gets:
```typescript
export const Route = createFileRoute("/_app/platform/roles")({
  beforeLoad: async ({ context }) => {
    const me = await context.queryClient.ensureQueryData({
      queryKey: qk.me(),
      queryFn: fetchMe,
    });
    if (!hasPlatformPerm(me, "platform.roles.manage")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: PlatformRolesPage,
});
```
The component bodies' `if (!hasPlatformPerm(...)) return <Forbidden/>` blocks are removed. `<Forbidden />` stays only as the fallback for the unauthenticated layout (kept for direct deep-links that bypass the loader).

**E.7 Page-pair dedupe via `useScopedRoleCrud` + `<ScopedRolesPage>` (M11).** New hook + page:
```typescript
// hooks/use-scoped-role-crud.ts — owns useQuery + create/update/delete mutations
export function useScopedRoleCrud(scope: "platform" | "workspace", workspaceId?: string) { ... }

// components/scoped-roles-page.tsx — generic UI shell
export function ScopedRolesPage({ scope, workspaceId }: Props) { ... }
```
`platform-roles-page.tsx` and `workspace-roles-page.tsx` shrink to thin wrappers (~20 LoC each).
Same pattern for `<ScopedInviteDialog>` (drains the tenant-users vs workspace-members duplicate) and `<GrantManagerBody>` (drains PlatformBody/WorkspaceBody).

**E.8 accept-invite TanStack Router loader (M12).** `accept-invite-page.tsx` becomes:
```typescript
export const Route = createFileRoute("/accept-invite")({
  loader: async ({ context }) => {
    return context.queryClient.fetchQuery({
      queryKey: ["accept-invite", session.user.id],
      queryFn: () => postAcceptInvite(),
    });
  },
  component: AcceptInvitePage,
});
```
`useEffect` + `useRef` guard + `eslint-disable` all removed.

**E.9 Toaster moves out of AuthGuard (M24).** `__root.tsx`:
```tsx
<>
  <AuthGuard>
    <Outlet />
  </AuthGuard>
  <Toaster richColors closeButton position="bottom-right" />
</>
```
Toaster survives redirects.

**E.10 Pure route resolver (L9).** `route-resolver.ts` signature changes to accept `lastWorkspace` as an argument rather than reading localStorage internally. Caller (auth-guard) reads `readLastWorkspace()` once and passes it.

**E.11 routeTree.gen.ts eslint ignore (L11).** `eslint.config.ts:7` adds `"src/routeTree.gen.ts"` to ignores. No more `as any` linter noise from generated code.

### 8.3 New artifacts

- `apps/web/src/hooks/use-scoped-role-crud.ts`
- `apps/web/src/components/scoped-roles-page.tsx`, `scoped-invite-dialog.tsx`, `scoped-grant-manager-body.tsx`
- `apps/web/src/lib/session-cache.ts` (module-level cached session)
- `apps/web/src/__tests__/scoped-roles-page.test.tsx`
- `apps/web/src/__tests__/api-fetch.test.ts` (timeout, abort, 401 refresh paths)
- `apps/web/src/__tests__/auth-cache-clear.test.tsx` (verifies cache clear on SIGNED_OUT)

### 8.4 Acceptance

- `make check` green (vitest + tsc).
- Sign out, sign in as different user → no `me` from previous user visible in cache (verified via test mocking `queryClient.clear`).
- Pagination scroll on audit log: navigate away and back → previously-loaded pages still rendered (no re-fetch from cursor=null).
- ESLint fails on inline queryKey array-literal.
- Deep-linking to a forbidden route never renders the page (loader redirects before component mounts).
- `platform-roles-page.tsx` and `workspace-roles-page.tsx` each ≤ 30 LoC (wrappers around `<ScopedRolesPage>`).

### 8.5 Risk

- TanStack Router `beforeLoad` requires `me` to be query-cacheable before the route. Current AuthGuard already fetches `me`; the loader uses `ensureQueryData` to reuse the cache. Should be transparent.
- The session-cache approach (L10) requires careful handling around the initial mount before `onAuthStateChange` has fired. Mitigation: `apiFetch` falls back to `supabase.auth.getSession()` if the module-scope cache is `undefined`. After first auth state event, cache is populated and stays current.

---

## 9. Phase F — CI/testing/migrations

### 9.1 Findings addressed

| ID | Title | Current state |
|---|---|---|
| **H12** | Serial CI against shared Supabase project | `group: ci-test-db` + per-test cleanup-in-finally |
| **H13** | No E2E, no MSW, manual TS mirror of Pydantic | All page tests mock api+auth; api-types files start "Mirror of ..." |
| **H14** | bootstrap.py untested | Single test reads back manually-created state |
| **H15** | No dep-audit / secret-scan / coverage / SBOM | Only `ci.yml`, no dependabot, no audit, no gitleaks |
| **M19** | Known-flaky tests still in main suite | test_signup_status_default_false, test_signup_disabled_returns_403 |
| **M20** | Migration 0008 ordering dependency on reconciler | Pure-resolver functions on empty user_roles |
| **M21** | Migrations without CONCURRENTLY, no two-step NOT NULL | 0006-0009 zero CONCURRENTLY |
| **L12** | pre-commit claims to mirror make check, omits mypy + tests | Pre-commit only ruff + format + prettier |
| **L13** | mise.toml majors-only, no local Postgres alternative | Major-pin + valkey-only docker-compose |
| **L15** | Tenant.created_by no FK at ORM level | Comment confirms intentional |

### 9.2 Locked decisions

**F.1 Ephemeral Postgres in CI (H12).** `.github/workflows/ci.yml` switches to:
```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_PASSWORD: postgres
    options: >-
      --health-cmd "pg_isready"
      --health-interval 5s
    ports:
      - 5432:5432
```
- `DATABASE_URL` points at `postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`.
- Migrations run against the ephemeral instance.
- For Supabase-specific tests (auth, JWT), keep a `supabase-test` job that uses the managed CI project — but with **per-test SAVEPOINT rollback** so cleanup is automatic.
- `concurrency.cancel-in-progress: true` (we no longer share state).
- Per-test rollback fixture in `conftest.py`:
```python
@pytest.fixture
async def db(...):
    async with engine.begin() as conn:
        async with conn.begin_nested() as savepoint:
            yield conn
            await savepoint.rollback()
```

**F.2 E2E + MSW (H13).** Adopt:
- **Playwright** — one smoke test: sign-in → list roles → create role → audit log shows the create event → delete the role → sign-out. Runs on every push. ~3 min budget.
- **MSW** — for component tests that previously mocked `lib/api`, switch to MSW handlers that return real-shape JSON. Verifies the api-fetch ↔ Pydantic-schema alignment lives in test code.

**F.3 OpenAPI codegen (H13).** Replace `packages/api-types/src/*.ts` mirrors:
- `pnpm` script: `pnpm api-types:generate` → curl `/openapi.json` → `openapi-typescript` → `packages/api-types/generated/openapi.d.ts`.
- Existing `*.ts` files (manual mirrors) become thin re-exports: `export type MeResponse = components["schemas"]["MeResponse"];`.
- CI gate: regenerate types, diff against committed file, fail if drift.
- Drift in CI = "you changed a Pydantic schema without regenerating types" — forced sync.

**F.4 `bootstrap.py` test (H14).** `tests/scripts/test_bootstrap_main.py`:
- Monkeypatches `supabase.create_client` to return a fake admin client.
- Calls `bootstrap.main()` with test env vars.
- Asserts: `platform_users` row, `user_roles` super_admin row, `rbac_audit_log` entry, idempotent on second call.
- Extends `tests/integration/test_no_super_admin_creation.py` allow-list by one entry for the new test file.

**F.5 CI security gates (H15).** New CI jobs (parallel where possible):
- `pip-audit` (via uv): `uv pip compile pyproject.toml | pip-audit -r -`. Fail on CVSS≥7.
- `pnpm audit --audit-level=high`. Fail on high+.
- **Dependabot** — `.github/dependabot.yml` with weekly cadence for `pip`, `npm`, `github-actions`.
- **gitleaks** — `.gitleaks.toml` with default rules + project allowlist for `.env.example`.
- **Trivy** — defer until containers exist (post-PAR), but add the job stub.
- **CodeQL** — Python + TypeScript, default queries.
- **Coverage gate** — `pytest --cov=apps/api/src --cov-fail-under=70` and `vitest --coverage` with `--reporter=cobertura` plus `npx coverage-threshold --statements 70`. Conservative start; ratchet up via PR.

**F.6 Flaky test quarantine (M19).** `tests/routes/test_signup.py`:
- Mark `test_signup_status_default_false` and `test_signup_disabled_returns_403` with `@pytest.mark.xfail(reason="depends on managed-DB platform_settings live state; redesign in F", strict=False)`.
- Replacement test design: fixture that creates a dedicated `platform_settings` row per test, with explicit setup/teardown — no managed-DB global-state dependency. (Replacement deferred to within PAR-F if scope allows; otherwise to a dedicated polish PR.)

**F.7 Migration 0008 ordering hardening (M20).** Add an assertion at the top of `migrations/versions/0008_*.py`'s upgrade:
```python
def upgrade():
    bind = op.get_bind()
    user_role_count = bind.execute(text("SELECT count(*) FROM user_roles")).scalar()
    platform_user_count = bind.execute(text("SELECT count(*) FROM platform_users")).scalar()
    if platform_user_count > 0 and user_role_count == 0:
        raise RuntimeError(
            "0008 expects user_roles to be backfilled (run 0006 + reconciler). "
            "Refusing to upgrade on a populated DB with empty user_roles."
        )
```

**F.8 Migration discipline going forward (M21).** New project doc `docs/superpowers/migration-style.md` (referenced from `ENGINEERING_PRINCIPLES.md`):
- Indexes on existing tables: `CREATE INDEX CONCURRENTLY` (`op.execute(...)` + `AUTOCOMMIT` isolation).
- `NOT NULL` on existing column: two-step (add `CHECK ... NOT VALID`, then `VALIDATE CONSTRAINT`, then `SET NOT NULL`).
- Backfills > 10k rows: batched (1000-row chunks with `pg_sleep(0.1)`).
- 0010 + 0011 (this PAR) demonstrate these patterns and serve as the canonical examples.

**F.9 Pre-commit alignment (L12).** Options considered:
- (a) Add mypy + pytest to pre-commit: too slow, blocks commits unreasonably.
- (b) Add a pre-push hook: mypy + typecheck + smoke pytest. Pre-commit stays fast (format/lint only).
- **Decision: (b)** + update pre-commit comment from "Mirrors what make check does" → "Fast feedback only; full check is `make check` (also runs on push via hook + on PR via CI)."

**F.10 mise version pinning (L13).** `mise.toml` pins patch versions explicitly:
```toml
[tools]
node = "22.7.0"
python = "3.12.5"
pnpm = "10.4.1"
```
Plus a docs section in `ENGINEERING_PRINCIPLES.md` about the local-Postgres alternative (a `docker-compose.local.yml` with a postgres service for contributors who can't / won't provision Supabase — `make dev-local` boots it). The default stays managed-Supabase; local Postgres is opt-in.

**F.11 Tenant.created_by FK at ORM level (L15).** `models/tenant.py`:
```python
created_by: Mapped[UUID] = mapped_column(
    Uuid, ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False
)
```
The FK is no-op against the DB (already there) but enables ORM cascade introspection and surfaces the relationship in `__repr__`.

### 9.3 New artifacts

- `.github/workflows/ci.yml` (rewritten — ephemeral PG service)
- `.github/workflows/e2e.yml` (new — Playwright)
- `.github/workflows/security.yml` (new — pip-audit, pnpm audit, gitleaks, CodeQL)
- `.github/dependabot.yml`
- `.gitleaks.toml`
- `apps/web/playwright.config.ts`, `apps/web/tests/e2e/admin-smoke.spec.ts`
- `packages/api-types/scripts/generate.ts`, `packages/api-types/generated/openapi.d.ts`
- `tests/scripts/test_bootstrap_main.py`
- `docs/superpowers/migration-style.md`
- `docker-compose.local.yml`

### 9.4 Acceptance

- Two PRs can run CI in parallel (no `concurrency: ci-test-db`).
- `pnpm api-types:generate && git diff --exit-code packages/api-types/generated/` passes (drift check).
- `make check` includes `--cov-fail-under=70`.
- Playwright smoke runs on every push.
- `gitleaks` runs on every PR.
- `bootstrap.main()` covered by tests (and `make test` runs the bootstrap test).
- Pre-push hook blocks pushes that break mypy or typecheck.

### 9.5 Risk

- Ephemeral Postgres needs the same extensions managed Supabase ships (`pgcrypto`, `citext`, `uuid-ossp`). All present in the standard `postgres:16` image OR installable via `CREATE EXTENSION`. Verified.
- OpenAPI codegen + drift check adds a maintenance touch-point: forgetting to regenerate after schema changes → CI fails. Acceptable — that's the point.
- Playwright in CI adds ~3 min to the build. Acceptable.

---

## 10. Cross-cutting principles (apply to every phase)

These compound principles span all phases. Reaffirmed here so plan-writers don't drift:

1. **No demo data.** Tests bootstrap via fixtures; no `INSERT INTO ... example data` in migrations or seed scripts. (Already a project principle — reasserted.)
2. **Design tokens only, no hardcoded colors.** New UI surfaces (none in PAR; reasserted for safety).
3. **500 LoC ceiling per file.** New `core/auth.py` rewrite must split if it crosses; same for `lib/api.ts`. Split with intent.
4. **mypy --strict** + **ruff format --check** + **tseslint strict**. No `# type: ignore` without a comment naming the reason. No `as any` in hand-written TS.
5. **RLS is defense-in-depth, backend `require_permission()` is primary.** PAR-C strengthens both; doesn't move the primary gate.
6. **Backend tests can hit real DB.** Frontend tests use MSW or mocked api layer. Cross-layer = E2E (Playwright).
7. **No emojis in code or commit messages** (unless the user requests them). PR descriptions and commit messages use the existing convention.
8. **No Claude co-author trailer on commits/PRs** (per `feedback_no_claude_coauthor`).

---

## 11. Sequencing

```
Day 0       Day 1       Day 2       Day 3       Day 4       Day 5       Day 6       Day 7       Day 8+
[A: auth perimeter]
[B: pool+JWKS+ops]
                        [C: rbac integrity]
                                                [D: services+perf]
                                                [E: frontend correctness]
                                                                        [F: ci+testing+migrations]
```

- **A + B in parallel** (no shared files; A touches auth.py + invite services + rate_limit module; B touches db.py + main.py + logging + health).
- **C depends on B** for `pool_reset_on_return` and the SQLAlchemy `checkin` listener seam.
- **D depends on C** for the perm-cache invalidation hooks tied to grant/revoke; also depends on B for structured logging in the outbox worker.
- **E parallels D** (frontend-only changes; the only backend touch is OpenAPI codegen which lands in F).
- **F lands last** so its drift gates can guard everything PAR-D and PAR-E shipped.

**Total wall-clock estimate:** 2-3 calendar weeks at one engineer with the lean-controller cadence (CLAUDE.md §"one Opus subagent per phase + ship it"). Each PR is one branch, one squash-merge, post-merge HANDOFF update.

---

## 12. Acceptance per phase (consolidated)

| Phase | Gate |
|---|---|
| **A** | `make check` green + adversarial JWT tests pass + signup non-enumerable + 429 on rate-limited path + `privilege_escalation` 403 body sanitized |
| **B** | `make check` green + `/health/{live,ready}` work + `statement_timeout=5000` on connection + request_id round-trips + JWKS rotation drill |
| **C** | `make check` green + 3 new race tests pass + bypass GUC fails on non-reconciler role + super_admin grant race returns 409 not 500 + owner floor enforced by DB trigger |
| **D** | `make check` green + `/me` ≤ 100ms for 50-tenant user + EXPLAIN uses audit indexes + cursor HMAC validates + onboarding race returns 409 + reconcile under advisory lock |
| **E** | `make check` green + cache cleared on sign-out + pagination survives nav-away + ESLint bans inline queryKeys + route-level perm gating + duplicates extracted |
| **F** | `make check` green + Playwright smoke green + drift check green + pip-audit / pnpm-audit / gitleaks / CodeQL green + coverage ≥ 70% + bootstrap.main() covered |

---

## 13. Out-of-scope / explicitly deferred

- **gotrue → supabase_auth migration** — HANDOFF tracks this as its own coordinated PR (requires `supabase + pydantic` major-minor upgrade).
- **L14** — redundant with M5 (handled by PAR-D).
- **M7** — INCORRECT against current code; no fix.
- **The "first product feature"** — resumes after PAR-F merges. New features ride the hardened perimeter.
- **Workspace UI/UX redesign**, dashboard, product surfaces — separate track.
- **Container/Kubernetes deployment artifacts** — PAR is API + frontend + CI hardening only.
- **Stale-grace JWKS beyond bounded window** — implementation caps at `JWKS_STALE_GRACE_SEC` (default 600s). Longer staleness is operator pager-duty material.

---

## 14. Locked decisions (2026-05-26 — user approved)

1. **DB pool target = Supavisor pooler (port 6543, transaction mode) in prod; direct (port 5432) in dev.** PAR-B branches `core/db.py` on URL host: pooler URL → `poolclass=NullPool`; direct URL → sized pool. `connect_args` include `statement_cache_size=0` on asyncpg side for pooler compatibility.

2. **Rate-limit backend = Valkey in BOTH dev and prod (user override).** Single code path everywhere. Local dev requires `docker compose up valkey` (the service is already in `docker-compose.yml`). CI gets a Valkey service in `ci.yml`. M16's "config without consumer" gap is fully closed by this consumer.

3. **Perm cache TTL = 30 seconds.** Aligned with frontend `me` staleTime. Invalidation hooks on grant/revoke/role-permission updates clear cache entries directly — TTL is the worst-case missed-invalidation window, not the norm.

4. **Migration 0010 backfill = brief lock (single UPDATE).** Pre-launch DB scale justifies it; batched-migration pattern is documented in PAR-F's `docs/superpowers/migration-style.md` as the standard for future migrations against populated tables.

5. **OpenAPI codegen = full replace.** `packages/api-types/src/*.ts` files become 1-line re-exports of generated types from `packages/api-types/generated/openapi.d.ts`. Pydantic is the single source of truth. CI drift gate fails when committed types diverge from regeneration.

6. **Playwright in CI = every push.** ~3 min cost per PR; safety > latency. Flaky tests get fixed, not silently skipped — a flake more than once a week is a blocking item.

7. **Coverage gate = 70% backend / 60% frontend with monthly ratchet.** Conservative start that current code likely meets; ratchet up 2-5 percentage points per month until natural ceiling (~85/75).

---

## 15. Status

**Spec status: APPROVED** (2026-05-26).

**Execution plan from here:**
- **PAR-A (this turn)** — auth/security perimeter, one Opus implementer, ship it.
- **PAR-B (next)** — DB pool + JWKS + ops. PAR-A merges first to avoid `main.py` conflict, then PAR-B starts on the updated `main`.
- **PAR-C** — RBAC integrity. Depends on B (pool reset hook).
- **PAR-D + PAR-E** — backend services + frontend correctness, in parallel (different file trees).
- **PAR-F** — CI + testing + migrations, lands last.

The audit found a well-architected codebase with operational gaps. PAR closes them.
