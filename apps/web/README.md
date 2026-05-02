# `apps/web` — Ichor dashboard

Next.js 15 + Tailwind v4 + shadcn/ui + lightweight-charts v5.2 + motion v12.

Deployed to Cloudflare Pages on `app-ichor.pages.dev` during Phase 0
(domain `ichor.app` deferred — see `docs/decisions/ADR-002`).

## Phase 0 status

🚧 Skeleton only. Real implementation Phase 0 Week 4 (steps 25-32).

## Stack rationale (verified 2026-05-02)

- **Next 15.x**, not 16.x — Serwist (PWA) incompat with Next 16 Webpack
  changes (see `docs/AUDIT_V3.md` §6).
- **Tailwind v4** with @tailwindcss/postcss (v4 dropped the standalone CLI).
- **lightweight-charts v5.2.0** — `attributionLogo: true` is now the default
  (compliance attribution simplified, no custom code needed).
- **motion v12.38.0**, not framer-motion — package was renamed in 2025.
- **orval ≥8.0.3** required for OpenAPI codegen (CVE-2026-24132 RCE patched).
