import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
      // Hermetic placeholders: unit tests never make real network calls
      // (api/auth/fetch are mocked); these only prevent lib/supabase.ts and
      // lib/api.ts from throwing at import. NOT app config — must be
      // fake/deterministic.
      env: {
        VITE_SUPABASE_URL: "http://supabase.test.invalid",
        VITE_SUPABASE_ANON_KEY: "test-anon-key-not-a-secret",
        VITE_API_BASE_URL: "http://api.test.invalid",
      },
    },
  }),
);
