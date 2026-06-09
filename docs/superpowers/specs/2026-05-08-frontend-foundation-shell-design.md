# Spec #4 — Frontend Foundation & Layout Shell Design

**Status:** draft, awaiting user review
**Date:** 2026-05-08
**Owner:** platform team
**Depends on:** spec #1 (multi-tenant foundation, especially section 11 frontend architecture); ENGINEERING_PRINCIPLES section 2 (TypeScript discipline)
**Blocks:** Plan 1E (user management) and every future client-facing UI plan

---

## 1. Purpose & Scope

### 1.1 Purpose

Establish the **visual foundation** for the Xtrusio platform's web app: routing, design tokens, layout shell, theme system, and a curated set of installed shadcn-ui components. This work produces a polished, professional, "real-looking" SaaS app that **renders correctly with no data** — because per project rule (saved memory `feedback_no_demo_data.md`), no mock or demo data ever appears in the codebase.

The spec deliberately stops short of features that need backend wiring (auth, real user lists, real tenant CRUD). Those are reserved for plans 1C-1E. This spec produces a foundation those plans can build on without re-thinking design tokens, layout, or component conventions.

### 1.2 In scope (v1)

1. **Tailwind v4** integrated into `apps/web/` via the v4-native CSS-first configuration (no `tailwind.config.js`).
2. **shadcn-ui** initialized via the official CLI; a curated set of components installed and committed under `apps/web/src/components/ui/`.
3. **TanStack Router** (file-based routing) installed and configured. A root layout route + 5 child routes.
4. **B/W color system** with light + dark themes via `next-themes`. Tokens defined as CSS variables in a single `globals.css`.
5. **Geist Sans + Geist Mono** typography via `@fontsource-variable/geist`.
6. **Layout shell**: shadcn `Sidebar` (inset variant) + topbar with breadcrumbs + theme toggle + user-menu placeholder + Cmd-K trigger stub.
7. **Five routes with real empty states** (no mock data on any of them):
   - `/` (Dashboard)
   - `/users` (Platform users)
   - `/clients` (Tenants)
   - `/settings`
   - `/sign-in` (visual placeholder, no auth yet)
8. **Shared `EmptyState` component** used on every empty list page.
9. **Strict styling rules** enforced: zero custom CSS outside `globals.css`, zero hardcoded colors, zero mock data.

### 1.3 Out of scope (deferred)

| Concern | Lands in |
|---|---|
| Real authentication, sign-in form wiring, session handling | Plan 1C |
| `make create-platform-owner` CLI bootstrap script | Plan 1B/1C |
| Real user list, real tenant list, invite flow forms | Plan 1E |
| TanStack Query, API client setup | Plan 1C |
| RBAC route-guards | Plan 1D |
| Cmd-K real search implementation | Plan 1E+ |
| i18n, analytics events, Storybook | Future |

### 1.4 Non-goals

- Building a UI prototype with mock data (forbidden by project memory rule).
- Custom CSS overrides on shadcn components (every styling decision goes through Tailwind utilities or token redefinition in `globals.css`).
- Adopting a brand color in v1. The design's restraint *is* the brand. (Reference aesthetic: Linear, Vercel, Supabase, Notion.)
- Locking in Cmd-K search behavior — only the affordance and modal stub.

---

## 2. Tech Stack Additions

| Library | Version | Why |
|---|---|---|
| `tailwindcss` | `^4.0.0` | CSS-first config (`@theme` directive), no JS config file. |
| `@tailwindcss/vite` | `^4.0.0` | Vite plugin replaces PostCSS pipeline. |
| `@tanstack/react-router` | `^1.130.0` | Type-safe, file-based routing. |
| `@tanstack/router-plugin` | `^1.130.0` | Vite plugin for route generation. |
| `next-themes` | `^0.4.0` | Theme switching with FOUC-free hydration. |
| `lucide-react` | `^0.469.0` | shadcn-ui's default icon set. |
| `sonner` | `^1.7.0` | Toast notifications (shadcn default). |
| `class-variance-authority` | `^0.7.0` | shadcn dependency. |
| `clsx` | `^2.1.0` | shadcn dependency. |
| `tailwind-merge` | `^2.5.0` | shadcn dependency. |
| `@fontsource-variable/geist` | `^5.1.0` | Geist Sans variable font (local files). |
| `@fontsource-variable/geist-mono` | `^5.1.0` | Geist Mono variable font (local files). |

