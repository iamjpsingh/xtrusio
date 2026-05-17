"""RBAC ORM models: permissions, roles, role_permissions, user_roles, audit log."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    auth_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    granted_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RbacAuditLog(Base):
    __tablename__ = "rbac_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_auth_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    before: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
