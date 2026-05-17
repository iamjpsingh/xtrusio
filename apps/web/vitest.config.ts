import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
      // Hermetic placeholders: unit tests never make real Supabase calls
      // (api/auth are mocked); these only prevent lib/supabase.ts from
      // throwing at import. NOT app config — must be fake/deterministic.
      env: {
        VITE_SUPABASE_URL: "http://supabase.test.invalid",
        VITE_SUPABASE_ANON_KEY: "test-anon-key-not-a-secret",
      },
    },
  }),
);
