# feat(auth-events) — GoTrue auth-event capture: `auth` activity-feed category via a Supabase Database Webhook

The **last open item** from the deep auth+UX audit (`docs/superpowers/specs/2026-06-05-auth-security-audit-and-remediation.md`) and the activity-feed work (plan `docs/superpowers/plans/2026-06-06-activity-feed.md`). The unified feed already reserved an `auth` category that stayed empty; this fills it with GoTrue login/logout/etc events.

**Mechanism (the flagged operator decision, now made):** a Supabase **Database Webhook** on `INSERT` of `auth.audit_log_entries` POSTs each new GoTrue audit row to a new ingest endpoint. Chosen over an Auth Hook (those gate the auth flow — wrong blast radius for passive capture) or a polling mirror (extra moving part). Each accepted event becomes one `rbac_audit_log` row, so it flows through the **existing** viewer, catalog, and `?category=auth` filter with **zero schema change**.

## Backend
- **`POST /api/internal/auth-events`** (`routes/internal_auth_events.py`) — unauthenticated in the JWT sense (Supabase calls it, not a browser). Its only gate is a shared secret in the `X-Webhook-Secret` header, **constant-time** compared (`secrets.compare_digest`, always invoked — missing header and wrong secret take the same path, no presence timing signal) against `AUTH_WEBHOOK_SECRET`. Maps the GoTrue `payload.action` → `action='auth.<action>'`, `scope='platform'`, actor = `payload.actor_id`; preserves `actor_username` / `ip_address` / `gotrue_event_id` / `gotrue_created_at` in the `after` payload.
- **FK-safe ingest.** `rbac_audit_log.actor_auth_user_id` is an FK to `auth.users` (`ON DELETE SET NULL`). A GoTrue `actor_id` does not always resolve to a live row (a `user_deleted` event, an external/anonymous actor) → a raw insert would FK-violate → 500 → the webhook retries forever. The insert runs inside a **SAVEPOINT** (`begin_nested`); on `IntegrityError` it re-records with a **NULL FK actor** (the id stays in `after.actor_id`). A genuine transient DB error still surfaces as 500 — correctly retryable — rather than being swallowed.
- **Fail-safe retry posture.** Every well-formed delivery we simply can't turn into an event (wrong table / non-INSERT / missing record / missing-or-blank action) returns **`200 {"status":"ignored"}` + a log line** — never a retry-triggering non-2xx — so a future GoTrue payload-shape drift can't cause an infinite retry loop. Non-2xx is reserved for `401` (bad/absent secret — operator misconfig) and FastAPI's own `422` (structurally malformed body).
- **Rate-limit exempt.** The SlowAPI authenticated catch-all (60/min, IP-keyed for tokenless callers) is exempted for this route in `main.py` (mirroring the health-probe pattern) — Supabase's webhook arrives from a single egress IP, so the catch-all would otherwise throttle legitimate login/refresh volume. The endpoint's own shared-secret is the gate.
- **Config (`core/config.py`)** — new required `AUTH_WEBHOOK_SECRET` (no default; fail-fast) + a prod `model_validator` that refuses to boot on the dev placeholder or a secret `< 32` chars (reuses the `CURSOR_HMAC_KEY` weak-key constants).
- **Catalog (`core/audit_catalog.py`)** — 12 `auth.*` actions mapped to the `auth` category with human labels ("Signed in", "Signed out", …); unmapped GoTrue actions fall through to `other` (still visible unfiltered).
- **`core/audit.py`** — `write_audit_event` `actor_id` is now `UUID | None` (the column + the viewer's `actor_email` LEFT JOIN already tolerate NULL); all existing callers unaffected.

**No migration** — the table already accepts arbitrary action/target strings and a NULL actor. Alembic head stays `0014`.

## Tests
`tests/routes/test_internal_auth_events.py` (12) — secret gate (missing/wrong → 401), ignore semantics (non-INSERT / wrong-table / missing-record / missing-action → 200), happy-path row write (action/scope/target/`after` provenance), anonymous → NULL FK actor, **the unresolvable-actor regression (ghost actor_id → 200, NULL FK, id preserved — not a 500)**, end-to-end visibility in `GET /api/platform/audit-log?category=auth` with the right `action_label`/`category`, and a config assertion locking in the rate-limit exemption. Rows self-clean by unique actor_id / synthesized action.

## Adversarial review
Ran a multi-lens review (security / correctness / operational / integration) with per-finding skeptic verification (22 agents). Actioned: missing-action `400 → 200/ignored` (fail-safe), always-constant-time secret compare, expanded `.env.example` operator checklist. Refuted (correctly) and **not** applied: "wrap the fallback write in a catch-all → return 200" — that would silently drop events on transient DB errors; a NULL-actor write can't FK-violate, so the only path to the fallback failing is a genuine transient error that *should* 500-and-retry.

## Gate
`mypy --strict` clean (222 files); ruff check + format clean; backend targeted — `test_internal_auth_events` + audit-catalog + platform/workspace audit-log suites green vs managed Supabase; web `turbo typecheck test` green (**324/324 vitest**). No signup/sign-in/onboarding path touched.

## Operator setup (required for events to flow)
See the `AUTH_WEBHOOK_SECRET` block in `.env.example` — generate a 32-byte secret, set it, then in Supabase Dashboard → Database → Webhooks create an `INSERT`-on-`auth.audit_log_entries` HTTP POST to `<API>/api/internal/auth-events` with the matching `X-Webhook-Secret` header. A curl smoke-test is included. Until wired, the `auth` category stays empty (no error surfaced).

## Follow-ups (deferred — product/ops decisions, surfaced not silently decided)
- **`token_refreshed` volume** — GoTrue fires it ~hourly per active user; capturing it can make the feed noisy and grow `rbac_audit_log`. Currently captured for completeness. If undesired, skip it (and/or `token_revoked`) at ingest — a one-line change, optionally env-driven. Flagged for the operator.
- **Timeline = ingest time, not event time** — `rbac_audit_log.created_at` is `now()` at ingest; the true GoTrue time is preserved in `after.gotrue_created_at`. Webhook delivery is typically sub-second, so feed ordering is effectively correct; revisit only if forensic precision is needed.
- **No cross-delivery dedup** — Database Webhooks fire once per INSERT; a duplicate auth row is rare/low-severity. `after.gotrue_event_id` is captured so a future dedup/unique-index can be added.
