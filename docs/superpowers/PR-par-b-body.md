# PAR-B — DB pool + JWKS rotation + observability (audit C3, H7, M13, M14, L1, L2, L16)

Second phase of the **Production Audit Remediation** (PAR) sprint. Closes the operational hardening findings from the 2026-05-26 audit (`docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` section 5).

## Summary

- **C3 — Explicit DB pool + server-side timeouts.** `core/db.py` rewritten:
  - Pooler-aware branching on `DATABASE_URL` host (`.pooler.supabase.com`): pooler → `NullPool` + asyncpg `statement_cache_size=0` + SQLAlchemy `prepared_statement_cache_size=0` (Supavisor transaction-mode safe); direct host → `pool_size/max_overflow/pool_recycle/pool_timeout` + `pool_pre_ping` + `pool_reset_on_return="rollback"`.
  - Server settings pushed via asyncpg `connect_args`: `statement_timeout`, `idle_in_transaction_session_timeout`, `application_name="xtrusio-api"` — all driven by new required env vars.
  - SQLAlchemy `checkin` event listener resets the request-scoped GUCs `app.actor_id` and `app.bypass_priv_escalation` before a connection returns to the pool — defense-in-depth seam PAR-C builds on.
- **H7 — JWKS rotation + stale-grace.** `core/auth.py`:
  - Module-lifetime `httpx.AsyncClient` singleton (connection reuse + TLS amortization), closed in lifespan shutdown.
  - On a token whose `kid` is missing from the cached JWKS, the verifier refetches ONCE (`force_refresh=True`) before giving up — collapses the post-rotation 401 window from one full TTL to one fetch.
  - On upstream JWKS-fetch failure with an expired-but-within-grace-window cache entry, the stale doc is served (configurable `JWKS_STALE_GRACE_SEC`) — a Supabase outage no longer flips auth to 100% failure for a full TTL.
- **M13 — Structured logging + global exception handler + request id.**
  - `structlog` wired through stdlib logging in `core/logging.py`; JSON renderer in prod, console renderer in dev.
  - `core/middleware.py:RequestIdMiddleware` reads or generates `X-Request-ID` per request, binds it on `structlog.contextvars`, echoes it on the response.
  - `main.py` registers three global exception handlers — Starlette HTTPException, FastAPI RequestValidationError, and a catch-all `Exception` — every error body now carries `request_id` so user-reported errors are traceable.
- **M14 — CORS hardening.** Explicit `allow_methods=["GET","POST","PATCH","PUT","DELETE","OPTIONS"]`, `allow_headers=["Authorization","Content-Type","X-Request-ID"]`, `expose_headers=["X-Request-ID"]`, `max_age=600`. No more `["*"]` wildcards.
- **L1 — Health probes split.** `routes/health.py`: `GET /health/live` (no deps), `GET /health/ready` (executes `SELECT 1` with 2-second timeout, 503 on failure). Legacy `GET /health` kept as alias of `/health/live`.
- **L2 — Engine config noted for lazy-load.** Engine is created at module import on first `get_settings()` call; settings come from `.env` which fails fast on missing keys, so misconfiguration surfaces at startup rather than first request. (Full lazy-engine refactor deferred — current shape is acceptable now that all engine kwargs come from `.env`.)
- **L16 — Request body size cap.** `core/middleware.py:BodySizeLimitMiddleware` rejects `Content-Length > MAX_REQUEST_BODY_BYTES` with 413 before Pydantic; streaming-chunked requests counted byte-by-byte and aborted mid-flight on overflow.

## New env vars (required — fail-fast on missing)

| Variable | Purpose |
|---|---|
| `XTRUSIO_ENV` | `dev` / `prod` / `test` — gates prod-only pooler-hostname warning |
| `JWKS_STALE_GRACE_SEC` | Seconds the verifier may serve a stale JWKS doc on upstream failure |
| `DB_STATEMENT_TIMEOUT_MS` | asyncpg `statement_timeout` server-setting |
| `DB_IDLE_IN_TX_TIMEOUT_MS` | asyncpg `idle_in_transaction_session_timeout` server-setting |
| `DB_POOL_SIZE` | SQLAlchemy `pool_size` (direct DSN only) |
| `DB_MAX_OVERFLOW` | SQLAlchemy `max_overflow` (direct DSN only) |
| `DB_POOL_RECYCLE_SEC` | SQLAlchemy `pool_recycle` (direct DSN only) |
| `DB_POOL_TIMEOUT_SEC` | SQLAlchemy `pool_timeout` (direct DSN only) |
| `MAX_REQUEST_BODY_BYTES` | Hard cap on request body size before Pydantic |

`.env.example` updated with sensible defaults.

## New runtime artifacts

- `apps/api/src/xtrusio_api/core/logging.py` — structlog configuration
- `apps/api/src/xtrusio_api/core/middleware.py` — RequestIdMiddleware + BodySizeLimitMiddleware
- `apps/api/src/xtrusio_api/routes/health.py` — `/health/live` + `/health/ready` + legacy `/health` alias

## New tests

- `tests/routes/test_health.py` — live + ready + legacy alias
- `tests/integration/test_db_pool_config.py` — asserts `statement_timeout`, `idle_in_transaction_session_timeout`, `application_name` were pushed to the connection via `SHOW`
- `tests/routes/test_request_id.py` — request-id round-trip + presence on error body
- `tests/integration/test_jwks_rotation.py` — three unit tests (no network): unknown-kid refetch fires exactly once; stale-grace serves cached doc when upstream fails; expired-beyond-grace lets the upstream error surface

## Existing tests touched

- `tests/conftest.py` — `_patch_jwks` monkeypatch signature widened to accept the new `force_refresh` kwarg PAR-B added.

## Dependencies added

- `structlog ~= 24.4.0`

## Spec

- `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` section 5 — this PR ships Phase B.

## Documentation

- `docs/superpowers/HANDOFF.md` updated.

## Test plan

- [x] `ruff check` ✅ (167 files)
- [x] `ruff format --check` ✅
- [x] `mypy --strict` ✅ (0 issues, 167 source files)
- [x] `turbo lint` ✅ (no new violations)
- [x] `turbo typecheck` ✅
- [x] `vitest` ✅
- [x] `pytest apps/api/tests` ✅ (via session-mode Supavisor pooler)

## What's next

PAR-C (RBAC defense-in-depth: trigger broadening, super_admin id pin, owner-floor trigger, reconciler DB role, `_set_actor` lifts to FastAPI dependency) — depends on PAR-B's `checkin` listener seam.
