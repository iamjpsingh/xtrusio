import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { AuditEventsPage, MeResponse } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { server } from "@/test/msw/server";
import { installMswServer } from "@/test/msw/install";
import { auditEventCreate, auditEventDelete, meSuperAdmin } from "@/test/msw/fixtures";
import { PlatformAuditLogPage } from "./platform-audit-log-page";

// MSW-based (F.2): drive the page through the genuine `apiFetch` → network path.
// `resolveSession` is mocked so `apiFetch` reads a deterministic token without
// touching Supabase.
vi.mock("@/lib/session-cache", () => ({
  resolveSession: vi.fn().mockResolvedValue({ access_token: "test-tok" }),
  getCachedSession: vi.fn().mockReturnValue({ access_token: "test-tok" }),
}));

installMswServer();

const API = "http://api.test.invalid";

const EV_UPDATE = { ...auditEventCreate, id: 2, action: "platform_role.update" };

function meWithout(): MeResponse {
  return { ...meSuperAdmin, platform_permissions: [] };
}

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <PlatformAuditLogPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("<PlatformAuditLogPage />", () => {
  it("renders <Forbidden /> when me lacks platform.audit.read", async () => {
    server.use(http.get(`${API}/api/me`, () => HttpResponse.json(meWithout())));
    renderWith(newClient());
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("renders the first page of events", async () => {
    server.use(
      http.get(`${API}/api/platform/audit-log`, () =>
        HttpResponse.json<AuditEventsPage>({
          items: [auditEventCreate, EV_UPDATE],
          next_cursor: "next-1",
        }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.update")).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    // Cursor-paged handler: page 1 (no cursor) -> create + next_cursor; page 2
    // (cursor=next-1) -> delete + null. Verifies the cursor is actually round-
    // tripped through `apiFetch` query-string building.
    server.use(
      http.get(`${API}/api/platform/audit-log`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        if (cursor === "next-1") {
          return HttpResponse.json<AuditEventsPage>({
            items: [auditEventDelete],
            next_cursor: null,
          });
        }
        return HttpResponse.json<AuditEventsPage>({
          items: [auditEventCreate],
          next_cursor: "next-1",
        });
      }),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.delete")).toBeInTheDocument();
    });
  });

  it("opens the drawer with the clicked event", async () => {
    server.use(
      http.get(`${API}/api/platform/audit-log`, () =>
        HttpResponse.json<AuditEventsPage>({
          items: [auditEventCreate],
          next_cursor: null,
        }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByText("platform_role.create"));
    // The structured drawer renders snapshot values as leaves (not raw JSON):
    // the `key` field's "auditor" value appears only inside the drawer.
    await waitFor(() => expect(screen.getByText("auditor")).toBeInTheDocument());
  });
});
