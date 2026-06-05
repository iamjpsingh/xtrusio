import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionDef, PlatformRoleOut } from "@xtrusio/api-types";
import { RoleFormDialog } from "./role-form-dialog";
import { errorMessage } from "@/lib/error-messages";

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
    expect(screen.getByLabelText("Key")).toHaveValue("");
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("leads with the Name field before the Key field", () => {
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
    const inputs = screen.getAllByRole("textbox");
    // Name input precedes Key input in the DOM order.
    const nameIdx = inputs.indexOf(screen.getByLabelText("Name"));
    const keyIdx = inputs.indexOf(screen.getByLabelText("Key"));
    expect(nameIdx).toBeGreaterThanOrEqual(0);
    expect(nameIdx).toBeLessThan(keyIdx);
  });

  it("renders a DialogDescription for accessibility", () => {
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
    expect(screen.getByText(/bundle permissions into a reusable role/i)).toBeInTheDocument();
  });

  it("renders a scrollable body container so the footer stays visible", () => {
    const { container } = render(
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
    expect(container.ownerDocument.querySelector(".overflow-y-auto")).not.toBeNull();
  });

  it("shows a live selected-permissions count in the footer", () => {
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
    expect(screen.getByText(/1 permission selected/i)).toBeInTheDocument();
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
    expect(screen.getByLabelText("Key")).toHaveValue("dispatcher");
    expect(screen.getByLabelText("Key")).toBeDisabled();
    expect(screen.getByLabelText("Name")).toHaveValue("Dispatcher");
    expect(screen.getByRole("checkbox", { name: /platform.users.read/i })).toBeChecked();
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
    await userEvent.type(screen.getByLabelText("Key"), "auditor");
    await userEvent.type(screen.getByLabelText("Name"), "Auditor");
    await userEvent.click(screen.getByRole("checkbox", { name: /platform.users.read/i }));
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
    expect(screen.getByText(/role with this key already exists/i)).toBeInTheDocument();
  });

  it("surfaces a friendly message for the sanitized privilege_escalation save error", () => {
    // The backend (slice #65) returns a bare `privilege_escalation` detail;
    // the page maps it via errorMessage(errorCode(e)) and passes it here.
    const friendly = errorMessage("privilege_escalation");
    expect(friendly).toMatch(/you can only include permissions you currently hold/i);
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={friendly}
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.getByText(/you can only include permissions you currently hold/i),
    ).toBeInTheDocument();
  });
});
