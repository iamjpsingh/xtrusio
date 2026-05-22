// packages/api-types/src/permission.ts
// Mirror of apps/api/src/xtrusio_api/schemas/permission.py. Frontend fetches
// /api/permissions/catalog once per session (staleTime: Infinity); the data
// only changes with a backend deploy.

export type PermissionScope = "platform" | "workspace";

export type PermissionDef = {
  scope: PermissionScope;
  key: string;
  category: string;
  description: string;
};

export type PermissionsCatalog = {
  items: PermissionDef[];
};
