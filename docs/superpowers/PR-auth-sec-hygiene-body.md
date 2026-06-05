# auth-sec — security hygiene: weak HMAC key + security headers + opaque 401s

Closes three findings from the 2026-06-05 auth security audit (`docs/superpowers/specs/2026-06-05-auth-security-audit-and-remediation.md`). All backend, no DB migration.

## 1. Reject weak `CURSOR_HMAC_KEY` in prod (MEDIUM vuln · CWE-798/321)

The placeholder `dev-only-change-me-…` had been copied verbatim into the live `.env`; pagination cursors are HMAC-signed, so a known key = forgeable cursors.

- `.env.example`: placeholder value emptied + `secrets.token_hex(32)` generation comment.
- `core/config.py`: `@model_validator(mode="after")` rejects the `dev-only-change-me` prefix (any variant) **or** a `< 32`-char key when `env == "prod"` — fails fast at `Settings()` construction so the app won't boot on a weak key. No-op in dev/test.
- Local `.env` (gitignored, not committed): rotated to a fresh 64-hex value.

## 2. Security-headers middleware (MEDIUM · CWE-693/1021)

New `SecurityHeadersMiddleware` (`core/middleware.py`), registered outermost in `main.py` so it also stamps CORS-preflight short-circuits and the global exception handler's responses. Headers added via `setdefault` (never clobbers existing values):

- always: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, minimal `Permissions-Policy`.
- prod only: `Strict-Transport-Security: max-age=63072000; includeSubDomains` (never on localhost).
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'` on every path **except** the docs UI (`/docs`, `/redoc`, `/openapi.json`) — Swagger/ReDoc load CDN+inline assets, so a blanket CSP would break them. Docs still get all the other hardening headers.

## 3. Opaque 401 error codes (LOW · CWE-209)

`core/auth.py` no longer echoes raw JOSE/JWKS exception text to clients. Client-facing 401s are now stable opaque codes — `invalid_token` (decode/header/alg/kid/claim failures) and `token_verification_unavailable` (JWKS fetch failures) — while the detailed exception is logged server-side at WARN (structlog, request_id rides via contextvars). Removes the recon/JWKS-host leak on the 401 path.

## Tests

- `tests/core/test_config_cursor_key.py` — prod rejects weak/short key; non-prod tolerates; strong key passes.
- `tests/core/test_security_headers.py` — baseline headers present; HSTS prod-only; CSP omitted on docs paths; CORS preflight not broken.
- `tests/core/test_es256_jwt.py` — 401 body is the opaque code and contains no library/JWKS internals.

Gate: `make lint` + `make typecheck` clean; `mypy --strict` clean; 18 slice tests + full `tests/core` green (managed-DB full suite is impractical per-slice — see spec process note; all new tests are Supabase-free).
