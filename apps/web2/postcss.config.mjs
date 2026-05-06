// Tailwind v4 with the dedicated PostCSS plugin. No `@tailwind` directives
// needed — the framework auto-injects via `@import "tailwindcss"` in
// `app/globals.css`.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
