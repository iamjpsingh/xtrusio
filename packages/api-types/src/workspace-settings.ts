// packages/api-types/src/workspace-settings.ts
// Mirror of apps/api/src/xtrusio_api/schemas/workspace_settings.py. P6d MVP
// only exposes `name` as mutable; slug/timestamps are read-only.

export type WorkspaceSettingsOut = {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type WorkspaceSettingsUpdate = {
  name: string;
};
