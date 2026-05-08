# Plan 1A — Monorepo + Local Dev Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the empty monorepo skeleton so every later plan inherits a working dev environment — pnpm + uv workspaces, Turborepo, Docker Compose for Postgres+pgvector+Valkey, lint/format/type-check tooling, an empty FastAPI app that responds to `/health`, an empty Vite+React app that boots, and a `make dev` command that brings the whole stack up locally.

**Architecture:** Polyglot monorepo. **pnpm workspaces** drive `apps/web`, `packages/ui`, `packages/api-types`. **uv workspace** drives `apps/api` (Python). **Turborepo** orchestrates cross-package tasks (`build`, `lint`, `test`, `dev`). Local services run in Docker Compose. There is no CI/CD setup in this plan — local-equivalent commands only, per project policy.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, pytest, Ruff, mypy. Node 22, pnpm 10, TypeScript 5.5+ (strict), React 19, Vite 8, Vitest, ESLint 9, Prettier. Turborepo 2. Postgres 16 + pgvector, Valkey 8. Tool versions pinned via `mise`. Local quality gate enforced via `pre-commit`.

**Container conventions:**
- All containers are **named with `xtrusio-` prefix** (e.g., `xtrusio-postgres`, `xtrusio-valkey`).
- All containers run on a **custom Docker network** (`xtrusio-net`) so they resolve each other by name without exposing internal ports.
- **Non-default host ports** are used to avoid colliding with other Postgres/Redis instances on the developer machine: Postgres on host port `54322`, Valkey on host port `63792`.

---

## Files Created in This Plan

### Repo root
- `package.json` — pnpm workspace root
- `pnpm-workspace.yaml`
- `turbo.json` — Turbo pipeline definition
- `pyproject.toml` — uv workspace root (members + shared Python tool configs: ruff, mypy, pytest)
- `docker-compose.yml` — Postgres + pgvector + Valkey on `xtrusio-net`
- `Makefile` — primary developer entrypoint
- `.env.example` — documented environment variables
- `.gitignore`
- `.editorconfig`
- `README.md` — quickstart
- `.python-version` — `3.12`
- `.nvmrc` — `22`
- `mise.toml` — pins Node/Python/pnpm versions for everyone
- `.pre-commit-config.yaml` — local quality gate on `git commit`

### `apps/api/` (FastAPI)
- `apps/api/pyproject.toml`
- `apps/api/src/xtrusio_api/__init__.py`
- `apps/api/src/xtrusio_api/main.py` — FastAPI app with `/health`
- `apps/api/tests/__init__.py`
- `apps/api/tests/test_health.py` — smoke test

### `apps/web/` (Vite + React)
- `apps/web/package.json`
- `apps/web/tsconfig.json`
- `apps/web/vite.config.ts`
- `apps/web/index.html`
- `apps/web/src/main.tsx`
- `apps/web/src/App.tsx`
- `apps/web/src/App.test.tsx` — smoke test
- `apps/web/eslint.config.js`
- `apps/web/.prettierrc.json`
- `apps/web/vitest.config.ts`

### `packages/ui/` (placeholder; real components added in later plans)
- `packages/ui/package.json`
- `packages/ui/tsconfig.json`
- `packages/ui/src/index.ts` — empty barrel

### `packages/api-types/` (placeholder)
- `packages/api-types/package.json`
- `packages/api-types/tsconfig.json`
- `packages/api-types/src/index.ts` — empty barrel

### `infra/postgres/`
- `infra/postgres/init.sql` — `CREATE EXTENSION vector;`

---

## Prerequisites Check

