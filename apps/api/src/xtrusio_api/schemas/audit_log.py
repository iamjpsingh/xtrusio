"""Pydantic schemas for the audit-log viewer.

`rbac_audit_log.id` is `bigint` (NOT uuid) and `target_id` is `text` (NOT
uuid) — both decisions were made when the schema landed in P2 so the audit
table can record actions against arbitrary targets (workspace ids, invite
tokens, future non-uuid identifiers). The schema below mirrors those types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from ..core.audit_catalog import describe_action


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_auth_user_id: UUID | None
    actor_email: str | None
    action: str
    target_type: str
    target_id: str
    scope: str
    workspace_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime

    # Derived from ``action`` via the event catalog (no service change — these
    # serialise automatically). No name clash: the model has no ``category``
    # field, so ``action_label``/``category`` are safe per the plan.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_label(self) -> str:
        return describe_action(self.action)[0]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category(self) -> str:
        return describe_action(self.action)[1]


class AuditEventsPage(BaseModel):
    items: list[AuditEventOut]
    next_cursor: str | None = None
