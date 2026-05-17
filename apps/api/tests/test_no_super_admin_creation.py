"""Guard: no test may CREATE a super_admin (platform_users row, user_roles
grant, or via the PlatformRole.SUPER_ADMIN enum). The single super_admin is
created only by the operator via `make create-platform-owner`; tests verify
against the existing one (read-only `existing_super_admin` fixture).

Under the RBAC model `'super_admin'` is also a legitimate role-catalog *key*
that read-only RBAC tests reference in SQL/assertions. Those references are
NOT creation and must not trip this guard, so the guard matches only
super_admin *creation* signals, never bare references."""

from __future__ import annotations

import re
from pathlib import Path

_TESTS_DIR = Path(__file__).parent

# The PlatformRole.SUPER_ADMIN enum is only ever used to set a role when
# constructing/assigning a platform user — never in a read-only test.
_ENUM = re.compile(r"PlatformRole\.SUPER_ADMIN")

# A write into platform_users/user_roles, or a PlatformUser(...) construction,
# associated with super_admin — scanned over the whole file (DOTALL, bounded
# gap) so multi-line raw SQL is still caught. Pure SELECT/WHERE reads and
# role-key references do not contain these write tokens, so they don't match.
_WRITE_WITH_SUPER_ADMIN = re.compile(
    r"(INSERT\s+INTO\s+(?:platform_users|user_roles)|PlatformUser\s*\()"
    r"(?:.|\n){0,400}?super_admin",
    re.IGNORECASE,
)

# Files allowed to mention the term — matched by path RELATIVE to _TESTS_DIR.
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
        content = path.read_text(encoding="utf-8")
        if _WRITE_WITH_SUPER_ADMIN.search(content):
            offenders.append(f"{path.relative_to(_TESTS_DIR)}: writes a super_admin row/grant")
        for lineno, line in enumerate(content.splitlines(), 1):
            if _ENUM.search(line):
                offenders.append(f"{path.relative_to(_TESTS_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Tests must NEVER create a super_admin (platform_users row, user_roles "
        "grant, or PlatformRole.SUPER_ADMIN). Use the read-only "
        "`existing_super_admin` fixture instead.\n" + "\n".join(offenders)
    )
