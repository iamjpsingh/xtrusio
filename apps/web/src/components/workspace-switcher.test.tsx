import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";

const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
  useRouterState: () => ({ location: { pathname: "/platform" } }),
}));

import { WorkspaceSwitcher } from "./workspace-switcher";
import { readLastWorkspace } from "@/lib/last-workspace";

function renderSwitcher(me: {
  platform: { role: "super_admin"; is_active: true } | null;
  tenants: { id: string; slug: string; name: string; role: "owner"; permissions: string[] }[];
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: me.platform,
    platform_permissions: me.platform ? ["platform.users.read"] : [],
    tenants: me.tenants,
    pending_invite: null,
  });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceSwitcher />
    </QueryClientProvider>,
  );
}

describe("WorkspaceSwitcher", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    window.localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("lists every tenant in the dropdown", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [
        { id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] },
        { id: "t2", slug: "beta", name: "Beta Co", role: "owner", permissions: [] },
      ],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Beta Co")).toBeInTheDocument();
  });

  it("shows 'Platform admin' only when me.platform is present", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    // "Platform admin" also labels the trigger when the active scope is
    // platform, so assert on the menu item specifically.
    expect(screen.getByRole("menuitem", { name: /platform admin/i })).toBeInTheDocument();
  });

  it("hides 'Platform admin' when me.platform is null", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: null,
      tenants: [{ id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] }],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    expect(screen.queryByText(/platform admin/i)).toBeNull();
  });

  it("navigates to /workspace/<id> and persists last-selected on tenant click", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [{ id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] }],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    await user.click(screen.getByText("Acme"));
    expect(navigateMock).toHaveBeenCalledWith({
      to: "/workspace/$workspaceId",
      params: { workspaceId: "t1" },
    });
    expect(readLastWorkspace()).toBe("t1");
  });

  it("navigates to /platform and persists the platform sentinel on 'Platform admin' click", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    await user.click(screen.getByRole("menuitem", { name: /platform admin/i }));
    expect(navigateMock).toHaveBeenCalledWith({ to: "/platform" });
    expect(readLastWorkspace()).toBe("__platform__");
  });
});
