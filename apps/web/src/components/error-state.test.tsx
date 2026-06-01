import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "./error-state";

describe("ErrorState", () => {
  it("renders the default title and description", () => {
    render(<ErrorState />);
    expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();
    expect(screen.getByText(/check your connection and try again/i)).toBeInTheDocument();
  });

  it("renders a custom title and description", () => {
    render(<ErrorState title="Failed to load roles" description="The roles service is down." />);
    expect(screen.getByRole("heading", { name: /failed to load roles/i })).toBeInTheDocument();
    expect(screen.getByText(/the roles service is down/i)).toBeInTheDocument();
  });

  it("does NOT render the retry button when onRetry is omitted", () => {
    render(<ErrorState />);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("renders the retry button when onRetry is provided and calls it on click", async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} />);
    const button = screen.getByRole("button", { name: /try again/i });
    expect(button).toBeInTheDocument();
    await userEvent.click(button);
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
