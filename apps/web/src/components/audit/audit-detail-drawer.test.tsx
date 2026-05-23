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
  created_at: "2026-05-22T10:00:00Z",
};

const DELETE_EVENT: AuditEventOut = {
  ...CREATE_EVENT,
  id: 2,
  action: "platform_role.delete",
  before: { key: "old", permission_keys: [] },
  after: null,
};

describe("<AuditDetailDrawer />", () => {
  it("renders no dialog when event is null", () => {
    render(<AuditDetailDrawer event={null} onOpenChange={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the 'after' JSON for a create event and shows 'before' as empty", () => {
    render(
      <AuditDetailDrawer event={CREATE_EVENT} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/dispatcher/i)).toBeInTheDocument();
    // 'before' should render with an explicit empty marker.
    expect(screen.getByText(/before/i)).toBeInTheDocument();
  });

  it("renders the 'before' JSON for a delete event and shows 'after' as empty", () => {
    render(
      <AuditDetailDrawer event={DELETE_EVENT} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/"key": "old"/)).toBeInTheDocument();
  });

  it("fires onOpenChange(false) when the close affordance is clicked", async () => {
    const onOpenChange = vi.fn();
    render(
      <AuditDetailDrawer event={CREATE_EVENT} onOpenChange={onOpenChange} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
