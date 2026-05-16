"""Crash-proof purge of all test data from the shared managed DB.

Test data is identified ONLY by the `@example.com` email convention. The single
real account (admin@xtrusio.com) and any non-@example.com row are never touched.
Importable (used by the session-scoped autouse fixture) AND runnable as a script
(`python -m tests._cleanup` / `make test-clean`) so a crashed run can be cleaned
at any time.
"""

from __future__ import annotations

import asyncio
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from xtrusio_api.core.db import SessionLocal

# Belt-and-suspenders: even within @example.com, never delete this.
_REAL_OWNER = "admin@xtrusio.com"
_TEST_EMAIL_LIKE = "%@example.com"


async def purge_test_data() -> dict[str, int]:
    """Delete every @example.com test row in FK-safe order. Returns per-table counts.

    Idempotent and safe to run anytime (no test running, after a crash, etc.).
    """
    counts: dict[str, int] = {}
    async with SessionLocal() as s:
        # Resolve the set of test auth.users ids first (drives FK-dependent deletes).
        test_ids = [
            r[0]
            for r in (
                await s.execute(
                    text("SELECT id FROM auth.users " "WHERE email LIKE :pat AND email <> :real"),
                    {"pat": _TEST_EMAIL_LIKE, "real": _REAL_OWNER},
                )
            ).all()
        ]

        # Statements in strict child->parent order. Each filters to test data only.
        # Email-based deletes run first, then id-based (for rows whose invitee email
        # might differ but whose tenant/inviter is test-owned).
        stmts: list[tuple[str, str]] = [
            (
                "platform_invites",
                "DELETE FROM platform_invites WHERE email LIKE :pat",
            ),
            (
                "tenant_invites",
                "DELETE FROM tenant_invites WHERE email LIKE :pat",
            ),
        ]

        for label, sql in stmts:
            params: dict[str, object] = {
                "pat": _TEST_EMAIL_LIKE,
                "real": _REAL_OWNER,
                "ids": test_ids,
            }
            res = cast(CursorResult[tuple[object, ...]], await s.execute(text(sql), params))
            counts[label] = res.rowcount or 0

        # Id-based second pass: invites whose invitee email might not be @example.com
        # but whose tenant or inviter is test-owned. Guard on empty test_ids to avoid
        # asyncpg empty-array misbehaviour.
        if test_ids:
            id_stmts: list[tuple[str, str]] = [
                (
                    "platform_invites_by_inviter",
                    "DELETE FROM platform_invites WHERE invited_by = ANY(:ids)",
                ),
                (
                    "tenant_invites_by_tenant",
                    "DELETE FROM tenant_invites WHERE tenant_id IN "
                    "(SELECT id FROM tenants WHERE created_by = ANY(:ids))",
                ),
                (
                    "tenant_invites_by_inviter",
                    "DELETE FROM tenant_invites WHERE invited_by = ANY(:ids)",
                ),
                (
                    "tenant_memberships",
                    "DELETE FROM tenant_memberships WHERE tenant_id IN "
                    "(SELECT id FROM tenants WHERE created_by = ANY(:ids))",
                ),
                (
                    "tenants",
                    "DELETE FROM tenants WHERE created_by = ANY(:ids)",
                ),
            ]
            for label, sql in id_stmts:
                params = {
                    "pat": _TEST_EMAIL_LIKE,
                    "real": _REAL_OWNER,
                    "ids": test_ids,
                }
                res = cast(CursorResult[tuple[object, ...]], await s.execute(text(sql), params))
                counts[label] = res.rowcount or 0
        else:
            for label in (
                "platform_invites_by_inviter",
                "tenant_invites_by_tenant",
                "tenant_invites_by_inviter",
                "tenant_memberships",
                "tenants",
            ):
                counts[label] = 0

        # Parent rows last.
        email_parent_stmts: list[tuple[str, str]] = [
            (
                "platform_users",
                "DELETE FROM platform_users WHERE email LIKE :pat AND email <> :real",
            ),
            (
                "auth_users",
                "DELETE FROM auth.users WHERE email LIKE :pat AND email <> :real",
            ),
        ]
        for label, sql in email_parent_stmts:
            params = {
                "pat": _TEST_EMAIL_LIKE,
                "real": _REAL_OWNER,
                "ids": test_ids,
            }
            res = cast(CursorResult[tuple[object, ...]], await s.execute(text(sql), params))
            counts[label] = res.rowcount or 0

        await s.commit()

        # Hard post-condition: no stray super_admin may remain other than the real owner.
        stray = (
            await s.execute(
                text(
                    "SELECT count(*) FROM platform_users "
                    "WHERE role = 'super_admin' AND email <> :real"
                ),
                {"real": _REAL_OWNER},
            )
        ).scalar_one()

    if stray:
        raise AssertionError(
            f"purge_test_data left {stray} stray super_admin row(s) "
            f"(other than {_REAL_OWNER}); test-data convention violated"
        )
    return counts


def main() -> None:
    counts = asyncio.run(purge_test_data())
    total = sum(counts.values())
    print(f"test-data purge complete ({total} rows): {counts}")


if __name__ == "__main__":
    main()
