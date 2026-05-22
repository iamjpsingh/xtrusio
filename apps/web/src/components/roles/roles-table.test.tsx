import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import { RolesTable } from "./roles-table";

const ROLES: PlatformRoleOut[] = [
  {
    id: "r1",
    key: "super_admin",
    name: "Super admin",
    description: null,
    is_system: true,
    permission_keys: [],
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    id: "r2",
    key: "dispatcher",
    name: "Dispatcher",
    description: "Routes requests",
    is_system: false,
    permission_keys: ["platform.users.read"],
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

describe("<RolesTable />", () => {
  it("renders every role", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("super_admin")).toBeInTheDocument();
    expect(screen.getByText("dispatcher")).toBeInTheDocument();
  });

  it("shows a system badge for is_system rows and hides their action buttons", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText(/system/i)).toBeInTheDocument();
    // The super_admin row's action buttons should be hidden.
    const superRow = screen.getByText("super_admin").closest("tr");
    if (!superRow) throw new Error("super_admin row not found");
    expect(superRow.querySelector('[aria-label^="Edit"]')).toBeNull();
    expect(superRow.querySelector('[aria-label^="Delete"]')).toBeNull();
    // The dispatcher row's buttons should be present.
    const dispatcherRow = screen.getByText("dispatcher").closest("tr");
    if (!dispatcherRow) throw new Error("dispatcher row not found");
    expect(dispatcherRow.querySelector('[aria-label^="Edit"]')).not.toBeNull();
  });

  it("hides all action buttons when canManage is false", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage={false}
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("fires onEdit / onDelete with the row's role", async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /edit dispatcher/i }),
    );
    expect(onEdit).toHaveBeenCalledWith(ROLES[1]);
    await userEvent.click(
      screen.getByRole("button", { name: /delete dispatcher/i }),
    );
    expect(onDelete).toHaveBeenCalledWith(ROLES[1]);
  });
});