All loaded via `pnpm` into `apps/web/`. No global font CDN calls. All TypeScript; configs in `.ts`, never `.js`/`.mjs` (per `ENGINEERING_PRINCIPLES` section 2.0).

### 2.1 shadcn-ui CLI

```bash
pnpm dlx shadcn@latest init
```

Choices:
- Style: `new-york`
- Base color: `neutral` (we override the palette in `globals.css` — neutral is closest to pure B/W)
- CSS variables: `yes`
- React Server Components: `no` (Vite app)
- Path aliases: `@/components`, `@/lib/utils`

### 2.2 shadcn components installed

```
button, input, label, textarea, card, separator, avatar, dropdown-menu,
sheet, dialog, tabs, table, skeleton, badge, tooltip, breadcrumb,
sidebar, sonner, command, scroll-area, popover
```

All sourced into `apps/web/src/components/ui/`. We own these files — no `node_modules` lock.

---

## 3. File / Module Layout

```
apps/web/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts                   # adds @tanstack/router-plugin + @tailwindcss/vite
├── vitest.config.ts
├── eslint.config.ts
├── components.json                  # shadcn-ui config (added by `shadcn init`)
└── src/
    ├── main.tsx                     # bootstraps React + RouterProvider + ThemeProvider
    ├── globals.css                  # Tailwind directive + CSS variable tokens + Geist imports
    ├── router.ts                    # TanStack Router instance
    ├── routeTree.gen.ts             # generated by @tanstack/router-plugin (gitignored? see section 3.3)
    │
    ├── routes/                      # file-based routes
    │   ├── __root.tsx               # root layout (sidebar + topbar)
    │   ├── index.tsx                # / (Dashboard)
    │   ├── users.tsx                # /users
    │   ├── clients.tsx              # /clients
    │   ├── settings.tsx             # /settings
    │   └── sign-in.tsx              # /sign-in (skeleton)
    │
    ├── components/
    │   ├── ui/                      # shadcn components, owned
    │   │   ├── button.tsx
    │   │   ├── sidebar.tsx
    │   │   └── ... (rest from section 2.2)
    │   ├── app-sidebar.tsx          # our composition of shadcn Sidebar
    │   ├── app-topbar.tsx           # breadcrumbs + theme toggle + user menu
    │   ├── theme-toggle.tsx         # dropdown: Light / Dark / System
    │   ├── theme-provider.tsx       # next-themes wrapper
    │   ├── empty-state.tsx          # shared EmptyState component
    │   └── search-trigger.tsx       # Cmd-K stub
    │
    └── lib/
        ├── utils.ts                 # cn() (shadcn util)
        └── nav.ts                   # static nav config (Dashboard, Users, Clients, Settings)
```

### 3.1 Per-file LoC targets

Per `ENGINEERING_PRINCIPLES` section 1: hard ceiling 500, target 200-300. The largest files in this spec:

- `app-sidebar.tsx` — ~180 LoC (composes Sidebar primitives, renders nav from `lib/nav.ts`)
- `globals.css` — ~150 LoC (Tailwind directives + CSS variable tokens for both themes + Geist font-face)
- `__root.tsx` — ~100 LoC (sidebar + topbar layout, ThemeProvider, Outlet)
- Each route file — ~80-150 LoC (page header + EmptyState use)

### 3.2 Path aliases

`tsconfig.json` `paths`:
```json
{
  "@/*": ["./src/*"]
}
```

Vite reads tsconfig paths automatically via `vite-tsconfig-paths` (already a transitive dep of `@vitejs/plugin-react` ecosystem). All imports use `@/components/...`, `@/lib/...`, etc. No relative `../../` paths beyond one level.

### 3.3 `routeTree.gen.ts`

Generated by `@tanstack/router-plugin` from the `routes/` filesystem. **Committed**, not gitignored — keeps PRs honest about route changes. Formatter ignores it.

---

## 4. Color System

### 4.1 Reference aesthetic

