// apps/web/src/routes/_app.tsx
// Pathless layout for every authed page. The two physically-separate shells
// live in `_app.platform.tsx` and `_app.workspace.$workspaceId.tsx`. This
// file intentionally renders only an Outlet so each shell owns its own
// SidebarProvider tree.
import { Outlet, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app")({
  component: AppPassthrough,
});

function AppPassthrough() {
  return <Outlet />;
}
