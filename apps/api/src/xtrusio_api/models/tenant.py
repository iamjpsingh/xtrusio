"""Tenant model."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, DateTime, ForeignKey, Table, Text, Uuid, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")

# L15: Supabase's ``auth.users`` is owned by GoTrue, not this project, so it has
# no ORM model. We register a minimal Core ``Table`` stub in the SAME metadata
# purely so string ``ForeignKey("auth.users.id")`` references on our own models
# resolve at mapper-configuration time. It is NEVER emitted by migrations:
# Alembic autogenerate is not used here (all migrations are hand-written raw
# SQL) and ``context.configure`` does not set ``include_schemas=True``, so the
# non-default ``auth`` schema is excluded from any autogenerate comparison.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", Uuid, primary_key=True),
    schema="auth",
)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # FK to auth.users(id) is enforced at DB level (see migration 0001). The
    # ORM-level ForeignKey resolves against the ``auth.users`` Table stub above
    # (L15) so the relationship is introspectable; it is no-op against the DB
    # (the constraint already exists). ``ondelete="RESTRICT"`` documents the
    # intent — the actual ON DELETE behaviour is whatever 0001 declared.
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False
    )


class TenantIn(BaseModel):
    slug: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be 3-64 chars, lowercase, start/end alphanumeric, "
                "allow a-z 0-9 and hyphen between"
            )
        return v


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    created_at: datetime
    updated_at: datetime
    created_by: UUID


class TenantsPage(BaseModel):
    items: list[TenantOut]
    next_cursor: str | None = None
