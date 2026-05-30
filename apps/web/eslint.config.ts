import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  // E.11 (L11): the generated route tree ships its own `as any` casts; keep it
  // out of lint scope so it never adds noise or trips no-explicit-any.
  { ignores: ["dist", "node_modules", "src/routeTree.gen.ts"] },
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
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      // E.5 (H4): a `queryKey:` whose value is an inline array literal bypasses
      // the `qk` registry, so cache invalidation can silently miss. Force every
      // query key to come from `qk.*` (which returns arrays via a function call,
      // not an array-literal expression node).
      "no-restricted-syntax": [
        "error",
        {
          selector: "Property[key.name='queryKey'] > ArrayExpression",
          message:
            "Inline queryKey array literals bypass the `qk` registry. Use a `qk.*` factory from @/lib/query-keys instead.",
        },
      ],
    },
  },
);
