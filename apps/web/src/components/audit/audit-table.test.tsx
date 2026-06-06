import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AuditEventOut } from "@xtrusio/api-types";
import { AuditTable } from "./audit-table";

const EVENTS: AuditEventOut[] = [
  {
    id: 1,
    actor_auth_user_id: "u-1",
    actor_email: "ana@acme.com",
    action: "platform_role.update",
    target_type: "role",
    target_id: "11111111-1111-1111-1111-111111111111",
    scope: "platform",
    workspace_id: null,
    before: null,
    after: { key: "dispatcher" },
    action_label: "Updated platform role",
    category: "roles",
    created_at: "2026-05-22T10:00:00Z",
  },
  {
    id: 2,
    actor_auth_user_id: null,
    actor_email: null,
    action: "system_event",
    target_type: "role",
    target_id: "22222222-2222-2222-2222-222222222222",
    scope: "platform",
    workspace_id: null,
    before: null,
    after: null,
    action_label: "System Event",
    category: "other",
    created_at: "2026-05-22T09:00:00Z",
  },
];

function firstEvent(): AuditEventOut {
  const e = EVENTS[0];
  if (!e) throw new Error("EVENTS[0] missing");
  return e;
}

describe("<AuditTable />", () => {
  it("renders the human action label plus the raw action for every row", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    expect(screen.getByText("ana@acme.com")).toBeInTheDocument();
    // Human label is primary, raw machine action is the mono subtitle.
    expect(screen.getByText("Updated platform role")).toBeInTheDocument();
    expect(screen.getByText("platform_role.update")).toBeInTheDocument();
    expect(screen.getByText("System Event")).toBeInTheDocument();
    expect(screen.getByText("system_event")).toBeInTheDocument();
  });

  it("renders the role label from the snapshot and the category badge", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    // role pulled from after.key ("dispatcher")
    expect(screen.getByText("dispatcher")).toBeInTheDocument();
    expect(screen.getByText("roles")).toBeInTheDocument();
    expect(screen.getByText("other")).toBeInTheDocument();
  });

  it("renders '—' for null actor_email and a roleless event", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    // event 2 has a null actor AND no role → at least two em-dashes.
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("truncates target_id and exposes the full id as a title attribute", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    const target = screen.getByTitle("11111111-1111-1111-1111-111111111111");
    expect(target.textContent).not.toEqual("11111111-1111-1111-1111-111111111111");
    expect(target.textContent?.length ?? 0).toBeLessThan(20);
  });

  it("fires onSelect with the clicked event", async () => {
    const onSelect = vi.fn();
    render(<AuditTable events={EVENTS} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("platform_role.update"));
    expect(onSelect).toHaveBeenCalledWith(firstEvent());
  });
});
