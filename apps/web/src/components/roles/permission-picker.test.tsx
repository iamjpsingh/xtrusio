import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionDef } from "@xtrusio/api-types";
import { PermissionPicker } from "./permission-picker";

const CATALOG: PermissionDef[] = [
  {
    scope: "platform",
    key: "platform.roles.manage",
    category: "Access control",
    description: "Create/edit/delete platform roles",
  },
  {
    scope: "platform",
    key: "platform.users.read",
    category: "Platform users",
    description: "View platform users",
  },
  {
    scope: "platform",
    key: "platform.users.invite",
    category: "Platform users",
    description: "Invite platform users",
  },
  {
    scope: "workspace",
    key: "workspace.roles.manage",
    category: "Access control",
    description: "Create/edit/delete workspace roles",
  },
  {
    scope: "workspace",
    key: "workspace.members.read",
    category: "Members",
    description: "View workspace members",
  },
];

describe("<PermissionPicker />", () => {
  it("renders only the permissions matching the scope prop", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("platform.roles.manage")).toBeInTheDocument();
    expect(screen.queryByText("workspace.roles.manage")).not.toBeInTheDocument();
  });

  it("groups permissions by category", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Access control")).toBeInTheDocument();
    expect(screen.getByText("Platform users")).toBeInTheDocument();
  });

  it("emits onChange with the toggled key added", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.roles.manage/i }),
    );
    expect(onChange).toHaveBeenCalledWith(["platform.roles.manage"]);
  });

  it("emits onChange with the toggled key removed when already present", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.roles.manage"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.roles.manage/i }),
    );
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("per-category select-all adds every key in that category and only that category", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /select all platform users/i }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining(["platform.users.read", "platform.users.invite"]),
    );
    const firstCall = onChange.mock.calls[0];
    if (!firstCall) throw new Error("onChange not called");
    expect(firstCall[0]).not.toContain("platform.roles.manage");
  });
});