Before starting, the engineer's machine has:
- Docker Desktop (or compatible) running
- Node 22 (`fnm` / `nvm` / `volta` to manage)
- pnpm 10 (`corepack enable && corepack prepare pnpm@10`)
- Python 3.12 (`uv` will manage; install `uv` itself via `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- GNU Make
- Git

These are documented in the README task at the end.

---

## Task 1: Initialize repo metadata files

**Files:**
- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `.python-version`
- Create: `.nvmrc`

- [ ] **Step 1: Create `.gitignore`**

```
# Node
node_modules/
.pnpm-store/
dist/
.turbo/

# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
.uv-cache/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
*.egg-info/

# Editors
.idea/
.vscode/
*.swp
.DS_Store

# Local env
.env
.env.local
.env.*.local

# Build outputs
build/
*.tsbuildinfo
```

- [ ] **Step 2: Create `.editorconfig`**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[Makefile]
indent_style = tab
```

- [ ] **Step 3: Create `.python-version`**

```
3.12
```

- [ ] **Step 4: Create `.nvmrc`**

```
22
```

- [ ] **Step 5: Verify and commit**

```bash
ls -a
# Expected: .gitignore .editorconfig .python-version .nvmrc visible
git add .gitignore .editorconfig .python-version .nvmrc
git commit -m "chore: add repo metadata files"
```

---

## Task 1A: Pin tool versions with `mise`

**Files:**
- Create: `mise.toml`

**Why:** `mise` (formerly rtx) reads a single config file to install/select Node, Python, and pnpm. Engineers run `mise install` once and every shell uses the right versions automatically — replaces the per-tool dance of nvm + pyenv + corepack. Optional but strongly recommended; `.python-version` and `.nvmrc` from Task 1 still work for engineers who don't use `mise`.

- [ ] **Step 1: Create `mise.toml`**

```toml
[tools]
node = "22"
python = "3.12"
pnpm = "10"

[env]
# Default process role for shells that don't override (most engineers run `make api` / `make worker` which set this explicitly).
XTRUSIO_PROCESS_ROLE = "api"
```

- [ ] **Step 2: (Optional) Verify `mise` installs the tools**

If you have `mise` installed (`brew install mise` on macOS, or see https://mise.jdx.dev):

```bash
mise install
mise current
```

Expected: prints `node 22.x.y`, `python 3.12.x`, `pnpm 10.x.y`. If `mise` is not installed, this step is skippable — `.python-version` and `.nvmrc` still drive nvm/pyenv users.

- [ ] **Step 3: Commit**

```bash
git add mise.toml
git commit -m "chore: pin tool versions via mise.toml"
```

---

## Task 2: Set up pnpm workspace root

**Files:**
- Create: `package.json`
- Create: `pnpm-workspace.yaml`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "xtrusio",
  "version": "0.0.0",
  "private": true,
  "packageManager": "pnpm@10.0.0",
  "engines": {
    "node": ">=22",
    "pnpm": ">=10"
  },
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "test": "turbo run test",
    "typecheck": "turbo run typecheck"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.5.0",
    "prettier": "^3.3.0"
  }
}
```

- [ ] **Step 2: Create `pnpm-workspace.yaml`**

```yaml
packages:
  - "apps/web"
  - "packages/*"
```

> Note: `apps/api` is intentionally NOT a pnpm workspace member — Python is managed by uv (Task 5).

- [ ] **Step 3: Verify pnpm installs**

```bash
pnpm install
# Expected: creates node_modules/ and pnpm-lock.yaml without errors.
# It will warn that workspace members don't exist yet — acceptable for now.
```

- [ ] **Step 4: Commit**

```bash
git add package.json pnpm-workspace.yaml pnpm-lock.yaml
git commit -m "chore: set up pnpm workspace root"
```

---

## Task 3: Set up Turborepo pipeline

**Files:**
- Create: `turbo.json`

- [ ] **Step 1: Create `turbo.json`**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", "build/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "lint": {
      "dependsOn": ["^build"]
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"]
    }
  }
}
```

- [ ] **Step 2: Verify Turbo recognizes the config**

```bash
pnpm exec turbo run lint --dry=json
# Expected: prints a JSON dry-run plan (empty tasks list because no packages exist yet).
# No "invalid configuration" errors.
```

- [ ] **Step 3: Commit**

```bash
git add turbo.json
git commit -m "chore: add Turborepo pipeline"
```

---

## Task 4: Add root tooling configs (Prettier)

**Files:**
- Create: `.prettierrc.json`
- Create: `.prettierignore`

- [ ] **Step 1: Create `.prettierrc.json`**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

- [ ] **Step 2: Create `.prettierignore`**

```
node_modules
dist
build
.turbo
.venv
**/__pycache__
**/*.py
pnpm-lock.yaml
uv.lock
```

- [ ] **Step 3: Verify Prettier runs**

```bash
pnpm exec prettier --check .
# Expected: "All matched files use Prettier code style!" or no files matched.
```

- [ ] **Step 4: Commit**

```bash
git add .prettierrc.json .prettierignore
git commit -m "chore: configure root Prettier"
```

---

## Task 5: Set up uv workspace + root pyproject.toml

**Files:**
- Create: `pyproject.toml` (root: workspace declaration + shared Python tool config)

> **Note:** uv 0.11+ requires the workspace declaration in `pyproject.toml` (not in `uv.toml`). Earlier guidance in this plan that mentioned `uv.toml` for workspace setup is outdated — do not create one.

- [ ] **Step 1: Create root `pyproject.toml`**

