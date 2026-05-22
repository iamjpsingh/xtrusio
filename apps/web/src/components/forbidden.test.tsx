import { render, screen } from "@testing-library/react";
import {
  RouterContextProvider,
  createMemoryHistory,
  createRouter,
} from "@tanstack/react-router";
import { describe, expect, it } from "vitest";
import { routeTree } from "@/routeTree.gen";
import { Forbidden } from "./forbidden";

function renderForbidden(landingPath: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(
    <RouterContextProvider router={router}>
      <Forbidden landingPath={landingPath} />
    </RouterContextProvider>,
  );
}

describe("<Forbidden />", () => {
  it("renders the access-denied message and a link to the landing path", () => {
    renderForbidden("/platform");
    expect(
      screen.getByText(/don't have access|don't have permission/i),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /go back|home/i });
    expect(link).toHaveAttribute("href", "/platform");
  });
});
