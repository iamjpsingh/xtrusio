#!/usr/bin/env bash
# Pre-push gate (PAR-F F.9 / L12).
#
# Pre-commit stays fast (format + lint only). This pre-push hook adds the
# heavier-but-still-bounded checks so a push can't break the build:
#   1. mypy --strict on the backend
#   2. turbo typecheck (frontend)
#   3. a FAST smoke pytest subset (NOT the full suite — the full suite runs in
#      CI). The smoke set is Supabase-free + quick, so it needs no managed DB
#      and finishes in a few seconds.
#
# The full `make check` (which also runs the complete test suites) is the
# authoritative local gate; CI is the authoritative remote gate. This hook is
# the cheap "did I obviously break types or core logic" tripwire.
set -euo pipefail

echo "[pre-push] mypy (backend, strict)..."
uv run mypy apps/api

echo "[pre-push] turbo typecheck (frontend)..."
pnpm exec turbo run typecheck

echo "[pre-push] smoke pytest subset (Supabase-free, fast)..."
# A small, fast, DB-independent slice. Deliberately NOT the full suite.
uv run pytest \
  apps/api/tests/test_health.py \
  apps/api/tests/test_cors.py \
  apps/api/tests/test_no_super_admin_creation.py \
  apps/api/tests/rbac/test_models.py \
  apps/api/tests/rbac/test_catalog.py \
  apps/api/tests/core/test_pagination.py \
  apps/api/tests/core/test_cursor_signature.py \
  apps/api/tests/services/test_slug.py \
  apps/api/tests/services/test_invite_rules.py \
  -q -p no:cacheprovider

echo "[pre-push] OK"
