import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AuditEventOut } from "@xtrusio/api-types";
import { AuditDetailDrawer } from "./audit-detail-drawer";

const CREATE_EVENT: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "ana@acme.com",
  action: "platform_role.create",
  target_type: "role",
  target_id: "tid",
  scope: "platform",
  workspace_id: null,
  before: null,
  after: { key: "dispatcher", permission_keys: ["platform.users.read"] },
  action_label: "Created platform role",
  category: "roles",
  created_at: "2026-05-22T10:00:00Z",
};

const DELETE_EVENT: AuditEventOut = {
  ...CREATE_EVENT,
  id: 2,
  action: "platform_role.delete",
  action_label: "Deleted platform role",
  before: { key: "old", permission_keys: [] },
  after: null,
};

const UPDATE_EVENT: AuditEventOut = {
  ...CREATE_EVENT,
  id: 3,
  action: "platform_role.update",
  action_label: "Updated platform role",
  before: { name: "Old name" },
  after: { name: "New name" },
};

describe("<AuditDetailDrawer />", () => {
  it("renders no dialog when event is null", () => {
    render(<AuditDetailDrawer event={null} onOpenChange={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the action label, category, and the 'after' leaf for a create event", () => {
    render(<AuditDetailDrawer event={CREATE_EVENT} onOpenChange={() => {}} />);
    expect(screen.getByText("Created platform role")).toBeInTheDocument();
    expect(screen.getByText("roles")).toBeInTheDocument();
    // structured diff renders the value as a leaf, not raw JSON.stringify.
    expect(screen.getByText("dispatcher")).toBeInTheDocument();
    // a humanized field label appears for the snapshot keys.
    expect(screen.getByText("Permission keys")).toBeInTheDocument();
    // before side of a create is explicitly empty (≥1 "empty" marker).
    expect(screen.getAllByText(/empty/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the 'before' leaf for a delete event", () => {
    render(<AuditDetailDrawer event={DELETE_EVENT} onOpenChange={() => {}} />);
    expect(screen.getByText("old")).toBeInTheDocument();
  });

  it("highlights a changed field row for an update event", () => {
    render(<AuditDetailDrawer event={UPDATE_EVENT} onOpenChange={() => {}} />);
    expect(screen.getByText("Old name")).toBeInTheDocument();
    expect(screen.getByText("New name")).toBeInTheDocument();
    const changedRow = document.querySelector('tr[data-changed="true"]');
    expect(changedRow).not.toBeNull();
  });

  it("fires onOpenChange(false) when the close affordance is clicked", async () => {
    const onOpenChange = vi.fn();
    render(<AuditDetailDrawer event={CREATE_EVENT} onOpenChange={onOpenChange} />);
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
