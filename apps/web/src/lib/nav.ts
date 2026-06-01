import {
  LayoutDashboard,
  Users,
  Building2,
  Settings,
  Shield,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

/** Sidebar section a nav item belongs to. Drives the grouped rendering. */
export type NavGroup = "overview" | "manage" | "settings";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Permission catalog key required to see this item. */
  required_perm: string;
  /** Sidebar section. Defaults to "manage" when omitted. */
  group?: NavGroup;
};

/** A rendered sidebar section: an optional heading + its visible items. */
export type NavSection = {
  group: NavGroup;
  label: string | null;
  items: NavItem[];
};

const GROUP_ORDER: NavGroup[] = ["overview", "manage", "settings"];

/**
 * Human heading per group. `null` renders no `SidebarGroupLabel`:
 * - `overview` (Dashboard / Overview) leads, unlabelled.
 * - `manage` carries the "Manage" heading so the admin items read as a set.
 * - `settings` is unlabelled and set apart purely by being its own
 *   `SidebarGroup` (extra vertical padding) — this also avoids a duplicate
 *   "Settings" heading clashing with the "Settings" nav item below it.
 */
const GROUP_LABEL: Record<NavGroup, string | null> = {
  overview: null,
  manage: "Manage",
  settings: null,
};

/**
 * Whether a nav `to` should read as active for the current pathname.
 *
 * Index routes (the shell roots `/platform` and `/workspace/<id>`) match
 * exactly so they don't light up on every nested page. Every other item
 * matches its own path *and* any descendant (`/platform/clients/<slug>/users`
 * keeps the "Clients" item active), so deep links highlight their parent.
 */
export function isNavItemActive(pathname: string, to: string, isIndex: boolean): boolean {
  if (isIndex) return pathname === to;
  return pathname === to || pathname.startsWith(`${to}/`);
}

/**
 * Group a flat, already permission-filtered nav list into ordered sections,
 * dropping any section that has no visible items.
 */
export function groupNav(items: NavItem[]): NavSection[] {
  return GROUP_ORDER.map((group) => ({
    group,
    label: GROUP_LABEL[group],
    items: items.filter((i) => (i.group ?? "manage") === group),
  })).filter((section) => section.items.length > 0);
}

/**
 * Platform-shell nav. `to` paths are absolute; the Link component navigates
 * via TanStack Router.
 */
export const platformNav: NavItem[] = [
  {
    to: "/platform",
    label: "Dashboard",
    icon: LayoutDashboard,
    required_perm: "platform.users.read",
    group: "overview",
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
    group: "settings",
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
    group: "overview",
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
    group: "settings",
  },
];
