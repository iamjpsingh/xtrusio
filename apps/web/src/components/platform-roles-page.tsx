import { getDefaultLandingPath, hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { Forbidden } from "@/components/forbidden";
import { ScopedRolesPage } from "@/components/scoped-roles-page";

export function PlatformRolesPage() {
  // Deep-link fallback; the route's beforeLoad gate is the primary guard.
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.roles.manage")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <ScopedRolesPage scope="platform" />;
}
