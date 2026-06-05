import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SearchTrigger } from "./search-trigger";

describe("<SearchTrigger />", () => {
  it("shows neutral, user-facing empty copy with no internal plan reference", async () => {
    render(<SearchTrigger />);
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() =>
      expect(screen.getByText(/search isn.t available yet/i)).toBeInTheDocument(),
    );
    // The old dev placeholder leaked an internal milestone to end users.
    expect(screen.queryByText(/plan 1e/i)).toBeNull();
    expect(screen.queryByText(/wired up/i)).toBeNull();
  });
});
