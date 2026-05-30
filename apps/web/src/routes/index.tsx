// apps/web/src/routes/index.tsx
// Root index route. `/` is never a content page — it exists ONLY so the router
// has a real match for `/` (otherwise it raises a notFound → the "Not Found
// after login" bug). The actual redirect is owned by <AuthGuard> in __root,
// which already resolves `/` to the user's landing (platform / workspace /
// onboarding) or to /sign-in. AuthGuard short-circuits (returns null while it
// redirects), so this component never actually renders.
//
// We deliberately do NOT put a redirecting `beforeLoad` here: doing so raced
// AuthGuard and, on a stale/expired session, bounced the user to /sign-in in a
// loop.
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: () => null,
});
