"""Guard: no test may CREATE a super_admin. The single super_admin is created
only by the operator via `make create-platform-owner`. Tests verify against
the existing one (read-only `existing_super_admin` fixture)."""

from __future__ import annotations

import re
from pathlib import Path

_TESTS_DIR = Path(__file__).parent
# Patterns that would CREATE a super_admin row in a test.
_FORBIDDEN = re.compile(
    r"(PlatformRole\.SUPER_ADMIN|role\s*=\s*['\"]super_admin['\"]|'super_admin'|\"super_admin\")"
)
# Files allowed to mention the term (this guard itself + the read-only fixture +
# the crash-proof purge helper which must remain to keep CI clean).
_ALLOWED = {"test_no_super_admin_creation.py", "conftest.py", "_cleanup.py"}


def test_no_test_creates_a_super_admin() -> None:
    offenders: list[str] = []
    for path in _TESTS_DIR.rglob("*.py"):
        if path.name in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(_TESTS_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Tests must NEVER create or hardcode a super_admin role. "
        "Use the read-only `existing_super_admin` fixture instead.\n" + "\n".join(offenders)
    )
