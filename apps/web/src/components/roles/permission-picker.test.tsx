import { render, screen, within } from "@testing-library/react";
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
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    expect(screen.getByText("platform.roles.manage")).toBeInTheDocument();
    expect(screen.queryByText("workspace.roles.manage")).not.toBeInTheDocument();
  });

  it("groups permissions into category cards", () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    expect(screen.getByText("Access control")).toBeInTheDocument();
    expect(screen.getByText("Platform users")).toBeInTheDocument();
  });

  it("promotes the human description as the row label and demotes the key", () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    // The description labels the checkbox; the machine key is secondary text.
    expect(screen.getByText("Create/edit/delete platform roles")).toBeInTheDocument();
    expect(screen.getByText("platform.roles.manage")).toBeInTheDocument();
  });

  it("toggling the row label adds the key", async () => {
    const onChange = vi.fn();
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /platform.roles.manage/i }));
    expect(onChange).toHaveBeenCalledWith(["platform.roles.manage"]);
  });

  it("toggling an already-selected key removes it", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.roles.manage"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: /platform.roles.manage/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("tri-state category checkbox selects all rows in that category when not full", async () => {
    const onChange = vi.fn();
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /select all platform users/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining(["platform.users.read", "platform.users.invite"]),
    );
    const firstCall = onChange.mock.calls[0];
    if (!firstCall) throw new Error("onChange not called");
    expect(firstCall[0]).not.toContain("platform.roles.manage");
  });

  it("tri-state category checkbox clears all rows in that category when already full", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.users.read", "platform.users.invite"]}
        onChange={onChange}
      />,
    );
    const catBox = screen.getByRole("checkbox", {
      name: /select all platform users/i,
    });
    expect(catBox).toBeChecked();
    await userEvent.click(catBox);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("category checkbox is indeterminate when partially selected", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.users.read"]}
        onChange={() => {}}
      />,
    );
    const catBox = screen.getByRole("checkbox", {
      name: /select all platform users/i,
    });
    expect(catBox).toHaveAttribute("data-state", "indeterminate");
  });

  it("shows per-category and global selected counts", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.users.read"]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    // Platform users category card shows "1 / 2".
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("global select-all emits every in-scope key; clear-all empties it", async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /select all/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining([
        "platform.roles.manage",
        "platform.users.read",
        "platform.users.invite",
      ]),
    );

    onChange.mockClear();
    rerender(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.roles.manage", "platform.users.read", "platform.users.invite"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /clear all/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("search filters rows by key or description", async () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    const search = screen.getByRole("searchbox", { name: /search permissions/i });
    await userEvent.type(search, "invite");
    expect(screen.getByText("platform.users.invite")).toBeInTheDocument();
    expect(screen.queryByText("platform.roles.manage")).not.toBeInTheDocument();
    expect(screen.queryByText("Create/edit/delete platform roles")).not.toBeInTheDocument();
  });

  it("search by description text matches", async () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    const search = screen.getByRole("searchbox", { name: /search permissions/i });
    await userEvent.type(search, "delete");
    expect(screen.getByText("platform.roles.manage")).toBeInTheDocument();
    expect(screen.queryByText("platform.users.invite")).not.toBeInTheDocument();
  });

  it("shows an empty hint when no rows match the search", async () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    const search = screen.getByRole("searchbox", { name: /search permissions/i });
    await userEvent.type(search, "zzznope");
    expect(screen.getByText(/no permissions match/i)).toBeInTheDocument();
  });

  it("orders categories deterministically (alphabetical)", () => {
    render(<PermissionPicker catalog={CATALOG} scope="platform" value={[]} onChange={() => {}} />);
    const headings = screen
      .getAllByText(/Access control|Platform users/)
      .map((el) => el.textContent);
    expect(headings).toEqual(["Access control", "Platform users"]);
  });

  it("renders workspace-scope permissions when scope=workspace", () => {
    render(<PermissionPicker catalog={CATALOG} scope="workspace" value={[]} onChange={() => {}} />);
    expect(screen.getByText("workspace.roles.manage")).toBeInTheDocument();
    expect(screen.getByText("workspace.members.read")).toBeInTheDocument();
    expect(screen.queryByText("platform.roles.manage")).not.toBeInTheDocument();
    // Members card has a single (unselected) row.
    const membersCard = screen.getByText("Members").closest("section");
    if (!membersCard) throw new Error("Members card not found");
    expect(within(membersCard).getByText("0 / 1")).toBeInTheDocument();
  });
});
