import { getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { Forbidden } from "@/components/forbidden";
import { ScopedRolesPage } from "@/components/scoped-roles-page";

export function WorkspaceRolesPage({ workspaceId }: { workspaceId: string }) {
  // Deep-link fallback; the route's beforeLoad gate is the primary guard.
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.roles.manage")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <ScopedRolesPage scope="workspace" workspaceId={workspaceId} />;
}
