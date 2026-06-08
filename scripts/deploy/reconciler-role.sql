-- PAR-C reconciler role (migration 0013 created `xtrusio_reconciler` NOLOGIN,
-- with NO credential in source). Give it a login + password so the app can
-- connect AS this least-privilege role via RECONCILE_DATABASE_URL for the
-- boot/seed reconcile. The privilege-escalation bypass GUC only takes effect
-- when current_user = 'xtrusio_reconciler', so the reconcile must run as it.
--
-- Run as the role that owns it (the `postgres`/owner role that ran migration
-- 0013). Replace __RECONCILER_PASSWORD__ with a strong password.
--
-- Then set (do NOT commit this — it carries the password):
--   RECONCILE_DATABASE_URL=postgresql+asyncpg://xtrusio_reconciler:__RECONCILER_PASSWORD__@db.__PROJECT_REF__.supabase.co:5432/postgres
--
-- ⚠️ Leave RECONCILE_DATABASE_URL UNSET until you have smoke-tested it (see
-- docs/DEPLOYMENT.md §6). The dev fallback (the request engine) is safe and
-- correct; a half-working reconciler DSN can break boot/seed reconcile.

alter role xtrusio_reconciler login password '__RECONCILER_PASSWORD__';

-- Rollback (revert to the migration's NOLOGIN, no-credential state):
--   alter role xtrusio_reconciler nologin password null;