Pure B/W with a neutral gray ramp **plus four semantic status colors** (`destructive`, `warning`, `success`, `info`). Inspirations: Linear, Vercel, Supabase, Notion, Stripe-dashboard. **No brand/marketing color in v1** — the platform's restraint is the brand. Status colors are reserved for state communication (banners, badges, toasts), never decoration.

### 4.2 Token definitions in `globals.css`

```css
@import "@fontsource-variable/geist";
@import "@fontsource-variable/geist-mono";
@import "tailwindcss";

@theme {
  --font-sans: "Geist Variable", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "Geist Mono Variable", ui-monospace, "Cascadia Code", monospace;
  --radius: 0.625rem;
}

@layer base {
  :root {
    /* Light mode — pure B/W base */
    --background: 0 0% 100%;          /* #FFFFFF */
    --foreground: 0 0% 4%;            /* #0A0A0A */
    --card: 0 0% 100%;
    --card-foreground: 0 0% 4%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 4%;
    --primary: 0 0% 9%;               /* #171717 */
    --primary-foreground: 0 0% 98%;
    --secondary: 0 0% 96%;            /* #F5F5F5 */
    --secondary-foreground: 0 0% 9%;
    --muted: 0 0% 96%;
    --muted-foreground: 0 0% 45%;     /* #737373 */
    --accent: 0 0% 96%;
    --accent-foreground: 0 0% 9%;
    --destructive: 0 72% 51%;         /* #DC2626 — red 600 */
    --destructive-foreground: 0 0% 98%;
    --warning: 38 92% 50%;            /* #F59E0B — amber 500 */
    --warning-foreground: 26 83% 14%; /* dark amber for legible text */
    --success: 142 72% 29%;           /* #15803D — green 700 */
    --success-foreground: 0 0% 98%;
    --info: 217 91% 60%;              /* #3B82F6 — blue 500 */
    --info-foreground: 0 0% 98%;
    --border: 0 0% 90%;               /* #E5E5E5 */
    --input: 0 0% 90%;
    --ring: 0 0% 4%;
    --sidebar: 0 0% 98%;
    --sidebar-foreground: 0 0% 9%;
    --sidebar-border: 0 0% 90%;
    --sidebar-accent: 0 0% 96%;
    --sidebar-accent-foreground: 0 0% 9%;
    --sidebar-ring: 0 0% 4%;
  }

  .dark {
    --background: 0 0% 4%;            /* #0A0A0A */
    --foreground: 0 0% 98%;           /* #FAFAFA */
    --card: 0 0% 6%;                  /* #0F0F0F */
    --card-foreground: 0 0% 98%;
    --popover: 0 0% 6%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 9%;
    --secondary: 0 0% 10%;            /* #1A1A1A */
    --secondary-foreground: 0 0% 98%;
    --muted: 0 0% 10%;
    --muted-foreground: 0 0% 63%;     /* #A1A1A1 */
    --accent: 0 0% 12%;               /* #1F1F1F */
    --accent-foreground: 0 0% 98%;
    --destructive: 0 63% 51%;         /* #DC4040 — slightly desat red */
    --destructive-foreground: 0 0% 98%;
    --warning: 38 92% 55%;            /* #FBBF24 — amber, warmer in dark */
    --warning-foreground: 26 83% 14%;
    --success: 142 64% 42%;           /* #22A861 — softer green for dark */
    --success-foreground: 0 0% 98%;
    --info: 217 91% 65%;              /* #60A5FA — softer blue for dark */
    --info-foreground: 0 0% 98%;
    --border: 0 0% 16%;               /* #292929 */
    --input: 0 0% 16%;
    --ring: 0 0% 83%;
    --sidebar: 0 0% 6%;
    --sidebar-foreground: 0 0% 98%;
    --sidebar-border: 0 0% 16%;
    --sidebar-accent: 0 0% 10%;
    --sidebar-accent-foreground: 0 0% 98%;
    --sidebar-ring: 0 0% 83%;
  }
}
```

### 4.3 Usage discipline

- Components MUST use the semantic Tailwind utilities tied to these variables: `bg-background`, `text-foreground`, `bg-muted`, `text-muted-foreground`, `border-border`, etc.
- **No `text-zinc-*`, no `bg-gray-*`, no hex colors in JSX/TSX.** Lint rule (added in section 9) enforces.
- Adding a new semantic role means defining it in `globals.css` for **both** light and dark themes — never inline, never one mode only.

