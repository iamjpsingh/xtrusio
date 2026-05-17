"""ORM mapper config + table names for the RBAC models."""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers
from xtrusio_api.models import (
    Permission,
    RbacAuditLog,
    Role,
    RolePermission,
    UserRole,
)


def test_table_names() -> None:
    assert Permission.__tablename__ == "permissions"
    assert Role.__tablename__ == "roles"
    assert RolePermission.__tablename__ == "role_permissions"
    assert UserRole.__tablename__ == "user_roles"
    assert RbacAuditLog.__tablename__ == "rbac_audit_log"


def test_mappers_configure() -> None:
    configure_mappers()  # raises if any mapping is invalid


def test_role_has_scope_and_is_system() -> None:
    cols = Role.__table__.columns
    assert "scope" in cols and "workspace_id" in cols
    assert "is_system" in cols and "key" in cols


def test_user_role_columns() -> None:
    cols = UserRole.__table__.columns
    for c in ("auth_user_id", "role_id", "workspace_id", "granted_by", "granted_at"):
        assert c in cols
