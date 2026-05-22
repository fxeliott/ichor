# SESSION_LOG 2026-05-16 — Round 82 (ADR-099 Tier 1.5: Corrélations unconditional → Tier 1 CLOSED)

> Round type: **frontend-only** (low-risk ; `/v1/correlations` already
> existed → no backend split). Branch `claude/friendly-fermi-2fff71`.
> ZERO Anthropic API spend. Voie D + ADR-017 held. Trigger: Eliot
> "continue" → ADR-099 Tier 1.5.

## What r82 shipped — closes Tier 1 end-to-end

The Corrélations panel was **hidden entirely** when
`card.correlations_snapshot` was absent (`{card?.correlations_snapshot
? (...) : null}`). Now it **always renders**, with a live fallback.

- R59: `/v1/correlations` already exists (`routers/correlations.py`,
  `CorrelationMatrix` shape: assets[] + matrix[][]). `CorrelationMatrix`
  TS type already in api.ts:718 → **reused (anti-doublon)**, no new type.
- `lib/api.ts`: `getCorrelations(windowDays=30)` helper (house pattern,
  reuses `CorrelationMatrix`).
- `app/briefing/[asset]/page.tsx`: fetch `/v1/correlations` in the SSR
  `Promise.all` ; `deriveCorrelationRow(matrix, asset)` extracts THIS
  asset's row → `{compactKey: rho}` with a small `_CORR_KEY` map
  (EUR_USD→EURUSD …) so the **existing CorrelationsStrip parser renders
  "EUR/USD" etc. with ZERO component change** (anti-accumulation, zero
  regression). Precedence: card snapshot → live-derived row → honest
  empty-state. Section is now **unconditional** with a dynamic source
  label ("Snapshot carte" / "Live · fenêtre N j" / "Indisponible").

## Empirical witnesses (R59)

- `tsc --noEmit` + `eslint --max-warnings 0` clean (api.ts + page.tsx ;
  CorrelationsStrip untouched).
- `redeploy-web2.sh deploy`: `DEPLOY OK`, `local=200 public=200`, URL
  unchanged (r75 fix holds).
- Live `/v1/correlations` via the client proxy path: `assets` =
  `[EUR_USD,GBP_USD,USD_JPY,AUD_USD,USD_CAD,XAU_USD,NAS100_USD,SPX500_USD]`
  — **all 5 priority assets present**, `n_returns_used=239`, a real flag
  (`XAU_USD/NAS100_USD unusually tighter +0.53 vs +0.20`). So the
  fallback works for every priority asset.
- Rendered SSR `/briefing/EUR_USD`: `correlations-heading` present +
  source `"Snapshot carte · co-mouvement"` (EUR_USD's card HAS a
  snapshot → card path taken, correct precedence). `volume-heading` +
  `institutional-heading` present → **no regression**.
- Verification scope (honest): the card-path render is verified live.
  The live-fallback render path is verified-AVAILABLE (endpoint returns
  all 5 priority assets through the client proxy) + typechecked, but
  not force-rendered this round because EUR_USD has a card snapshot.
  The structural gap (section hidden when no snapshot) is fixed: the
  section is now unconditional + the fallback source is reachable.

## Tier 1 status — CLOSED

T1.1 Volume ✅ (r75) · T1.2 Géopolitique ✅ (r76+r77) · T1.3
holiday/weekend ✅ (r78+r79) · T1.4 institutional positioning ✅
(r80+r81) · **T1.5 Corrélations unconditional ✅ (r82)**. All explicit
ADR-099 vision-coverage gaps closed end-to-end.

## Next stage (on Eliot "continue")

ADR-099 **Tier 2 — analytical depth**, starting with the ichor-trader
**#1 gap**: the cross-asset **net-exposure / confluence lens** in
`apps/web2/lib/verdict.ts`. `verdict.ts` never reads correlation data,
so 5 verdicts that are really ~2.5 independent bets (SPX≈NAS ~0.9,
EUR/GBP co-move) are shown as 5. Now that `getCorrelations` exists
(r82), the cockpit `/briefing/page.tsx` can cluster the 5 verdicts by
correlation and surface "your 5 reads = ~N independent bets". HIGH
value / LOW effort (data already available). ADR-017-safe (pure
exposure-clustering context, no BUY/SELL). Optional before that: AAII
equity-sentiment follow-up (SPX/NAS sentiment layer).

## Checkpoint

Commit: api.ts + page.tsx + this SESSION_LOG on
`claude/friendly-fermi-2fff71`. Memory updated separately.
