"""Authorization rules for tenant invites.

Owner can invite: admin, editor, read_only.
Admin can invite: editor, read_only (not other admins).
Editor / read_only can't invite anyone.
Nobody can invite owner — that role is born only via self-serve signup.
"""

from __future__ import annotations

from ..models.tenant_membership import TenantRole

_OWNER_TARGETS = {TenantRole.ADMIN, TenantRole.EDITOR, TenantRole.READ_ONLY}
_ADMIN_TARGETS = {TenantRole.EDITOR, TenantRole.READ_ONLY}


def can_invite(*, inviter: TenantRole, target: TenantRole) -> bool:
    if target is TenantRole.OWNER:
        return False
    if inviter is TenantRole.OWNER:
        return target in _OWNER_TARGETS
    if inviter is TenantRole.ADMIN:
        return target in _ADMIN_TARGETS
    return False