### 4.4 When to use status colors

Status colors (`destructive`, `warning`, `success`, `info`) are reserved for **state communication only**. Never decoration, never branding, never as the primary surface color.

| Color | Use when | Example components | Don't use for |
|---|---|---|---|
| **destructive** | Irreversible / dangerous action, error states | Delete buttons, error toasts, validation errors, "Account suspended" badges | "Live" indicators, generic emphasis |
| **warning** | Action needed, non-fatal issue, pending state | "Trial ending in 3 days" banner, "Unsaved changes" indicator, expired API key badge | Decorative highlights |
| **success** | Confirmed positive outcome, completed state | "Saved" toast, completed run status badges, payment success | "On" or "Active" by default — those are foreground (B/W), not green |
| **info** | Informational, advisory, neutral state notice | "New feature available" banner, system message, link previews | Default action buttons (those are `primary`, which is foreground in our system) |

**Test for "is this status color appropriate":** would removing the color break the user's understanding of state? If yes → status color. If "it just looks nicer" → no, use `bg-muted` or stay B/W.

### 4.5 Component → token quick reference

| Component | Token usage |
|---|---|
| Page background | `bg-background text-foreground` |
| Card / panel | `bg-card text-card-foreground border-border` |
| Sidebar | `bg-sidebar text-sidebar-foreground border-sidebar-border` |
| Muted helper text | `text-muted-foreground` |
| Disabled control | `bg-muted text-muted-foreground` |
| Primary button | `bg-primary text-primary-foreground` |
| Secondary button | `bg-secondary text-secondary-foreground` |
| Destructive button | `bg-destructive text-destructive-foreground` |
| Success badge | `bg-success/10 text-success border border-success/20` (subtle) |
| Warning banner | `bg-warning/10 text-warning-foreground border-l-4 border-warning` |
| Info toast | `bg-info text-info-foreground` |
| Focus ring | `ring-2 ring-ring ring-offset-2 ring-offset-background` |

The opacity modifiers (`/10`, `/20`) keep status colors from overpowering the B/W base — they tint, not flood.

---

## 5. Typography

### 5.1 Fonts

- **Geist Sans** — UI body & headings
- **Geist Mono** — code, IDs, numbers in tables (with `tabular-nums` utility)

Loaded via `@fontsource-variable/geist` + `@fontsource-variable/geist-mono` packages — local font files, no Google Fonts CDN call. Variable axes (weight) supported.

### 5.2 Type scale

| Use | Class | Size |
|---|---|---|
| Headings (page title) | `text-2xl font-semibold tracking-tight` | 24px |
| Section heading | `text-xl font-semibold tracking-tight` | 20px |
| Body | `text-sm` | 14px (shadcn default) |
| Helper / caption | `text-xs text-muted-foreground` | 12px |
| Numbers/IDs | `font-mono tabular-nums text-xs` | 12px mono |

### 5.3 Discipline

- `tracking-tight` on every heading (matches reference SaaS aesthetics).
- `tabular-nums` on every data table (column widths stay stable).
- Font weights: 400 (body), 500 (UI emphasis), 600 (headings). No 700+ outside hero/marketing surfaces (we have none yet).

---

## 6. Layout Shell

### 6.1 Visual structure

