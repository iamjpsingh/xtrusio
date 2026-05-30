// packages/api-types/scripts/generate.ts
//
// OpenAPI -> TypeScript codegen for @xtrusio/api-types (F.3, finding H13).
//
// Pipeline:
//   1. Dump the FastAPI OpenAPI schema to JSON by importing the app and calling
//      `app.openapi()`. This only introspects routes — the lifespan does NOT run
//      on import, so no live DB/Supabase connection is needed. Settings still
//      load (from the repo-root `.env`), so the import must run with that env.
//   2. Feed the JSON through `openapi-typescript` to produce
//      `generated/openapi.d.ts`.
//
// Determinism: `openapi-typescript` is deterministic for a fixed input schema,
// so re-running with an unchanged backend produces a byte-identical file. The
// CI drift gate (.github/workflows/api-types-drift.yml) relies on this.
//
// Run via:  pnpm api-types:generate   (from the repo root)

import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const repoRoot = resolve(packageRoot, "..", "..");
const outFile = resolve(packageRoot, "generated", "openapi.d.ts");

/**
 * Dump the FastAPI OpenAPI schema as a JSON string. Settings load from the
 * repo-root `.env`; uv runs the API app with `--directory apps/api` so the
 * `xtrusio_api` package is importable.
 */
function dumpOpenApiJson(): string {
  const result = spawnSync(
    "uv",
    [
      "run",
      "--directory",
      "apps/api",
      "python",
      "-c",
      "import json,sys; from xtrusio_api.main import app; json.dump(app.openapi(), sys.stdout)",
    ],
    {
      cwd: repoRoot,
      encoding: "utf8",
      // Inherit the ambient env (the `pnpm api-types:generate` wrapper sources
      // the repo-root `.env` before invoking tsx, so Settings validation passes).
      env: process.env,
      maxBuffer: 32 * 1024 * 1024,
    },
  );

  if (result.status !== 0) {
    process.stderr.write(result.stderr ?? "");
    throw new Error(
      `Failed to dump OpenAPI schema (exit ${result.status}). ` +
        "Ensure the repo-root .env is sourced and `uv` is installed.",
    );
  }
  return result.stdout;
}

async function main(): Promise<void> {
  const json = dumpOpenApiJson();
  const schema = JSON.parse(json) as Parameters<typeof openapiTS>[0];

  const ast = await openapiTS(schema, {
    // Make nullable fields surface as `T | null` (not `T`) so the generated
    // types match the runtime JSON shape exactly.
    enum: false,
  });

  const banner =
    "/**\n" +
    " * GENERATED FILE — DO NOT EDIT BY HAND.\n" +
    " *\n" +
    " * Produced by `pnpm api-types:generate` (packages/api-types/scripts/generate.ts)\n" +
    " * from the FastAPI OpenAPI schema. Re-run after any backend schema change;\n" +
    " * the api-types-drift CI gate fails if this file is stale.\n" +
    " */\n\n";

  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, banner + astToString(ast), "utf8");
  process.stdout.write(`Wrote ${outFile}\n`);
}

main().catch((err: unknown) => {
  process.stderr.write(`${String(err)}\n`);
  process.exit(1);
});
