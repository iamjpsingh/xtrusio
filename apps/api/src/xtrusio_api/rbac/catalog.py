"""Code-defined RBAC permission catalog — the single source of truth.

Developers add `scope.resource.action` keys here as features ship. Roles are
data; permission primitives are NOT (spec §2.1). The reconciler projects this
into the `permissions` table; migration `0006` seeds system roles whose
`role_permissions` are derived from SYSTEM_ROLE_PERMISSIONS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Scope = Literal["platform", "workspace"]


@dataclass(frozen=True, slots=True)
class Permission:
    scope: Scope
    key: str
    category: str
    description: str


CATALOG: tuple[Permission, ...] = (
    Permission(
        "platform",
        "platform.roles.manage",
        "Access control",
        "Create/edit/delete platform roles and their permissions",
    ),
    Permission("platform", "platform.users.read", "Platform users", "View platform users"),
    Permission("platform", "platform.users.invite", "Platform users", "Invite platform users"),
    Permission(
        "platform",
        "platform.users.manage",
        "Platform users",
        "Activate/deactivate/assign roles to platform users",
    ),
    Permission("platform", "platform.clients.read", "Clients", "View client workspaces"),
    Permission("platform", "platform.clients.manage", "Clients", "Create/manage client workspaces"),
    Permission("platform", "platform.settings.read", "Settings", "View platform settings"),
    Permission("platform", "platform.settings.manage", "Settings", "Edit platform settings"),
    Permission("platform", "platform.audit.read", "Audit", "View the platform RBAC audit log"),
    Permission(
        "workspace",
        "workspace.roles.manage",
        "Access control",
        "Create/edit/delete workspace roles and their permissions",
    ),
    Permission("workspace", "workspace.members.read", "Members", "View workspace members"),
    Permission("workspace", "workspace.members.invite", "Members", "Invite workspace members"),
    Permission(
        "workspace",
        "workspace.members.manage",
        "Members",
        "Remove members / assign workspace roles",
    ),
    Permission("workspace", "workspace.settings.read", "Settings", "View workspace settings"),
    Permission("workspace", "workspace.settings.manage", "Settings", "Edit workspace settings"),
    Permission("workspace", "workspace.audit.read", "Audit", "View the workspace RBAC audit log"),
)


def catalog_keys() -> set[str]:
    return {p.key for p in CATALOG}


def _platform(*exclude: str) -> tuple[str, ...]:
    return tuple(p.key for p in CATALOG if p.scope == "platform" and p.key not in exclude)


def _workspace(*exclude: str) -> tuple[str, ...]:
    return tuple(p.key for p in CATALOG if p.scope == "workspace" and p.key not in exclude)


# Keys are system-role identifiers, NOT (scope,key) pairs. `admin` is the
# platform admin; `workspace_admin` is the workspace admin (distinct scopes).
SYSTEM_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "super_admin": _platform(),
    "admin": _platform("platform.roles.manage"),
    "owner": _workspace(),
    "workspace_admin": _workspace("workspace.roles.manage"),
    "editor": ("workspace.members.read", "workspace.settings.read"),
    "read_only": ("workspace.members.read", "workspace.settings.read"),
}