```
┌─────────────────────────────────────────────────────────────┐
│ Breadcrumbs              [Cmd-K]   [theme]    [user-menu]   │  ← topbar (h-14)
├──────────────────────────────────────────────────────────────┤
│ Xtrusio (logo)│                                              │
│ ──────────────│                                              │
│ □ Dashboard   │                                              │
│ □ Users       │             <route content here>             │
│ □ Clients     │                                              │
│ □ Settings    │                                              │
│ ──────────────│                                              │
│  collapsible  │                                              │
│  rail toggle  │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

### 6.2 Sidebar (`components/app-sidebar.tsx`)

- Built on shadcn's `Sidebar` component, **inset variant**.
- Header: app branding (logo + "Xtrusio" wordmark in Geist Sans).
- Body: navigation list from `lib/nav.ts`. Each nav item has `to`, `label`, `icon`. Active state from `useRouter`.
- Footer: theme toggle + user menu (placeholder for Plan 1C).
- Collapsible to icon-only via shadcn rail.

### 6.3 Topbar (`components/app-topbar.tsx`)

- Sticky top, `h-14`, `border-b border-border`.
- Left: breadcrumbs (built from current route segments).
- Center-right: command-K trigger (`SearchTrigger`) — visual button with `⌘K` shortcut affordance.
- Right: theme toggle (mobile shows here too); user menu (mobile shows here too).

### 6.4 `__root.tsx` (root route layout)

```tsx
// apps/web/src/routes/__root.tsx (≈100 LoC)
import { Outlet, createRootRoute } from "@tanstack/react-router";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <AppTopbar />
          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </SidebarInset>
        <Toaster richColors closeButton position="bottom-right" />
      </SidebarProvider>
    </ThemeProvider>
  );
}
```

### 6.5 Cmd-K stub

`SearchTrigger` opens shadcn's `Command` dialog with a single placeholder line: "Search coming with user management (Plan 1E)". Keystroke binding (`mod+k`) wires up now so muscle memory lands; full functionality later.

---

## 7. Routes & Empty States

### 7.1 Route inventory

All routes use the root layout (sidebar + topbar). Each is a standalone file in `apps/web/src/routes/`.

| Path | File | Page title | Empty-state copy |
|---|---|---|---|
| `/` | `index.tsx` | Dashboard | "Welcome to Xtrusio. The platform owner is created via `make create-platform-owner`. Once signed in, this page shows platform-wide activity." |
| `/users` | `users.tsx` | Platform users | "No platform users yet. The first owner is bootstrapped via CLI; subsequent users are invited from this page once auth lands (Plan 1C)." |
| `/clients` | `clients.tsx` | Tenants | "No client tenants yet. The first one is created here after the tenancy and auth plans land (1B/1C)." |
| `/settings` | `settings.tsx` | Settings | Tabs: **Theme** (working — switch light/dark/system), **Appearance** (placeholder). Profile / Security tabs deferred to Plan 1C. |
| `/sign-in` | `sign-in.tsx` | Sign in | Centered card with email + password fields (visual only — no submit handler yet). Wired up in Plan 1C. |

### 7.2 Page header convention

Every route's content begins with:

```tsx
<header className="mb-6 flex items-center justify-between">
  <div>
    <h1 className="text-2xl font-semibold tracking-tight">Page Title</h1>
    <p className="text-sm text-muted-foreground">One-line description.</p>
  </div>
  <div>{/* primary action button (disabled in v1) */}</div>
</header>
```

### 7.3 Empty-state convention

```tsx
<EmptyState
  icon={Users}
  title="No platform users yet"
  description="The first owner is bootstrapped via `make create-platform-owner`. Subsequent users are invited from here when Plan 1C ships."
  action={{
    label: "Invite a user",
    onClick: () => {},
    disabled: true,
    reason: "Available in Plan 1E (user management)",
  }}
