import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postAcceptInvite: vi.fn(),
}));

// vi.hoisted exposes shared spies + the mutable loader-data holder to the
// hoisted vi.mock factories.
const { navigateMock, signOutMock, loaderData } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  signOutMock: vi.fn().mockResolvedValue({ error: null }),
  loaderData: { code: "invite_expired" as string },
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signOut: signOutMock,
      // session-cache subscribes at import time (via lib/api).
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
    },
  },
}));

// The component reads its error code from the route loader via getRouteApi.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigateMock,
  getRouteApi: () => ({ useLoaderData: () => loaderData }),
}));

import { ApiError, postAcceptInvite } from "@/lib/api";
import { AcceptInvitePage } from "./accept-invite-page";

describe("AcceptInvitePage (loader-driven error view)", () => {
  beforeEach(() => {
    vi.mocked(postAcceptInvite).mockReset();
    navigateMock.mockReset();
    signOutMock.mockClear();
    loaderData.code = "invite_expired";
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
    loaderData.code = "totally_unknown_code";
    render(<AcceptInvitePage />);
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("does not import the old useEffect/useRef auto-post path", () => {
    // postAcceptInvite is now called by the route loader, not the component.
    render(<AcceptInvitePage />);
    expect(ApiError).toBeTruthy();
    expect(postAcceptInvite).not.toHaveBeenCalled();
  });
});
