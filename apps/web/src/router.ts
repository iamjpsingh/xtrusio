import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { NotFound } from "@/components/not-found";
import { RouterError } from "@/components/router-error";

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  // Friendly, recoverable 404 instead of TanStack's bare "Not Found" text.
  defaultNotFoundComponent: NotFound,
  // A thrown query/loader renders a recoverable ErrorState (with retry wired to
  // the boundary `reset`) instead of TanStack's bare dev error overlay.
  defaultErrorComponent: RouterError,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
