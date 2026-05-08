import { LayoutDashboard, Users, Building2, Settings, type LucideIcon } from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
};

export const platformNav: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/users", label: "Users", icon: Users },
  { to: "/clients", label: "Clients", icon: Building2 },
  { to: "/settings", label: "Settings", icon: Settings },
];
