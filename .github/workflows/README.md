# CI workflow

`ci.yml` runs on every PR to `main` and every push to `main`.

## Required secrets

Set these on the repo (Settings → Secrets and variables → Actions). All come from a
dedicated managed Supabase project called `xtrusio-ci` (separate from dev/prod):

- `CI_DATABASE_URL` — postgres connection string
- `CI_SUPABASE_URL`
- `CI_SUPABASE_ANON_KEY`
- `CI_SUPABASE_SERVICE_ROLE_KEY`
- `CI_SUPABASE_JWKS_URL`

## Re-running

Concurrency group `ci-test-db` is queue-not-cancel — a re-run waits for the
current job rather than killing it mid-cleanup. Force-skip by closing/reopening
the PR if a job is wedged.

## Common failures

- **Pre-test cleanup hangs:** the test DB has unrelated rows. Run `make test-clean`
  locally against the CI project, or wipe `@example.com` rows manually.
- **`pnpm install` slow:** the action's pnpm cache lives in `pnpm/action-setup` —
  invalidates on `pnpm-lock.yaml` change.