```toml
[tool.uv]
required-version = ">=0.11.0"

[tool.uv.workspace]
members = ["apps/api"]

# requires-python at workspace root silences uv's default warning.
# Each member's own pyproject.toml may pin a tighter range.
[project]
name = "xtrusio-workspace"
version = "0.0.0"
requires-python = ">=3.12,<3.13"

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["node_modules", "dist", "build", ".venv"]

[tool.ruff.lint]
select = [
    "E", "F", "W",        # pycodestyle, pyflakes
    "I",                  # isort
    "UP",                 # pyupgrade
    "B",                  # bugbear
    "SIM",                # simplify
    "ASYNC",              # async correctness
    "N",                  # naming
    "RUF",                # ruff-specific
]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
exclude = ["node_modules", "dist", "build", ".venv"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["apps/api/tests"]
addopts = "-ra -q --strict-markers"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "ml: marks tests requiring ML models (deselect with '-m \"not ml\"')",
    "perf: marks performance benchmarks (deselect with '-m \"not perf\"')",
]
```

- [ ] **Step 2: Verify uv recognizes the workspace**

```bash
uv sync
```

Expected: creates `.venv/` and finishes with `Resolved N packages` / `Checked in ...`. No errors. The workspace member `apps/api` doesn't exist yet — uv tolerates this until Task 6.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: set up uv workspace + Python tool configs"
```

---

## Task 6: Scaffold `apps/api` (FastAPI) with failing health test

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/xtrusio_api/__init__.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/tests/test_health.py`

- [ ] **Step 1: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "xtrusio-api"
version = "0.0.0"
description = "Xtrusio platform API"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi~=0.115.0",
    "uvicorn[standard]~=0.30.0",
    "pydantic~=2.9.0",
    "pydantic-settings~=2.5.0",
]

[dependency-groups]
dev = [
    "pytest~=8.3.0",
    "pytest-asyncio~=0.24.0",
    "httpx~=0.27.0",
    "ruff~=0.6.0",
    "mypy~=1.11.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/xtrusio_api"]