/>
```

---

## 8. Shared Components

### 8.1 `EmptyState` (`components/empty-state.tsx`)

```tsx
import { type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type Action = {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  reason?: string;
};

type EmptyStateProps = {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: Action;
};

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-center">
      {Icon && (
        <div className="rounded-full bg-muted p-3">
          <Icon className="h-6 w-6 text-muted-foreground" />
        </div>
      )}
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      {action && (
        action.disabled && action.reason ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="mt-2 inline-block">
                <Button disabled>{action.label}</Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{action.reason}</TooltipContent>
          </Tooltip>
        ) : (
          <Button onClick={action.onClick} disabled={action.disabled} className="mt-2">
            {action.label}
          </Button>
        )
      )}
    </div>
  );
}
```

Stateless, prop-driven, theme-agnostic — meets `ENGINEERING_PRINCIPLES` section 4 component rules.

### 8.2 `ThemeToggle` (`components/theme-toggle.tsx`)

shadcn `DropdownMenu` with three options (Light / Dark / System). Uses `useTheme` from `next-themes`. Icon swaps based on resolved theme.

### 8.3 `ThemeProvider` (`components/theme-provider.tsx`)

Thin wrapper around `next-themes`'s `ThemeProvider`. Forwards children + props.

---

## 9. Strict Rules (enforced by code review + tooling)

These are *project rules* on top of `ENGINEERING_PRINCIPLES` and apply to this and every future frontend plan.

### 9.1 No custom CSS outside `globals.css`

- `globals.css` is the only `.css` file in `apps/web/`.
- No CSS modules, no styled-components, no `:root` blocks anywhere else.
- ESLint rule (added in this plan): forbid `className` strings containing arbitrary `[#hex]` color values.
- Every visual decision goes through Tailwind utilities + shadcn primitives + CSS variable tokens.

### 9.2 No hardcoded colors

Forbidden in any `.tsx`/`.ts`/`.css` file (outside `globals.css`):
- Hex (`#000`, `#FFFFFF`, ...)
- Tailwind palette utilities (`bg-zinc-*`, `text-gray-*`, `bg-slate-*`, ...)
- HSL/RGB literals

Allowed:
- Semantic tokens — base (`bg-background`, `text-foreground`, `border-border`, `bg-muted`, `text-muted-foreground`, `bg-card`, `bg-popover`, `bg-primary`, `bg-secondary`, `bg-accent`, `bg-sidebar*`, `ring`)
- Status tokens (`bg-destructive`, `text-destructive`, `bg-warning`, `text-warning-foreground`, `bg-success`, `text-success`, `bg-info`, `text-info-foreground`, plus their `-foreground` pairs)
- Tailwind opacity modifiers on any token (`bg-foreground/5`, `border-border/50`, `bg-success/10`, `bg-warning/10`)

A grep gate (added to `scripts/check-colors.sh`, wired into pre-commit) catches violations.

### 9.3 No mock/demo data

Per saved memory rule (`feedback_no_demo_data.md`):
- No `users = [{ name: "John Doe", ... }]` anywhere — even commented out.
- No `// TODO: replace with real data` — write the empty state instead.
- Lint rule: forbid identifier patterns matching `mock*`, `fake*`, `demo*`, `seed*`, `example*` in `apps/web/`. Exceptions for legitimate cases (e.g., `mockServiceWorker` if we add it later) get an inline `// eslint-disable-next-line` with a reason.

### 9.4 TypeScript-only

Already in `ENGINEERING_PRINCIPLES` section 2.0; this spec doesn't introduce any `.js`/`.jsx`/`.mjs`/`.cjs`. Existing pre-commit hook (`scripts/check-no-js-in-frontend.sh`) catches violations.

### 9.5 Per-file LoC

Hard ceiling 500 LoC per `ENGINEERING_PRINCIPLES` section 1. Spec aims at 200-300 for every file we create.

---

## 10. Theme Switching Flow

1. User picks Light / Dark / System from `ThemeToggle`.
2. `next-themes` writes the class (`dark` or no class) to `<html>` and persists in `localStorage`.
3. CSS variables in `globals.css` re-resolve based on the `.dark` class scope.
4. No FOUC: `next-themes` injects an inline script before hydration that reads `localStorage` and sets the class synchronously.

System mode follows `prefers-color-scheme`, re-evaluating on OS theme change without a page reload.

---

## 11. Testing Strategy

### 11.1 Unit / component tests (Vitest + React Testing Library)

| Subject | What gets tested |
|---|---|
| `EmptyState` | Renders title + description; renders icon when provided; renders action button + click handler; disabled state shows tooltip with reason. |
| `ThemeToggle` | Cycles through Light / Dark / System; calls `setTheme` correctly. |
| `AppSidebar` | Renders nav items from `lib/nav.ts`; active route highlights correctly. |
| `AppTopbar` | Renders breadcrumbs from current pathname; theme toggle present. |
| Each route | Renders page header + empty state; no crashes; no `data-testid` containing "mock" or "fake". |

Coverage target: ≥ 80% on new code per `ENGINEERING_PRINCIPLES` section 9.

### 11.2 Visual regression (out of scope, but planned)

Storybook + Chromatic deferred. v1 verifies visually by hand via `make dev`.

### 11.3 Theme tests

Both light and dark themes are exercised: at least one test per route renders under each theme and asserts the rendered tree contains expected `bg-background` / `text-foreground` classes (not literal colors).

### 11.4 Accessibility smoke

- Every interactive element has an accessible name (label, aria-label, or text content).
- `EmptyState` action with `disabled + reason` exposes the reason via `aria-describedby` linked to a tooltip.
- Sidebar navigation uses semantic `<nav>` with proper `aria-current="page"`.
- Theme toggle button has `aria-label="Toggle theme"`.

These checks are part of the component tests above (RTL queries by role, not by test ID).

---

## 12. Local Verification Commands

After implementation, the following must pass locally:

```bash
make install                    # pnpm + uv sync
make db-up                      # Supabase + Valkey (for any future API calls during dev)
make dev                        # API + web, watch mode

# In a second shell:
curl -s http://localhost:5173 | grep -q '<div id="root">'    # web shell renders
pnpm --filter @xtrusio/web typecheck                          # tsc passes
pnpm --filter @xtrusio/web lint                               # ESLint + new rules pass
pnpm --filter @xtrusio/web test                               # Vitest passes
pnpm exec prettier --check apps/web                           # formatting clean
./scripts/check-colors.sh                                     # no hardcoded colors
./scripts/check-no-js-in-frontend.sh                          # no .js leakage
uv run pre-commit run --all-files                             # all hooks green
```

CI gates are deferred per project policy (`feedback_ci_cd_after_local.md`); the local commands are the contract until CI lands.

---

## 13. Open Questions

1. **Sidebar logo asset**: ship a placeholder SVG ("X" mark) until brand assets exist, or just text "Xtrusio" in Geist? Default: text + a future SVG slot.
2. **TanStack Router code-splitting**: enable per-route lazy loading in v1 or defer? Default: enable (Vite + TanStack handles it, near-zero cost). Marked done in success criteria.
3. **Settings page tabs**: should "Notifications" tab placeholder exist now, or wait for the notifications spec? Default: don't add — open settings tabs only when there's content. Just Theme + Appearance.
4. **`tailwindcss-animate`**: shadcn-ui historically required this plugin. Tailwind v4 has built-in animations; check if `tailwindcss-animate` is still needed when running shadcn `init` against v4. If yes, install; if no, omit. (Implementation-time check.)

---

## 14. Success Criteria

The foundation is "v1 done" when:

1. `apps/web/` starts via `make dev` and renders the root layout (sidebar + topbar) on every route.
2. All five routes (`/`, `/users`, `/clients`, `/settings`, `/sign-in`) render their page header + empty state with no console errors.
3. Theme toggle cycles Light / Dark / System with no FOUC; CSS variables resolve correctly in both themes.
4. shadcn components in `apps/web/src/components/ui/` exist and import cleanly into routes/components.
5. Cmd-K opens the search dialog; the placeholder text is visible.
6. Every route file is ≤ 250 LoC; `app-sidebar.tsx` ≤ 200 LoC.
7. Zero hardcoded colors detected by `scripts/check-colors.sh`.
8. Zero `.js`/`.jsx`/`.mjs`/`.cjs` files added (existing pre-commit hook).
9. Component test coverage ≥ 80% on new code; tests pass under both light and dark themes.
10. `pnpm --filter @xtrusio/web build` produces a clean `dist/` (Cloudflare-Pages-deploy-ready, even though we don't deploy yet).
11. Lint catches: arbitrary hex colors, `bg-zinc-*` / `bg-gray-*` / etc. usage, identifiers matching `mock*`/`fake*`/`demo*`/`seed*`/`example*`.
12. README's "Daily development" section shows the two new routes and the empty-state design as the verified default.

---

## 15. Cross-References

- `docs/superpowers/specs/2026-05-07-multi-tenant-foundation-design.md` (spec #1) — section 11 frontend architecture, section 3 identity model that informs sidebar/user-menu.
- `docs/superpowers/ENGINEERING_PRINCIPLES.md` — section 1 file size, section 2 TypeScript discipline, section 2.0 frontend extension rule, section 4 reusable components, section 9 PR review checklist.
- `MEMORY.md` (project memories) — `feedback_no_demo_data.md`, `feedback_frontend_typescript_only.md`, `project_dev_runtime_choice.md`, `project_production_architecture.md`.
- `Algo.md` — unrelated; mentioned for completeness.
