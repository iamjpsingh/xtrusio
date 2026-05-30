import { defineConfig, mergeConfig } from "vitest/config";
import { configDefaults } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
      // Playwright E2E specs live under tests/e2e/** and use a DIFFERENT runner
      // (@playwright/test). They must NEVER be collected by vitest — keep the
      // default exclude list AND drop the whole e2e tree (F.2).
      exclude: [...configDefaults.exclude, "tests/e2e/**"],
      // Hermetic placeholders: unit tests never make real network calls
      // (api/auth/fetch are mocked or intercepted by MSW); these only prevent
      // lib/supabase.ts and lib/api.ts from throwing at import. NOT app config
      // — must be fake/deterministic.
      env: {
        VITE_SUPABASE_URL: "http://supabase.test.invalid",
        VITE_SUPABASE_ANON_KEY: "test-anon-key-not-a-secret",
        VITE_API_BASE_URL: "http://api.test.invalid",
      },
      coverage: {
        provider: "v8",
        reporter: ["text-summary", "cobertura", "html"],
        // Conservative starting floor (F.2 / spec §9). Ratchet up via PR. Only
        // application source counts — exclude tests, generated route tree, the
        // MSW test harness, and config/entrypoints that aren't unit-tested.
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/**/*.test.{ts,tsx}",
          "src/test/**",
          "src/test-setup.ts",
          "src/routeTree.gen.ts",
          "src/main.tsx",
          "src/vite-env.d.ts",
        ],
        thresholds: {
          statements: 60,
          branches: 60,
          functions: 60,
          lines: 60,
        },
      },
    },
  }),
);
