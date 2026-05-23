import {
  LayoutDashboard,
  Users,
  Building2,
  Settings,
  Shield,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Permission catalog key required to see this item. */
  required_perm: string;
};

/**
 * Platform-shell nav. `to` paths are relative-to-app — the Link component
 * navigates via TanStack Router so use the absolute path.
 */
export const platformNav: NavItem[] = [
  {
    to: "/platform",
    label: "Dashboard",
    icon: LayoutDashboard,
    required_perm: "platform.users.read",
  },
  {
    to: "/platform/users",
    label: "Users",
    icon: Users,
    required_perm: "platform.users.read",
  },
  {
    to: "/platform/clients",
    label: "Clients",
    icon: Building2,
    required_perm: "platform.clients.read",
  },
  {
    to: "/platform/roles",
    label: "Roles",
    icon: Shield,
    required_perm: "platform.roles.manage",
  },
  {
    to: "/platform/audit-log",
    label: "Audit log",
    icon: ScrollText,
    required_perm: "platform.audit.read",
  },
  {
    to: "/platform/settings",
    label: "Settings",
    icon: Settings,
    required_perm: "platform.settings.read",
  },
];

/**
 * Workspace-shell nav. The Link `to` for these items is built at render time
 * by prefixing `/workspace/<id>`; the `to` here is the suffix only.
 */
export const workspaceNav: NavItem[] = [
  {
    to: "",
    label: "Overview",
    icon: LayoutDashboard,
    required_perm: "workspace.members.read",
  },
  {
    to: "/members",
    label: "Members",
    icon: Users,
    required_perm: "workspace.members.read",
  },
  {
    to: "/roles",
    label: "Roles",
    icon: Shield,
    required_perm: "workspace.roles.manage",
  },
  {
    to: "/audit-log",
    label: "Audit log",
    icon: ScrollText,
    required_perm: "workspace.audit.read",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: Settings,
    required_perm: "workspace.settings.read",
  },
];
