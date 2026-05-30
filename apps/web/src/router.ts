import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { NotFound } from "@/components/not-found";

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  // Friendly, recoverable 404 instead of TanStack's bare "Not Found" text.
  defaultNotFoundComponent: NotFound,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
