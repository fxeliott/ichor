// Root ESLint flat config — covers JS/TS/JSX/TSX across the workspace.
//
// Scope:
//   - apps/web/**        (legacy frontend, kept lint-clean during migration)
//   - apps/web2/**       (Phase 2 redesign — primary target)
//   - packages/ui/**     (shared component lib)
//
// Toolchain:
//   - typescript-eslint v8 (parser + plugin)
//   - @next/eslint-plugin-next 15 (Core Web Vitals + Next 15 best practices)
//   - eslint-plugin-react-hooks 5 (rules of hooks)
//   - eslint-plugin-jsx-a11y 6 (WCAG-adjacent rules; cf SPEC_V2_DESIGN.md §6)
//   - eslint-plugin-react 7 (JSX rules subset)
//
// Per-package `eslint.config.mjs` files re-export from this base.

import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import nextPlugin from "@next/eslint-plugin-next";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";

export default tseslint.config(
  // ── Global ignores ────────────────────────────────────────────────
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/.turbo/**",
      "**/dist/**",
      "**/build/**",
      "**/out/**",
      "**/coverage/**",
      "**/.venv/**",
      "**/.venv-tooling/**",
      "**/site-packages/**",
      "**/__pycache__/**",
      "**/.cache/**",
      "archive/**",
      "phase0-artifacts/**",
      "**/next-env.d.ts",
      "**/tsconfig.tsbuildinfo",
      "**/playwright-report/**",
      "**/test-results/**",
      // apps/web is the legacy frontend kept running during the apps/web2
      // migration. It uses `next lint` with its own implicit config; the
      // root flat config focuses on apps/web2 + packages/ui to avoid
      // double-linting with diverging rules. Re-include once parity is
      // reached and apps/web is archived.
      "apps/web/**",
    ],
  },

  // ── Base JS rules everywhere ──────────────────────────────────────
  js.configs.recommended,

  // ── TypeScript-aware rules everywhere ─────────────────────────────
  ...tseslint.configs.recommended,

  // ── Language options ──────────────────────────────────────────────
  {
    files: ["**/*.{js,mjs,cjs,jsx,ts,tsx,mts,cts}"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2024,
      },
    },
    rules: {
      // Defer no-unused-vars to TS-aware version (handles types correctly).
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      // Allow @ts-ignore in narrow cases but force a description.
      "@typescript-eslint/ban-ts-comment": [
        "warn",
        { "ts-ignore": "allow-with-description", "ts-expect-error": "allow-with-description" },
      ],
      // Strict equality + sane defaults.
      eqeqeq: ["error", "smart"],
      "no-var": "error",
      "prefer-const": "warn",
      "no-console": ["warn", { allow: ["warn", "error", "info"] }],
    },
  },

  // ── React + Next.js + a11y for .jsx/.tsx ──────────────────────────
  {
    files: ["**/*.{jsx,tsx}"],
    plugins: {
      "@next/next": nextPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
      react,
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      // Next.js core-web-vitals (subset of recommended that catches LCP/CLS bugs).
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
      // React Hooks correctness.
      ...reactHooks.configs.recommended.rules,
      // a11y subset — anchor + alt + aria attribute checks. Does NOT replace
      // axe-core scans (planned in Storybook + Playwright per HARDENING §2).
      ...jsxA11y.configs.recommended.rules,
      // React JSX hygiene.
      "react/jsx-key": "error",
      "react/jsx-no-undef": "error",
      "react/jsx-uses-react": "off", // automatic JSX runtime
      "react/jsx-uses-vars": "error",
      "react/no-unescaped-entities": "off", // French apostrophes are common in copy
      "react/react-in-jsx-scope": "off", // automatic JSX runtime
    },
    settings: {
      react: { version: "detect" },
    },
  },

  // ── Server-side Node files: relax browser-globals checks ──────────
  {
    files: [
      "**/next.config.{js,mjs,ts}",
      "**/postcss.config.{js,mjs,ts}",
      "**/tailwind.config.{js,mjs,ts}",
      "**/eslint.config.{js,mjs,ts}",
      "**/*.config.{js,mjs,ts}",
    ],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
);
