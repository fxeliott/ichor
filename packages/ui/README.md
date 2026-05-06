# `packages/ui` — Ichor design system

15 canonical components (12 from the original Phase 0 plan + 3
extensions — Timeline / EmptyState / DrillDownButton — added during
Phase 1 Step 1 marathon) :

- `<BiasBar>` — directional bias visualization
- `<AssetCard>` — asset-level summary card
- `<RegimeIndicator>` — HMM regime badge
- `<ConfidenceMeter>` — calibrated probability with credible interval
- `<SourceBadge>` — Anthropic Citations API source link
- `<AlertChip>` — alert classification chip
- `<BriefingHeader>` — briefing metadata header
- `<AudioPlayer>` — Azure Neural TTS audio playback
- `<DrillDownButton>` — request deeper Claude analysis on click
- `<ChartCard>` — lightweight-charts wrapper with Ichor branding
- `<DisclaimerBanner>` — AMF + EU AI Act Article 50 AI disclosure
- `<EmptyState>` — fallback when data unavailable

## Status (2026-05-06)

**SHIPPED**. Used by `apps/web` (legacy Phase 1 dashboard).
`apps/web2` (Phase 2 redesign) deliberately reimplements its own
component layer to align with the new design tokens (Tailwind v4

- motion 12 + Geist/JetBrains Mono/Fraunces stack) — the two
  dashboards run in parallel until web1 is decommissioned.

No automated tests at this layer ; the web2 e2e smoke suite
(`apps/web2/e2e/smoke.spec.ts`) covers the routes that consume
these components. RTL coverage is a Phase C deliverable.
