"""Catalog integrity: keys unique, scopes valid, system-role map closed."""

from __future__ import annotations

import pytest
from xtrusio_api.rbac.catalog import (
    CATALOG,
    SYSTEM_ROLE_PERMISSIONS,
    Permission,
    catalog_keys,
)


def test_keys_unique_and_scoped() -> None:
    keys = [p.key for p in CATALOG]
    assert len(keys) == len(set(keys)), "duplicate permission key"
    for p in CATALOG:
        assert p.scope in ("platform", "workspace")
        assert p.key.startswith(p.scope + "."), f"{p.key} not under its scope"
        assert p.category and p.description


def test_system_role_map_references_only_catalog_keys() -> None:
    valid = catalog_keys()
    for role_key, perm_keys in SYSTEM_ROLE_PERMISSIONS.items():
        for k in perm_keys:
            assert k in valid, f"{role_key} references unknown permission {k}"


def test_super_admin_has_every_platform_permission() -> None:
    platform_keys = {p.key for p in CATALOG if p.scope == "platform"}
    assert set(SYSTEM_ROLE_PERMISSIONS["super_admin"]) == platform_keys


def test_owner_has_every_workspace_permission() -> None:
    workspace_keys = {p.key for p in CATALOG if p.scope == "workspace"}
    assert set(SYSTEM_ROLE_PERMISSIONS["owner"]) == workspace_keys


def test_admin_excludes_roles_manage() -> None:
    assert "platform.roles.manage" not in SYSTEM_ROLE_PERMISSIONS["admin"]
    assert "workspace.roles.manage" not in SYSTEM_ROLE_PERMISSIONS["workspace_admin"]


def test_permission_is_frozen() -> None:
    p = CATALOG[0]
    assert isinstance(p, Permission)
    with pytest.raises(AttributeError):
        p.key = "x"  # type: ignore[misc]
