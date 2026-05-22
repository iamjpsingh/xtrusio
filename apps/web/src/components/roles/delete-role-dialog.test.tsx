import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import { DeleteRoleDialog } from "./delete-role-dialog";

const ROLE: PlatformRoleOut = {
  id: "r1",
  key: "dispatcher",
  name: "Dispatcher",
  description: null,
  is_system: false,
  permission_keys: ["platform.users.read"],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

describe("<DeleteRoleDialog />", () => {
  it("renders the cascade-warning copy", () => {
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.getByText(/anyone currently granted this role will lose it/i),
    ).toBeInTheDocument();
  });

  it("fires onConfirm once on confirm", async () => {
    const onConfirm = vi.fn();
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={onConfirm}
        onOpenChange={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("closes silently on cancel without firing onConfirm", async () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not render when role is null", () => {
    render(
      <DeleteRoleDialog
        role={null}
        pending={false}
        onConfirm={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
