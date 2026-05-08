import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { ThemeProvider } from "@/components/theme-provider";
import { routeTree } from "@/routeTree.gen";

function renderAt(initial: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  render(
    <ThemeProvider attribute="class" defaultTheme="system">
      <RouterProvider router={router} />
    </ThemeProvider>,
  );
}

describe("/ Dashboard route", () => {
  it("renders the welcome empty state", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /welcome to xtrusio/i })).toBeInTheDocument();
  });
});
