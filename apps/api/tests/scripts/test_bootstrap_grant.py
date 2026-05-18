"""Read-only: the real operator super_admin has a user_roles grant to the
fixed platform super_admin role (0000…00a1). Never creates a super_admin."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_existing_super_admin_has_user_roles_grant(
    existing_super_admin: PlatformUser,
) -> None:
    async with SessionLocal() as s:
        n = (
            await s.execute(
                text(
                    "SELECT count(*) FROM user_roles "
                    "WHERE auth_user_id=:u "
                    "AND role_id='00000000-0000-0000-0000-0000000000a1'"
                ),
                {"u": str(existing_super_admin.id)},
            )
        ).scalar_one()
    assert n == 1
