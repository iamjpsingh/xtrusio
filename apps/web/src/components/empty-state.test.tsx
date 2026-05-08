import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Users } from "lucide-react";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(<EmptyState title="No items yet" description="Create the first one." />);
    expect(screen.getByRole("heading", { name: /no items yet/i })).toBeInTheDocument();
    expect(screen.getByText(/create the first one/i)).toBeInTheDocument();
  });

  it("renders an action button when provided", async () => {
    const onClick = vi.fn();
    render(<EmptyState title="x" description="y" action={{ label: "Create", onClick }} />);
    const button = screen.getByRole("button", { name: /create/i });
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders disabled action button without firing onClick", async () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        title="x"
        description="y"
        action={{ label: "Locked", onClick, disabled: true, reason: "Unavailable" }}
      />,
    );
    const button = screen.getByRole("button", { name: /locked/i });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("renders the icon when provided", () => {
    const { container } = render(<EmptyState icon={Users} title="x" description="y" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
