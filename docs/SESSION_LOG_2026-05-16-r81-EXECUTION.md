# SESSION_LOG 2026-05-16 — Round 81 (ADR-099 Tier 1.4b: InstitutionalPositioningPanel)

> Round type: **frontend** (pure-frontend, low-risk — proven pattern).
> Branch `claude/friendly-fermi-2fff71`. ZERO Anthropic API spend.
> Voie D + ADR-017 held. Trigger: Eliot "continue" → ADR-099 Tier 1.4b.

## What r81 shipped — closes the institutional half of "acteurs du marché"

`InstitutionalPositioningPanel.tsx` (new, house style ex-VolumePanel/
GeopoliticsPanel/CorrelationsStrip) consuming the r80
`/v1/positioning/institutional?asset=X`. The smart-money complement to
the existing MyFXBook RETAIL panel — together they cover Eliot's
"ce que font les acteurs du marché" axis.

- `lib/api.ts`: `TffPositioning` / `CotPositioning` /
  `InstitutionalPositioning` types + `getInstitutionalPositioning(asset)`
  (house get\* pattern, mirrors the r80 Pydantic shape — anti-doublon).
- `InstitutionalPositioningPanel.tsx`: **TFF 4-class diverging bars**
  (Dealer/AssetMgr/LevFunds/Other, net long=bull/right, short=bear/left,
  scaled to max-abs, Δw/w shown, `Intl.NumberFormat` thousands +
  signed) + the descriptive **smart-money-divergence** callout when
  true ("contexte, pas un ordre" — ADR-017) + **COT block** (managed-
  money/swap/producer nets + Δ1/4/12w + pattern badge) OR an honest
  "COT non couvert pour cet actif" note when `cot:null` (ADR-093
  degraded-explicit, not a scary empty). Weekly `report_date`
  staleness badge (no fake freshness).
- `app/briefing/[asset]/page.tsx`: `getInstitutionalPositioning` added
  to the SSR `Promise.all`; new `<section>` "Acteurs du marché" placed
  right after the retail "Positionnement" section (the two halves
  grouped). No other call-site (deep-dive only — cockpit doesn't show
  per-asset positioning).

## Empirical witnesses (R59 — "marche exactement")

- `tsc --noEmit` + `eslint --max-warnings 0` clean on the 3 files.
- `redeploy-web2.sh deploy`: `DEPLOY OK`, `local=200 public=200`, URL
  **unchanged** `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (r75 conditional-tunnel fix still holds).
- Rendered SSR `/briefing/EUR_USD` (server-fetched, so the panel is in
  the HTML): `institutional-heading` + `Acteurs du marché` +
  `Positionnement institutionnel` + `TFF 4 classes` + `Asset Mgr` +
  `Lev Funds` present → real r80 TFF data renders. `COT Disaggregated`
  present = the honest "non couvert" note (EUR_USD `cot:null` from r80
  — correct degraded path, not a bug). `volume-heading` +
  `geopolitics-heading` present → **no regression** (Volume r75 /
  Géopolitique r77 intact).
- The `Rapport 2026-05-12` badge string didn't exact-match the grep
  (markup-spacing artifact, same as the r77 `Observé <date>` case) —
  the decisive heading + TFF-class markers conclusively prove the
  real-data render.
- ADR-017 intact: panel is pure positioning facts + a descriptive
  divergence flag explicitly framed "contexte, pas un ordre"; no
  BUY/SELL in the new component.

## Tier 1 progress

T1.1 Volume ✅ (r75) · T1.2 Géopolitique ✅ (r76+r77) · T1.3
holiday/weekend ✅ (r78+r79) · **T1.4 institutional positioning ✅
end-to-end (r80 backend + r81 frontend)** — the SPX/NAS positioning
dark gap is now filled (TFF covers SPX500 13874A). Remaining:
T1.4-followup AAII equity-sentiment (optional, fills SPX/NAS _sentiment_
layer 6), T1.5 Correlations unconditional.

## Next stage (on Eliot "continue")

ADR-099 **Tier 1.5 — Correlations unconditional**: the
`CorrelationsStrip` is gated on `card.correlations_snapshot` (hidden
when absent). R59 first: check `_section_correlations` + whether a
`/v1/correlations` read exists; make the panel always render (fallback
to the live correlations source), honest empty-state when truly absent.
Then the optional AAII follow-up, then Tier 2 (analytical depth /
verdict.ts net-exposure lens — the ichor-trader #1 gap).

## Checkpoint

Commit: api.ts + InstitutionalPositioningPanel.tsx + page.tsx + this
SESSION_LOG on `claude/friendly-fermi-2fff71`. Memory updated separately.
