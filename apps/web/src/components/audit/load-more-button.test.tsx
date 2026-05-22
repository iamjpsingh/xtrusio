import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LoadMoreButton } from "./load-more-button";

describe("<LoadMoreButton />", () => {
  it("renders 'Load more' when a next cursor exists", () => {
    render(
      <LoadMoreButton nextCursor="abc" pending={false} onClick={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: /load more/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing when nextCursor is null", () => {
    const { container } = render(
      <LoadMoreButton nextCursor={null} pending={false} onClick={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows pending state and disables", () => {
    render(<LoadMoreButton nextCursor="abc" pending onClick={() => {}} />);
    const btn = screen.getByRole("button", { name: /loading/i });
    expect(btn).toBeDisabled();
  });

  it("fires onClick", async () => {
    const onClick = vi.fn();
    render(
      <LoadMoreButton nextCursor="abc" pending={false} onClick={onClick} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
