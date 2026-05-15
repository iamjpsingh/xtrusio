"""Unit tests for can_invite — owner/admin permission rules."""

from __future__ import annotations

import pytest
from xtrusio_api.models.tenant_membership import TenantRole
from xtrusio_api.services.invite_rules import can_invite


@pytest.mark.parametrize(
    "inviter,target,allowed",
    [
        (TenantRole.OWNER, TenantRole.ADMIN, True),
        (TenantRole.OWNER, TenantRole.EDITOR, True),
        (TenantRole.OWNER, TenantRole.READ_ONLY, True),
        (TenantRole.OWNER, TenantRole.OWNER, False),
        (TenantRole.ADMIN, TenantRole.ADMIN, False),
        (TenantRole.ADMIN, TenantRole.EDITOR, True),
        (TenantRole.ADMIN, TenantRole.READ_ONLY, True),
        (TenantRole.ADMIN, TenantRole.OWNER, False),
        (TenantRole.EDITOR, TenantRole.READ_ONLY, False),
        (TenantRole.READ_ONLY, TenantRole.READ_ONLY, False),
    ],
)
def test_can_invite(inviter: TenantRole, target: TenantRole, allowed: bool) -> None:
    assert can_invite(inviter=inviter, target=target) is allowed
