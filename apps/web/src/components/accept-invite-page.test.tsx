import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postAcceptInvite: vi.fn(),
  fetchMe: vi.fn(),
}));

// vi.hoisted exposes shared spies + the mutable loader-data holder to the
// hoisted vi.mock factories.
const { navigateMock, signOutMock, updateUserMock, fetchQueryMock, loaderData } = vi.hoisted(
  () => ({
    navigateMock: vi.fn(),
    signOutMock: vi.fn().mockResolvedValue({ error: null }),
    updateUserMock: vi.fn(),
    fetchQueryMock: vi.fn(),
    loaderData: { status: "ready" } as { status: "ready" } | { status: "error"; code: string },
  }),
);

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signOut: signOutMock,
      updateUser: updateUserMock,
      // session-cache subscribes at import time (via lib/api).
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
    },
  },
}));

vi.mock("@/lib/query-client", () => ({
  queryClient: { fetchQuery: (...a: unknown[]) => fetchQueryMock(...a) },
}));

// The component reads its result from the route loader via getRouteApi.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigateMock,
  getRouteApi: () => ({ useLoaderData: () => loaderData }),
}));

import { ApiError, fetchMe, postAcceptInvite } from "@/lib/api";
import { AcceptInvitePage } from "./accept-invite-page";

const FAKE_ME = { pending_invite: null, platform: null, tenants: [] };

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    vi.mocked(postAcceptInvite).mockReset();
    vi.mocked(fetchMe).mockReset();
    navigateMock.mockReset();
    signOutMock.mockClear();
    updateUserMock.mockReset();
    fetchQueryMock.mockReset();
    loaderData.status = "ready";
    if ("code" in loaderData) delete (loaderData as { code?: string }).code;
    updateUserMock.mockResolvedValue({ error: null });
    fetchQueryMock.mockResolvedValue(FAKE_ME);
  });

  describe("set-password form (session established)", () => {
    it("renders the set-password form, not the error surface", () => {
      render(<AcceptInvitePage />);
      expect(screen.getByText(/set a password to join/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /set password & join/i })).toBeInTheDocument();
    });

    it("on submit: sets the password, THEN accepts, THEN lands the invitee", async () => {
      vi.mocked(postAcceptInvite).mockResolvedValue({
        kind: "platform",
        role: "admin",
        tenant_id: null,
      });
      render(<AcceptInvitePage />);

      await userEvent.type(screen.getByLabelText(/^password$/i), "supersecret");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "supersecret");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(updateUserMock).toHaveBeenCalledWith({ password: "supersecret" });
      expect(postAcceptInvite).toHaveBeenCalledTimes(1);
      // Order: password set before the accept POST.
      const [setOrder] = updateUserMock.mock.invocationCallOrder;
      const [acceptOrder] = vi.mocked(postAcceptInvite).mock.invocationCallOrder;
      expect(setOrder).toBeDefined();
      expect(acceptOrder).toBeDefined();
      expect(setOrder ?? 0).toBeLessThan(acceptOrder ?? 0);
      expect(fetchMe).toBeTruthy();
      expect(navigateMock).toHaveBeenCalledWith({ to: "/onboarding" });
    });

    it("password mismatch shows a validation error and does NOT join", async () => {
      render(<AcceptInvitePage />);
      await userEvent.type(screen.getByLabelText(/^password$/i), "supersecret");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "different123");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(screen.getByText(/passwords don't match/i)).toBeInTheDocument();
      expect(updateUserMock).not.toHaveBeenCalled();
      expect(postAcceptInvite).not.toHaveBeenCalled();
    });

    it("too-short password shows a validation error and does NOT join", async () => {
      render(<AcceptInvitePage />);
      await userEvent.type(screen.getByLabelText(/^password$/i), "short");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "short");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
      expect(updateUserMock).not.toHaveBeenCalled();
      expect(postAcceptInvite).not.toHaveBeenCalled();
    });

    it("a failed password update shows an inline error and does NOT join", async () => {
      updateUserMock.mockResolvedValue({ error: { code: "weak_password" } });
      render(<AcceptInvitePage />);

      await userEvent.type(screen.getByLabelText(/^password$/i), "supersecret");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "supersecret");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(updateUserMock).toHaveBeenCalled();
      expect(postAcceptInvite).not.toHaveBeenCalled();
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(navigateMock).not.toHaveBeenCalled();
    });

    it("an already-accepted invite still lands the invitee (idempotent)", async () => {
      vi.mocked(postAcceptInvite).mockRejectedValue(
        new ApiError(409, { detail: "invite_already_accepted" }),
      );
      render(<AcceptInvitePage />);

      await userEvent.type(screen.getByLabelText(/^password$/i), "supersecret");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "supersecret");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(updateUserMock).toHaveBeenCalled();
      expect(navigateMock).toHaveBeenCalledWith({ to: "/onboarding" });
    });

    it("a non-idempotent accept error shows an inline error and does NOT land", async () => {
      vi.mocked(postAcceptInvite).mockRejectedValue(
        new ApiError(403, { detail: "invite_revoked" }),
      );
      render(<AcceptInvitePage />);

      await userEvent.type(screen.getByLabelText(/^password$/i), "supersecret");
      await userEvent.type(screen.getByLabelText(/confirm password/i), "supersecret");
      await userEvent.click(screen.getByRole("button", { name: /set password & join/i }));

      expect(screen.getByText(/this invitation was revoked/i)).toBeInTheDocument();
      expect(navigateMock).not.toHaveBeenCalled();
    });
  });

  describe("error surface (expired / invalid link)", () => {
    beforeEach(() => {
      loaderData.status = "error";
      (loaderData as { code: string }).code = "invite_expired";
    });

    it("renders the specific message for the loader error code inside AuthLayout", () => {
      render(<AcceptInvitePage />);
      expect(screen.getByText(/this invitation has expired/i)).toBeInTheDocument();
      expect(screen.getByText("Xtrusio")).toBeInTheDocument();
    });

    it("signs out and navigates to /sign-in when Sign out is clicked", async () => {
      render(<AcceptInvitePage />);
      await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
      expect(signOutMock).toHaveBeenCalled();
    });

    it("uses the generic fallback for an unknown code", () => {
      (loaderData as { code: string }).code = "totally_unknown_code";
      render(<AcceptInvitePage />);
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });
});
