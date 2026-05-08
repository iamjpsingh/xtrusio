#!/usr/bin/env bash
# Block hardcoded colors and Tailwind palette utilities in frontend paths.
# Enforces ENGINEERING_PRINCIPLES §2.0 + spec #4 §9.
set -euo pipefail

# Files to scan: only newly added/modified frontend source under apps/web or packages/ui
staged=$(git diff --cached --name-only --diff-filter=AM \
  | grep -E '^(apps/web|packages/(ui|api-types))/.*\.(ts|tsx|css)$' \
  | grep -v 'src/globals\.css$' \
  | grep -v '/components/ui/' \
  | grep -v '/routeTree\.gen\.ts$' \
  || true)

if [ -z "$staged" ]; then
  exit 0
fi

# Patterns to forbid:
#   - Hex colors (#abc, #abcdef, #abcdef00)
#   - Tailwind palette utilities for colors that should go through tokens
forbidden_patterns=(
  '#[0-9a-fA-F]{3,8}\b'
  '(bg|text|border|ring|fill|stroke|from|via|to)-(slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]+'
)

violations=0
for file in $staged; do
  for pat in "${forbidden_patterns[@]}"; do
    matches=$(grep -nE "$pat" "$file" 2>/dev/null || true)
    if [ -n "$matches" ]; then
      echo "ERROR: hardcoded color in $file (use semantic tokens, see ENGINEERING_PRINCIPLES §2.0):"
      echo "$matches" | sed 's/^/  /'
      violations=$((violations + 1))
    fi
  done
done

if [ "$violations" -gt 0 ]; then
  exit 1
fi
exit 0
