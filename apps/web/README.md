# `apps/web` — Ichor dashboard (DEPRECATED)

> **DEPRECATED 2026-05-06** — replaced by [`apps/web2`](../web2/) (ADR-018).
>
> The 6 routes that lived only here (`/sessions` index,
> `/briefings/[id]`, `/hourly-volatility/[asset]`, `/assets/[code]`,
> `/confluence`, `/confluence/history`) were ported to `apps/web2`
> during the D.3 sprint of 2026-05-06. This package is no longer part
> of the pnpm workspace (see `pnpm-workspace.yaml`) and stops receiving
> tooling, dependabot, or CI runs from now on.
>
> The directory is kept on disk as a read-only reference for design
> tokens / Tailwind class patterns until Phase C completes the design
> system port. Once Phase C ships, this directory will be moved to
> `archive/2026-05-XX-web1-decommissioned/`.

## Historical context (Next.js 15 + Tailwind v4 + shadcn/ui + lightweight-charts v5.2 + motion v12)

Deployed to Cloudflare Pages on `app-ichor.pages.dev` during Phase 0
(domain `ichor.app` deferred — see `docs/decisions/ADR-002`).

### Phase 0 status (frozen 2026-05-06)

🛑 Decommissioned. Phase 0 dashboard work continues in `apps/web2`.

## Stack rationale (verified 2026-05-02)

- **Next 15.x**, not 16.x — Serwist (PWA) incompat with Next 16 Webpack
  changes (see `docs/AUDIT_V3.md` §6).
- **Tailwind v4** with @tailwindcss/postcss (v4 dropped the standalone CLI).
- **lightweight-charts v5.2.0** — `attributionLogo: true` is now the default
  (compliance attribution simplified, no custom code needed).
- **motion v12.38.0**, not framer-motion — package was renamed in 2025.
- **orval ≥8.0.3** required for OpenAPI codegen (CVE-2026-24132 RCE patched).
