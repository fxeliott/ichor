// Next.js 15 + TypeScript ESLint flat config — extends the repo root.
// When `pnpm install` runs, the root eslint.config.mjs will be enriched
// with @next/eslint-plugin-next + typescript-eslint + react-hooks +
// jsx-a11y. For now this file just re-exports the root for parity with
// `apps/web/`.

import baseConfig from "../../eslint.config.mjs";

export default [
  ...baseConfig,
  {
    ignores: [".next/**", "out/**", "node_modules/**"],
  },
];