```

- [ ] **Step 2: Create the package layout**

```bash
mkdir -p apps/api/src/xtrusio_api apps/api/tests
touch apps/api/src/xtrusio_api/__init__.py
touch apps/api/tests/__init__.py
```

- [ ] **Step 3: Write the failing test FIRST**

Create `apps/api/tests/test_health.py`:

```python
"""Smoke test for the /health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from xtrusio_api.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

```bash
uv sync
uv run pytest apps/api/tests/test_health.py -v
```

Expected: **FAIL** with `ModuleNotFoundError: No module named 'xtrusio_api.main'`. The test is correctly failing for the right reason.

- [ ] **Step 5: Commit the failing test**

```bash
git add apps/api/pyproject.toml apps/api/src/xtrusio_api/__init__.py apps/api/tests/__init__.py apps/api/tests/test_health.py
git commit -m "test(api): add failing health endpoint test"
```

---

## Task 7: Implement `/health` to make the test pass

**Files:**
- Create: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Create `apps/api/src/xtrusio_api/main.py`**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Xtrusio API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it passes**

```bash
uv run pytest apps/api/tests/test_health.py -v
```

Expected: **PASS** — `test_health_returns_ok PASSED`.

- [ ] **Step 3: Run lint and type check on api source**

```bash
uv run ruff check apps/api/src apps/api/tests
uv run ruff format --check apps/api/src apps/api/tests
uv run mypy apps/api/src apps/api/tests
```

Expected: all three commands exit 0 with no errors.

- [ ] **Step 4: Manually verify the dev server boots**

```bash
uv run uvicorn xtrusio_api.main:app --reload --port 8000 &
SERVER_PID=$!
sleep 3
curl -s http://localhost:8000/health
# Expected output: {"status":"ok"}
kill $SERVER_PID
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/main.py
git commit -m "feat(api): add /health endpoint"
```

---

## Task 8: Scaffold `apps/web` (Vite + React) with failing smoke test

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/eslint.config.js`
- Create: `apps/web/index.html`
- Create: `apps/web/src/App.test.tsx` (failing test, written first)

- [ ] **Step 1: Create `apps/web/package.json`**

```json
{
  "name": "@xtrusio/web",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --port 5173",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "typecheck": "tsc -b --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^8.0.0",
    "vitest": "^2.1.0",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.0",
    "jsdom": "^25.0.0",
    "eslint": "^9.10.0",
    "@eslint/js": "^9.10.0",
    "typescript-eslint": "^8.5.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.0",
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: Create `apps/web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "isolatedModules": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "useDefineForClassFields": true,
    "verbatimModuleSyntax": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"],
    "outDir": "dist"
  },
  "include": ["src", "vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 3: Create `apps/web/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
```

- [ ] **Step 4: Create `apps/web/vitest.config.ts`**

```ts
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
    },
  }),
);
```

- [ ] **Step 5: Create `apps/web/eslint.config.js`**

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
);
```

- [ ] **Step 6: Create `apps/web/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Xtrusio</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create the failing test FIRST — `apps/web/src/App.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the Xtrusio heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /xtrusio/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 8: Create the test setup file**

`apps/web/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 9: Install dependencies**

```bash
pnpm install
```

Expected: pnpm resolves React 19, Vite 8, etc. Lockfile updated.

- [ ] **Step 10: Run test to verify it fails**

```bash
pnpm --filter @xtrusio/web test
```

Expected: **FAIL** — `Cannot find module './App'` or similar. Test is correctly failing.

- [ ] **Step 11: Commit failing test scaffold**

```bash
git add apps/web/package.json apps/web/tsconfig.json apps/web/vite.config.ts apps/web/vitest.config.ts apps/web/eslint.config.js apps/web/index.html apps/web/src/App.test.tsx apps/web/src/test-setup.ts pnpm-lock.yaml
git commit -m "test(web): scaffold Vite + Vitest with failing App test"
```

---

## Task 9: Implement minimal `App` to make the web smoke test pass

**Files:**
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/main.tsx`

- [ ] **Step 1: Create `apps/web/src/App.tsx`**

```tsx
export function App() {
  return (
    <main>
      <h1>Xtrusio</h1>
    </main>
  );
}
```

- [ ] **Step 2: Create `apps/web/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root element not found in index.html");
}
createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 3: Run test to verify it passes**

```bash
pnpm --filter @xtrusio/web test
```

Expected: **PASS** — 1 test passing.

- [ ] **Step 4: Run lint and typecheck**

```bash
pnpm --filter @xtrusio/web lint
pnpm --filter @xtrusio/web typecheck
```

Expected: both exit 0.

- [ ] **Step 5: Manually verify the dev server boots**

```bash
pnpm --filter @xtrusio/web dev &
SERVER_PID=$!
sleep 3
curl -s http://localhost:5173 | grep -q '<div id="root">' && echo "OK" || echo "FAIL"
kill $SERVER_PID
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/main.tsx
git commit -m "feat(web): add minimal App component"
```

---

## Task 10: Scaffold `packages/ui` placeholder

**Files:**
- Create: `packages/ui/package.json`
- Create: `packages/ui/tsconfig.json`
- Create: `packages/ui/src/index.ts`

- [ ] **Step 1: Create `packages/ui/package.json`**

```json
{
  "name": "@xtrusio/ui",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "lint": "echo 'no source yet'",
    "typecheck": "tsc -b --noEmit",
    "test": "echo 'no tests yet'"
  },
  "devDependencies": {
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: Create `packages/ui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "outDir": "dist"
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create `packages/ui/src/index.ts`**

```ts
// Placeholder. Real components ship in later plans.
export {};
```

- [ ] **Step 4: Verify**

```bash
pnpm install
pnpm --filter @xtrusio/ui typecheck
```

Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add packages/ui pnpm-lock.yaml
git commit -m "chore: scaffold @xtrusio/ui placeholder"
```

---

## Task 11: Scaffold `packages/api-types` placeholder

**Files:**
- Create: `packages/api-types/package.json`
- Create: `packages/api-types/tsconfig.json`
- Create: `packages/api-types/src/index.ts`

- [ ] **Step 1: Create `packages/api-types/package.json`**

```json
{
  "name": "@xtrusio/api-types",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "lint": "echo 'no source yet'",
    "typecheck": "tsc -b --noEmit",
    "test": "echo 'no tests yet'"
  },
  "devDependencies": {
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: Create `packages/api-types/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "outDir": "dist"
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create `packages/api-types/src/index.ts`**

```ts
// Placeholder. Real types are generated from OpenAPI in later plans.
export {};
```

- [ ] **Step 4: Verify**

```bash
pnpm install
pnpm --filter @xtrusio/api-types typecheck
```

Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add packages/api-types pnpm-lock.yaml
git commit -m "chore: scaffold @xtrusio/api-types placeholder"
```

---

## Task 12: Add Postgres + Valkey via Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `infra/postgres/init.sql`

- [ ] **Step 1: Create `infra/postgres/init.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
name: xtrusio

networks:
  xtrusio-net:
    name: xtrusio-net
    driver: bridge

services:
  postgres:
    container_name: xtrusio-postgres
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    networks:
      - xtrusio-net
    ports:
      # Host:Container — non-default host port to avoid colliding with other Postgres
      - "54322:5432"
    environment:
      POSTGRES_USER: xtrusio
      POSTGRES_PASSWORD: xtrusio_dev
      POSTGRES_DB: xtrusio
    volumes:
      - xtrusio-postgres-data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U xtrusio -d xtrusio"]
      interval: 5s
      timeout: 3s
      retries: 10

  valkey:
    container_name: xtrusio-valkey
    image: valkey/valkey:8
    restart: unless-stopped
    networks:
      - xtrusio-net
    ports:
      # Host:Container — non-default host port to avoid colliding with other Redis/Valkey
      - "63792:6379"
    command: ["valkey-server", "--save", "60", "1", "--appendonly", "yes"]
    volumes:
      - xtrusio-valkey-data:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  xtrusio-postgres-data:
    name: xtrusio-postgres-data
  xtrusio-valkey-data:
    name: xtrusio-valkey-data
```

> **Why these choices:**
> - `name: xtrusio` at the top tells `docker compose` to use `xtrusio` as the project name regardless of the working directory.
> - `container_name` pins the Docker container name (otherwise Compose generates one like `xtrusio-postgres-1`).
> - `networks.xtrusio-net.name: xtrusio-net` pins the Docker network name (otherwise Compose prefixes with project name → `xtrusio_xtrusio-net`).
> - Host ports `54322` and `63792` are deliberately uncommon — apps on host connect via `localhost:54322` / `localhost:63792`. If two `xtrusio` containers ever need to talk to each other, they use `postgres:5432` / `valkey:6379` over `xtrusio-net` (in-network, no host port).
> - Named volumes (`xtrusio-postgres-data`, `xtrusio-valkey-data`) — stable across `docker compose down` so dev data survives restarts.

- [ ] **Step 3: Bring services up**

```bash
docker compose up -d
docker compose ps
```

Expected: containers `xtrusio-postgres` and `xtrusio-valkey` show `running` and `healthy` after ~10 seconds.

- [ ] **Step 4: Verify the network and named containers**

```bash
docker network inspect xtrusio-net --format '{{range $k,$v := .Containers}}{{$v.Name}}{{"\n"}}{{end}}'
```

Expected output:
```
xtrusio-postgres
xtrusio-valkey
```

- [ ] **Step 5: Verify Postgres + pgvector**

```bash
docker exec xtrusio-postgres psql -U xtrusio -d xtrusio -c "\dx"
```

Expected output includes: `vector | ... | extensions for pgvector`, `pgcrypto`, `citext`.

Verify host port mapping:

```bash
docker port xtrusio-postgres 5432
```

Expected: `0.0.0.0:54322` (or similar — key is the `54322`).

- [ ] **Step 6: Verify Valkey**

```bash
docker exec xtrusio-valkey valkey-cli ping
```

Expected: `PONG`.

```bash
docker port xtrusio-valkey 6379
```

Expected: `0.0.0.0:63792`.

- [ ] **Step 7: Tear down (the Makefile handles this in Task 14)**

```bash
docker compose down
```

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml infra/postgres/init.sql
git commit -m "feat(infra): add named Postgres + Valkey containers on xtrusio-net (host ports 54322/63792)"
```

---

## Task 13: Create `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

```ini
# === Process role (required) ===
# Set to "api" for the FastAPI/Uvicorn process, "worker" for Dramatiq/Prefect.
# Local dev: `make api` and `make worker` set this automatically.
XTRUSIO_PROCESS_ROLE=api

# === Database ===
# Host port 54322 maps to xtrusio-postgres:5432 inside the xtrusio-net network.
DATABASE_URL=postgresql+asyncpg://xtrusio:xtrusio_dev@localhost:54322/xtrusio

# === Valkey ===
# Host port 63792 maps to xtrusio-valkey:6379 inside the xtrusio-net network.
VALKEY_URL=redis://localhost:63792/0

# === Frontend ===
VITE_API_BASE_URL=http://localhost:8000

# === Observability (filled in later plans) ===
SENTRY_DSN=
LOG_LEVEL=INFO
```

- [ ] **Step 2: Verify nothing references `.env` itself yet (template only)**

```bash
grep -r "from .env" apps/ packages/ 2>/dev/null || echo "OK: no premature .env consumers"
```

Expected: `OK: no premature .env consumers`.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example template"
```

---

## Task 14: Add the developer Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create `Makefile`**

```makefile
SHELL := /bin/bash
.PHONY: help install db-up db-down db-logs api worker web dev lint format typecheck test check clean

help:
	@echo "Xtrusio dev Makefile"
	@echo ""
	@echo "  make install     - install JS + Python dependencies"
	@echo "  make db-up       - start Postgres + Valkey"
	@echo "  make db-down     - stop Postgres + Valkey"
	@echo "  make db-logs     - tail Postgres + Valkey logs"
	@echo "  make api         - run FastAPI dev server (XTRUSIO_PROCESS_ROLE=api)"
	@echo "  make worker      - placeholder; real worker added in later plans"
	@echo "  make web         - run Vite dev server"
	@echo "  make dev         - bring up DBs + API + web in parallel"
	@echo "  make lint        - lint Python + JS"
	@echo "  make format      - format Python + JS"
	@echo "  make typecheck   - mypy + tsc"
	@echo "  make test        - run all tests (Python + JS)"
	@echo "  make check       - lint + typecheck + test"
	@echo "  make clean       - remove caches and venvs"

install:
	pnpm install
	uv sync

db-up:
	docker compose up -d postgres valkey
	@echo "Waiting for services to be healthy..."
	@until docker compose ps --format json postgres | grep -q '"Health":"healthy"'; do sleep 1; done
	@until docker compose ps --format json valkey | grep -q '"Health":"healthy"'; do sleep 1; done
	@echo "DBs ready."

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres valkey

api:
	XTRUSIO_PROCESS_ROLE=api uv run uvicorn xtrusio_api.main:app --reload --port 8000 --app-dir apps/api/src

worker:
	@echo "worker target is a placeholder until later plans add Dramatiq/Prefect."
	@echo "Run 'XTRUSIO_PROCESS_ROLE=worker uv run python -c \"print(\\\"worker shell ready\\\")\"' for now."

web:
	pnpm --filter @xtrusio/web dev

dev: db-up
	@trap 'kill 0' INT TERM; \
	$(MAKE) api & \
	$(MAKE) web & \
	wait

lint:
	uv run ruff check apps/api
	uv run ruff format --check apps/api
	pnpm exec turbo run lint

format:
	uv run ruff format apps/api
	uv run ruff check --fix apps/api
	pnpm exec prettier --write .

typecheck:
	uv run mypy apps/api
	pnpm exec turbo run typecheck

test:
	uv run pytest apps/api/tests
	pnpm exec turbo run test

check: lint typecheck test

clean:
	rm -rf node_modules .pnpm-store .venv .turbo
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 2: Verify Makefile help target**

```bash
make help
```

Expected: prints the help text above without errors.

- [ ] **Step 3: Verify `make install` from a clean state**

```bash
make install
```

Expected: pnpm install + uv sync both complete without errors.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat: add developer Makefile"
```

---

## Task 15: Wire `lint`, `typecheck`, `test` Turbo tasks across all packages

**Files:**
- Modify: `apps/web/package.json` (already has scripts from Task 8 — verify)
- Modify: `packages/ui/package.json` (already has scripts from Task 10 — verify)
- Modify: `packages/api-types/package.json` (already has scripts from Task 11 — verify)

- [ ] **Step 1: Run the Turbo pipeline end-to-end**

```bash
pnpm exec turbo run lint typecheck test
```

Expected: every package's `lint`, `typecheck`, and `test` scripts run; all exit 0. Some print the placeholder `'no source yet'` / `'no tests yet'` echoes — that's correct.

- [ ] **Step 2: Run the full `make check`**

```bash
make check
```

Expected:
- `uv run ruff check apps/api` → 0 errors
- `uv run ruff format --check apps/api` → "would reformat 0 files"
- `pnpm exec turbo run lint` → all packages pass
- `uv run mypy apps/api` → "Success: no issues found"
- `pnpm exec turbo run typecheck` → all packages pass
- `uv run pytest apps/api/tests` → 1 passed
- `pnpm exec turbo run test` → 1 passed (the web smoke test)

- [ ] **Step 3: Commit if any tweaks were needed**

If `make check` failed at any step, fix the underlying file (do not modify the test or Makefile to skip it). Once passing:

```bash
git add -A
git commit -m "chore: verify make check passes end-to-end"
```

If nothing changed, no commit needed.

---

## Task 16: Verify `make dev` brings up the full stack

This task has **no file changes**. It's a validation gate. If `make dev` doesn't bring everything up cleanly, this is a regression — fix it before claiming Plan 1A done.

- [ ] **Step 1: Start fresh**

```bash
make db-down
docker volume rm xtrusio_postgres_data xtrusio_valkey_data 2>/dev/null || true
```

(Volume names may differ — check `docker volume ls | grep xtrusio` and adjust.)

- [ ] **Step 2: Run `make dev`**

```bash
make dev
```

Expected behavior:
- `docker compose up -d postgres valkey` brings DBs to healthy.
- API starts on `:8000` with reload.
- Web starts on `:5173`.
- Console shows interleaved logs from both processes.

- [ ] **Step 3: Smoke-test both services in a second terminal**

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}

curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173
# Expected: 200
```

- [ ] **Step 4: Tear down with Ctrl-C**

In the `make dev` terminal: press Ctrl-C. Both API and web should stop. Then:

```bash
make db-down
```

- [ ] **Step 5: Document the result**

If everything passed, no commit needed — this is a verification gate, not a code change.
If something broke, fix it in the appropriate file (Makefile, docker-compose.yml, app config) and commit the fix:

```bash
git add -A
git commit -m "fix: <short description of what broke and how it was fixed>"
```

---

## Task 17: Add the root README quickstart

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

````markdown
# Xtrusio

Multi-tenant AI SaaS platform.

## Prerequisites

- **Docker Desktop** (or compatible runtime) — running.
- **Node 22** — manage with `fnm` / `nvm` / `volta`. Project uses the version in `.nvmrc`.
- **pnpm 10** — `corepack enable && corepack prepare pnpm@10 --activate`.
- **Python 3.12** — `uv` will manage the interpreter; install `uv` itself:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **GNU Make** (preinstalled on macOS/Linux).

## First-time setup

```bash
git clone <repo>
cd xtrusio
cp .env.example .env
make install
```

## Daily development

| Command | What it does |
|---|---|
| `make dev` | Brings up Postgres + Valkey + API + Web in one terminal. |
| `make db-up` / `make db-down` | DBs only. |
| `make api` | FastAPI dev server on `:8000` (`XTRUSIO_PROCESS_ROLE=api`). |
| `make web` | Vite dev server on `:5173`. |
| `make worker` | Placeholder until later plans add Dramatiq/Prefect. |
| `make lint` | Ruff + ESLint + Prettier check. |
| `make format` | Auto-format Python + JS. |
| `make typecheck` | mypy + tsc. |
| `make test` | pytest + Vitest. |
| `make check` | lint + typecheck + test (run before committing). |
| `make clean` | Wipe caches and venvs. |

## Layout

```
apps/
  api/       FastAPI backend (Python, uv-managed)
  web/       Vite + React frontend (TS, pnpm-managed)
packages/
  ui/        Shared UI components (placeholder until later plans)
  api-types/ Generated OpenAPI types (placeholder until later plans)
infra/
  postgres/  Postgres init scripts (extensions)
docs/
  superpowers/specs/   Design specs
  superpowers/plans/   Implementation plans
```

## URLs

- API: http://localhost:8000
  - Health: `/health`
  - OpenAPI: `/docs`
- Web: http://localhost:5173

## CI/CD

Not in scope yet. Project policy: CI/CD is added once the local development environment runs cleanly end-to-end. Until then, `make check` is the contract.
````

- [ ] **Step 2: Verify the README renders correctly**

```bash
cat README.md | head -20
```

Expected: prints the first 20 lines including the H1 and Prerequisites section.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add quickstart README"
```

---

## Task 17A: Wire pre-commit hooks for local quality gate

**Files:**
- Create: `.pre-commit-config.yaml`
- Add devDependency to root `package.json`: none (`pre-commit` itself is installed via `uv` because it's a Python tool)

**Why:** `pre-commit` runs the same lint+format checks `make check` runs, but on every `git commit`, on only the changed files. Catches issues before they hit the repo. This is **local tooling, not CI/CD** — it complies with the project policy (no GitHub Actions / no automated runners).

- [ ] **Step 1: Add `pre-commit` to the root Python dev dependencies**

Edit `pyproject.toml` to add `pre-commit` to the dev group. If the root `pyproject.toml` doesn't yet have a `[dependency-groups]` section, add one:

```toml
[dependency-groups]
dev = [
    "pre-commit~=3.8.0",
]
```

Sync:

```bash
uv sync
```

- [ ] **Step 2: Create `.pre-commit-config.yaml`**

```yaml
# Local quality gate. Runs on `git commit` against changed files only.
# Mirrors what `make check` does — same tools, smaller scope.

default_language_version:
  python: python3.12

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: check-merge-conflict
      - id: mixed-line-ending
        args: ["--fix=lf"]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: ["--fix"]
        files: ^apps/api/
      - id: ruff-format
        files: ^apps/api/

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.3.3
    hooks:
      - id: prettier
        types_or: [javascript, jsx, ts, tsx, json, yaml, markdown, css]
        exclude: |
          (?x)^(
            pnpm-lock\.yaml|
            uv\.lock|
            apps/web/dist/|
            .*\.tsbuildinfo
          )$
```

- [ ] **Step 3: Install the hooks locally**

```bash
uv run pre-commit install
```

Expected: `pre-commit installed at .git/hooks/pre-commit`.

- [ ] **Step 4: Run pre-commit against all files once to baseline**

```bash
uv run pre-commit run --all-files
```

Expected: all hooks pass (some may auto-fix trailing whitespace / EOF — that's normal on the first run). Re-run if it auto-fixed anything; second run should be clean.

If anything fails legitimately (not auto-fixable), fix the underlying file and re-run. Don't disable hooks.

- [ ] **Step 5: Commit (the hook will run on this very commit)**

```bash
git add .pre-commit-config.yaml pyproject.toml uv.lock
git commit -m "chore: add pre-commit config (local quality gate, no CI)"
```

If the hook makes auto-fixes during this commit, re-stage and commit again:

```bash
git add -A
git commit --amend --no-edit
```

---

## Task 18: Final validation — fresh clone simulation

This is the **definition-of-done gate** for Plan 1A. Pretend you are a brand-new engineer cloning the repo for the first time. No file changes; pure validation.

- [ ] **Step 1: Wipe build artifacts**

```bash
make clean
make db-down
docker volume ls --filter name=xtrusio --format '{{.Name}}' | xargs -r docker volume rm
```

- [ ] **Step 2: Reinstall from scratch**

```bash
make install
```

Expected: pnpm + uv both succeed.

- [ ] **Step 3: Run the full check**

```bash
make check
```

Expected: every step exits 0.

- [ ] **Step 4: Run `make dev`**

```bash
make dev &
DEV_PID=$!
sleep 15
curl -s http://localhost:8000/health    # → {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173    # → 200
kill -INT $DEV_PID
wait $DEV_PID 2>/dev/null || true
make db-down
```

Expected: both curls return successfully; tear-down completes.

- [ ] **Step 5: Commit completion marker (optional)**

If you want a clean "Plan 1A done" commit on the log:

```bash
git commit --allow-empty -m "chore: Plan 1A complete — local dev scaffold verified"
```

---

## Plan 1A — Definition of Done

When all of the following are true, Plan 1A is complete and Plan 1B (DB foundation) can begin:

1. `make install` succeeds on a fresh clone.
2. `make check` exits 0 (lint + typecheck + test all pass).
3. `make dev` brings up Postgres, Valkey, API on `:8000`, and web on `:5173`.
4. `curl http://localhost:8000/health` returns `{"status":"ok"}`.
5. `curl http://localhost:5173` returns HTTP 200.
6. `docker exec xtrusio-postgres psql -U xtrusio -d xtrusio -c "\dx"` shows `vector`, `pgcrypto`, `citext` extensions installed.
7. `docker exec xtrusio-valkey valkey-cli ping` returns `PONG`.
8. `docker network inspect xtrusio-net` shows both `xtrusio-postgres` and `xtrusio-valkey` attached.
9. `docker port xtrusio-postgres 5432` returns `0.0.0.0:54322`; `docker port xtrusio-valkey 6379` returns `0.0.0.0:63792`.
10. `apps/api/src/xtrusio_api/main.py` and `apps/web/src/App.tsx` exist with the exact contents shown in Tasks 7 and 9.
11. `mise.toml` exists pinning Node 22, Python 3.12, pnpm 10.
12. `.pre-commit-config.yaml` exists; `uv run pre-commit run --all-files` passes.
13. The repo has zero `.github/workflows/*` files and no CI/CD setup, per project policy.

---

## Notes for the Engineer

- **Why TDD on a scaffold?** Because the smoke test for `/health` is the simplest possible regression detector — if a future change breaks the API server, this test fails before anything subtle does. Same for the `App` smoke test.
- **Why no `.env` file by default?** It's gitignored. `make api` and `make web` read environment variables; for local dev, `.env.example`'s defaults already point at `localhost:54322` (Postgres) / `localhost:63792` (Valkey) / `localhost:8000` (API), so most engineers don't need to copy `.env.example` to `.env` until they want to override something.
- **Why `XTRUSIO_PROCESS_ROLE`?** Plan 1A doesn't use it for anything functional yet — but Plan 1C (auth) and the analysis toolkit (spec #3) both rely on it. Setting it correctly from day one prevents a class of bugs later.
- **Why is `make worker` a placeholder?** The worker process needs Dramatiq/Prefect, which are introduced in later plans (around Plan 1C/1D). The placeholder keeps the developer-facing command surface stable so we don't have to retrain muscle memory later.
- **Why no shadcn/ui or Tailwind yet?** That comes with the frontend shell plan (around Plan 1D). Plan 1A is intentionally minimal — adding design-system pieces too early creates churn.

---

## What This Plan Does NOT Include

These are intentionally deferred to later plans:

- Alembic migrations (Plan 1B)
- Tenants table and RLS infrastructure (Plan 1B)
- Supabase auth wiring (Plan 1C)
- Identity tables (`platform_users`, `tenant_users`) (Plan 1D)
- TanStack Router and frontend layout (Plan 1D/1E)
- shadcn/ui, Tailwind, theme system (Plan 1D)
- Dramatiq, Prefect, observability stack (Plan 1C+)
- GitHub Actions / CI runners (deferred until local-stable bar; tracked separately)
