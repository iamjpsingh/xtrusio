// packages/api-types/src/audit-log.ts
// Mirror of apps/api/src/xtrusio_api/schemas/audit_log.py. Note `id` is a
// bigint server-side but JSON-serialises as a JS number — fine for cursor
// page sizes well under 2^53.

export type AuditEventOut = {
  id: number;
  actor_auth_user_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: string;
  scope: "platform" | "workspace";
  workspace_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type AuditEventsPage = {
  items: AuditEventOut[];
  next_cursor: string | null;
};
