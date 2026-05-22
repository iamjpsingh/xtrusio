import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionDef, PlatformRoleOut } from "@xtrusio/api-types";
import { RoleFormDialog } from "./role-form-dialog";

const CATALOG: PermissionDef[] = [
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
];

const EXISTING: PlatformRoleOut = {
  id: "role-1",
  key: "dispatcher",
  name: "Dispatcher",
  description: "Routes incoming requests",
  is_system: false,
  permission_keys: ["platform.users.read"],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

describe("<RoleFormDialog />", () => {
  it("renders an empty form in create mode", () => {
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/key/i)).toHaveValue("");
    expect(screen.getByLabelText(/name/i)).toHaveValue("");
  });

  it("prefills name/description/permissions in edit mode and disables the key field", () => {
    render(
      <RoleFormDialog
        mode="edit"
        role={EXISTING}
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/key/i)).toHaveValue("dispatcher");
    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    expect(screen.getByLabelText(/name/i)).toHaveValue("Dispatcher");
    expect(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    ).toBeChecked();
  });

  it("calls onSubmit with the form payload on save", async () => {
    const onSubmit = vi.fn();
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={onSubmit}
        onOpenChange={() => {}}
      />,
    );
    await userEvent.type(screen.getByLabelText(/key/i), "auditor");
    await userEvent.type(screen.getByLabelText(/name/i), "Auditor");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      key: "auditor",
      name: "Auditor",
      description: null,
      permission_keys: ["platform.users.read"],
    });
  });

  it("renders the error message in the footer", () => {
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error="A role with this key already exists."
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.getByText(/role with this key already exists/i),
    ).toBeInTheDocument();
  });
});
