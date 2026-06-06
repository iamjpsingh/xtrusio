import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchAuditCatalog: vi.fn().mockResolvedValue({
      categories: [
        { key: "roles", label: "Roles" },
        { key: "invites", label: "Invites" },
      ],
      actions: [],
    }),
  };
});

import * as api from "@/lib/api";
import { AuditCategoryFilter } from "./audit-category-filter";

function renderWith(value: string | null, onChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AuditCategoryFilter value={value} onChange={onChange} />
    </QueryClientProvider>,
  );
  return onChange;
}

describe("<AuditCategoryFilter />", () => {
  it("renders the trigger with the 'All categories' placeholder when unfiltered", async () => {
    renderWith(null);
    expect(screen.getByRole("combobox", { name: /filter by category/i })).toBeInTheDocument();
    await waitFor(() => expect(api.fetchAuditCatalog).toHaveBeenCalled());
    expect(screen.getByText("All categories")).toBeInTheDocument();
  });
});
