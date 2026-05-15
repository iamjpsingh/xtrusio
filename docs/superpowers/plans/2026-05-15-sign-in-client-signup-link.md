# Conditional Client-Signup Link on Sign-In — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a platform-admin-gated "Client sign up" link on the sign-in page that routes only to the existing client/org self-serve signup — never to platform-user creation.

**Architecture:** Split `routes/sign-in.tsx` into a thin route wrapper plus `components/sign-in-page.tsx` (HANDOFF gotcha #4 pattern). The component fetches signup status via the existing `fetchSignupStatus` query (shared `["signup-status"]` cache key) and renders the link only when `signups_enabled === true`, fail-closed otherwise. No backend changes — the client-only invariant already holds in `services/signup.py` + `services/onboarding.py`.

**Tech Stack:** React 19, TanStack Router, TanStack Query, Vitest + Testing Library, Tailwind.

**Spec:** `docs/superpowers/specs/2026-05-15-sign-in-client-signup-link-design.md`

---

### Task 1: Split sign-in into component + thin route wrapper (behavior-preserving)

Pure refactor — the app must look and behave exactly as before. No link yet.

**Files:**
- Create: `apps/web/src/components/sign-in-page.tsx`
- Modify: `apps/web/src/routes/sign-in.tsx` (becomes a 4-line wrapper)

- [ ] **Step 1: Create `apps/web/src/components/sign-in-page.tsx`**

Exact current sign-in code, moved verbatim, with two changes only: drop the
`createFileRoute` import, rename `SignInRoute` → `SignInPage` and `export` it.

```tsx
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
import { Eye, EyeOff, LockKeyhole, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

export function SignInPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const result = await signIn(email, password);
    setLoading(false);
    if (result.error) {
      setError("Email or password is incorrect.");
      return;
    }
    void navigate({ to: "/" });
  };

  return (
    <div className="dark flex min-h-screen flex-col items-center justify-between bg-background px-6 py-12">
      <div className="flex w-full max-w-[400px] flex-1 flex-col items-center justify-center">
        <motion.div
          className="mb-10 space-y-2 text-center"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <h1 className="text-4xl font-semibold tracking-tight text-foreground">Xtrusio</h1>
          <p className="text-sm text-muted-foreground">Multi-tenant AI workflows</p>
        </motion.div>

        <motion.div
          className="w-full rounded-2xl border border-foreground/10 bg-card p-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut", delay: 0.15 }}
        >
          <div className="mb-6 space-y-1.5 text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">Welcome back</h2>
            <p className="text-sm text-muted-foreground">Sign in to your dashboard</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="email"
                className="text-xs font-medium tracking-wide text-muted-foreground"
              >
                Email
              </label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="Enter your email"
                  disabled={loading}
                  className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-3 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="text-xs font-medium tracking-wide text-muted-foreground"
              >
                Password
              </label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  disabled={loading}
                  className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-10 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <Button
              type="submit"
              className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
              disabled={loading}
            >
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </motion.div>
      </div>

      <motion.p
        className="text-xs text-muted-foreground/70"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        Powered by <span className="font-medium text-muted-foreground">Xtrusio</span>
      </motion.p>
    </div>
  );
}
```

- [ ] **Step 2: Replace `apps/web/src/routes/sign-in.tsx` with the wrapper**

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { SignInPage } from "@/components/sign-in-page";

export const Route = createFileRoute("/sign-in")({ component: SignInPage });
```

- [ ] **Step 3: Typecheck + full frontend test suite (must be unchanged)**

Run: `cd apps/web && pnpm exec tsc --noEmit && pnpm --filter @xtrusio/web test`
Expected: tsc clean; `Tests 20 passed (20)` (no test added yet; behavior identical).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/sign-in-page.tsx apps/web/src/routes/sign-in.tsx
git commit -m "refactor(web/sign-in): split into component + route wrapper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add the platform-admin-gated client-signup link (TDD)

**Files:**
- Create: `apps/web/src/components/sign-in-page.test.tsx`
- Modify: `apps/web/src/components/sign-in-page.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/sign-in-page.test.tsx`. Mocks mirror
`onboarding-page.test.tsx` (router) and `sign-up-page.test.tsx` (api + query).
`useAuth` is mocked so the component renders without a real auth provider.
`Link` is mocked to a plain anchor so no RouterProvider is needed.

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignInPage } from "./sign-in-page";

vi.mock("@/lib/api", () => ({ fetchSignupStatus: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ signIn: vi.fn() }) }));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

import { fetchSignupStatus } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SignInPage />
    </QueryClientProvider>,
  );
}

describe("SignInPage", () => {
  beforeEach(() => {
    vi.mocked(fetchSignupStatus).mockReset();
  });

  it("shows the client sign-up link when signups are enabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    renderPage();
    const link = await screen.findByRole("link", { name: /client sign up/i });
    expect(link).toHaveAttribute("href", "/sign-up");
  });

  it("hides the link when signups are disabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    await waitFor(() => expect(fetchSignupStatus).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /client sign up/i })).toBeNull();
  });

  it("hides the link when the status query errors (fail-closed)", async () => {
    vi.mocked(fetchSignupStatus).mockRejectedValue(new Error("network"));
    renderPage();
    await waitFor(() => expect(fetchSignupStatus).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /client sign up/i })).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/components/sign-in-page.test.tsx`
Expected: FAIL — first test cannot find a `link` named "client sign up"
(no link rendered yet).

- [ ] **Step 3: Implement the conditional link in `sign-in-page.tsx`**

Add three things to `apps/web/src/components/sign-in-page.tsx`:

3a. Extend the router/query imports and add the api import. Replace:

```tsx
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
```

with:

```tsx
import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { fetchSignupStatus } from "@/lib/api";
```

3b. Inside `SignInPage`, immediately after `const navigate = useNavigate();`, add:

```tsx
  const { data: signupStatus } = useQuery({
    queryKey: ["signup-status"],
    queryFn: fetchSignupStatus,
  });
  const signupsEnabled = signupStatus?.signups_enabled === true;
```

3c. Inside the card `motion.div`, directly after the closing `</form>` tag and
before the closing `</motion.div>`, add the fail-closed conditional link:

```tsx
          {signupsEnabled && (
            <p className="mt-6 text-center text-sm text-muted-foreground">
              New organization?{" "}
              <Link
                to="/sign-up"
                className="font-medium text-foreground underline-offset-4 hover:underline"
              >
                Client sign up
              </Link>
            </p>
          )}
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd apps/web && pnpm exec vitest run src/components/sign-in-page.test.tsx`
Expected: PASS — all 3 tests green.

- [ ] **Step 5: Full verification (the `make check` contract)**

Run: `cd apps/web && pnpm exec tsc --noEmit && pnpm exec eslint . && pnpm --filter @xtrusio/web test`
Expected: tsc clean; eslint **0 errors** (pre-existing `react-refresh`
warnings in `ui/tabs.tsx` and `lib/auth.tsx` are the accepted baseline — no new
errors); `Tests 23 passed (23)` (20 prior + 3 new).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/sign-in-page.tsx apps/web/src/components/sign-in-page.test.tsx
git commit -m "feat(web/sign-in): platform-gated client signup link

Shows 'Client sign up' -> /sign-up only when signups_enabled is true
(fail-closed). Routes only to the existing client/org self-serve flow;
never creates a platform user.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Conditional on `signups_enabled` → Task 2 Step 3b/3c + tests 1–2. ✓
- Fail-closed on loading/false/error → `signups_enabled` strict `=== true`; Task 2 test 3. ✓
- Shared `["signup-status"]` query key → Task 2 Step 3b. ✓
- Org/client-oriented wording ("Client sign up", "New organization?") → Step 3c. ✓
- `/sign-up` keeps its own gate → untouched (no backend/sign-up changes). ✓
- Split component + wrapper, tests mirror `sign-up-page.test.tsx` → Task 1 + Task 2. ✓
- Styling matches card vocabulary, no new shadcn, no aurora → Step 3c classes only. ✓
- Backend invariant unchanged → no backend files in any task. ✓
- Out of scope items (forgot-password/SSO/social/platform self-reg) → none added. ✓

**Placeholder scan:** No TBD/TODO; all code blocks complete; exact paths and commands. ✓

**Type consistency:** `fetchSignupStatus` returns `{ signups_enabled: boolean }`
(matches `apps/web/src/lib/api.ts:42`); `SignInPage` name consistent across
Task 1 (define/export), Task 1 wrapper (import), Task 2 (import in test). Query
key `["signup-status"]` matches the existing sign-up-page usage. ✓

No issues found.
