// apps/web/src/lib/nav.test.ts
//
// Pure-function coverage for the nav helpers that carry correctness:
//   - isNavItemActive — the active-state bug fix (index routes match EXACTLY so
//     they don't light up on every nested page; non-index items match their own
//     path AND any descendant).
//   - groupNav — group ordering + empty-section drop.
import { describe, expect, it } from "vitest";
import { groupNav, isNavItemActive, type NavItem } from "./nav";
import { LayoutDashboard, Users, Settings } from "lucide-react";

describe("isNavItemActive", () => {
  describe("index routes (isIndex = true) — exact match only", () => {
    it("is active only on the exact path", () => {
      expect(isNavItemActive("/platform", "/platform", true)).toBe(true);
      expect(isNavItemActive("/workspace/t1", "/workspace/t1", true)).toBe(true);
    });

    it("is NOT active on a nested/descendant path (the bug fix)", () => {
      // /platform must NOT stay highlighted while on /platform/users etc.
      expect(isNavItemActive("/platform/users", "/platform", true)).toBe(false);
      expect(isNavItemActive("/workspace/t1/members", "/workspace/t1", true)).toBe(false);
    });

    it("is NOT active on a sibling path", () => {
      expect(isNavItemActive("/platform-other", "/platform", true)).toBe(false);
    });
  });

  describe("non-index routes (isIndex = false) — prefix match", () => {
    it("is active on the exact path", () => {
      expect(isNavItemActive("/platform/clients", "/platform/clients", false)).toBe(true);
    });

    it("is active on any descendant path so deep links highlight their parent", () => {
      expect(isNavItemActive("/platform/clients/acme/users", "/platform/clients", false)).toBe(
        true,
      );
      expect(isNavItemActive("/workspace/t1/members/u1", "/workspace/t1/members", false)).toBe(
        true,
      );
    });

    it("is NOT active for a prefix that isn't a path-segment boundary", () => {
      // "/platform/clients" must not match "/platform/clients-archive" — the
      // descendant test uses a `${to}/` separator, not a bare startsWith.
      expect(isNavItemActive("/platform/clients-archive", "/platform/clients", false)).toBe(false);
    });

    it("is NOT active on an unrelated path", () => {
      expect(isNavItemActive("/platform/users", "/platform/clients", false)).toBe(false);
    });
  });
});

describe("groupNav", () => {
  const overview: NavItem = {
    to: "/x",
    label: "Overview",
    icon: LayoutDashboard,
    required_perm: "p",
    group: "overview",
  };
  const manageA: NavItem = { to: "/a", label: "A", icon: Users, required_perm: "p" }; // group omitted → "manage"
  const manageB: NavItem = {
    to: "/b",
    label: "B",
    icon: Users,
    required_perm: "p",
    group: "manage",
  };
  const settings: NavItem = {
    to: "/s",
    label: "Settings",
    icon: Settings,
    required_perm: "p",
    group: "settings",
  };

  it("returns sections in overview → manage → settings order regardless of input order", () => {
    const sections = groupNav([settings, manageA, overview]);
    expect(sections.map((s) => s.group)).toEqual(["overview", "manage", "settings"]);
  });

  it("treats an item with no `group` as 'manage'", () => {
    const sections = groupNav([manageA]);
    expect(sections).toEqual([{ group: "manage", label: "Manage", items: [manageA] }]);
  });

  it("drops sections that have no visible items", () => {
    // Only manage items present → overview + settings sections are dropped.
    const sections = groupNav([manageA, manageB]);
    expect(sections).toEqual([{ group: "manage", label: "Manage", items: [manageA, manageB] }]);
  });

  it("returns no sections for an empty list", () => {
    expect(groupNav([])).toEqual([]);
  });

  it("labels only the manage section ('Manage'); overview + settings are unlabelled", () => {
    const sections = groupNav([overview, manageA, settings]);
    const byGroup = Object.fromEntries(sections.map((s) => [s.group, s.label]));
    expect(byGroup.overview).toBeNull();
    expect(byGroup.manage).toBe("Manage");
    expect(byGroup.settings).toBeNull();
  });
});
