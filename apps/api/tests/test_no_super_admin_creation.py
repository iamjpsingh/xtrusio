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
# Files allowed to mention the term — matched by path RELATIVE to _TESTS_DIR so
# that subdirectory conftests (e.g. rls/conftest.py) are NOT silently exempt.
_ALLOWED = {
    Path("test_no_super_admin_creation.py"),
    Path("conftest.py"),
    Path("_cleanup.py"),
}


def test_no_test_creates_a_super_admin() -> None:
    offenders: list[str] = []
    for path in _TESTS_DIR.rglob("*.py"):
        if path.relative_to(_TESTS_DIR) in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(_TESTS_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Tests must NEVER create or hardcode a super_admin role. "
        "Use the read-only `existing_super_admin` fixture instead.\n" + "\n".join(offenders)
    )
