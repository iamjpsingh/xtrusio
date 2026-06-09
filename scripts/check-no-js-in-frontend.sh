#!/usr/bin/env bash
# Block .js/.jsx/.mjs/.cjs files in frontend paths.
# Enforces ENGINEERING_PRINCIPLES.md section 2.0 (TypeScript-only frontend).
set -euo pipefail

forbidden=$(
  git diff --cached --name-only --diff-filter=AM \
    | grep -E '^(apps/web|packages/(ui|api-types))/.*\.(js|jsx|mjs|cjs)$' \
    || true
)

if [ -n "$forbidden" ]; then
  echo "ERROR: forbidden non-TypeScript files in frontend paths:"
  echo "$forbidden" | sed 's/^/  - /'
  echo ""
  echo "See ENGINEERING_PRINCIPLES.md section 2.0. Allowed extensions: .ts, .tsx."
  echo "If you genuinely cannot avoid JS (e.g., a third-party tool that"
  echo "loads only .js configs), open the issue for review BEFORE staging"
  echo "the file — do not bypass this hook."
  exit 1
fi

exit 0
