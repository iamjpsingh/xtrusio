import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

// Read .env from the repo root, not apps/web/. Object-form config (not a
// callback) so vitest's mergeConfig can consume this.
const envDir = path.resolve(__dirname, "../..");
const env = loadEnv(process.env.NODE_ENV ?? "development", envDir, "");
if (!env.WEB_DEV_PORT) {
  throw new Error("WEB_DEV_PORT must be set in .env");
}

export default defineConfig({
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  envDir,
  server: {
    port: Number(env.WEB_DEV_PORT),
  },
});
