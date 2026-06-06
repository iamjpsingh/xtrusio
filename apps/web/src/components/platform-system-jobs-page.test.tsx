import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { JobRunsPage, MeResponse } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { server } from "@/test/msw/server";
import { installMswServer } from "@/test/msw/install";
import { meSuperAdmin } from "@/test/msw/fixtures";
import { PlatformSystemJobsPage } from "./platform-system-jobs-page";

vi.mock("@/lib/session-cache", () => ({
  resolveSession: vi.fn().mockResolvedValue({ access_token: "test-tok" }),
  getCachedSession: vi.fn().mockReturnValue({ access_token: "test-tok" }),
}));

installMswServer();

const API = "http://api.test.invalid";

const RUN_OK = {
  id: 1,
  job_name: "invite_email_outbox",
  status: "success",
  started_at: "2026-06-06T09:00:00Z",
  finished_at: "2026-06-06T09:00:01Z",
  duration_ms: 1200,
  items_processed: 3,
  items_succeeded: 3,
  items_failed: 0,
  detail: null,
  created_at: "2026-06-06T09:00:01Z",
};
const RUN_ERR = {
  ...RUN_OK,
  id: 2,
  status: "partial",
  duration_ms: 65000,
  items_succeeded: 1,
  items_failed: 2,
  detail: { errors: ["smtp timeout"] },
};

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
        <PlatformSystemJobsPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("<PlatformSystemJobsPage />", () => {
  it("renders <Forbidden /> when me lacks platform.audit.read", async () => {
    server.use(http.get(`${API}/api/me`, () => HttpResponse.json(meWithout())));
    renderWith(newClient());
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("renders job runs with status + duration", async () => {
    server.use(
      http.get(`${API}/api/platform/job-runs`, () =>
        HttpResponse.json<JobRunsPage>({ items: [RUN_OK, RUN_ERR], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getAllByText("invite_email_outbox").length).toBeGreaterThanOrEqual(2);
    });
    expect(screen.getByText("1.2s")).toBeInTheDocument();
    expect(screen.getByText("1m 5s")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
  });

  it("opens the detail drawer with the run's errors", async () => {
    server.use(
      http.get(`${API}/api/platform/job-runs`, () =>
        HttpResponse.json<JobRunsPage>({ items: [RUN_ERR], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("partial"));
    await userEvent.click(screen.getByText("invite_email_outbox"));
    await waitFor(() => expect(screen.getByText("smtp timeout")).toBeInTheDocument());
  });
});
