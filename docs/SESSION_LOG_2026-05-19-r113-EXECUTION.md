# SESSION_LOG 2026-05-19 — r113 EXECUTION

**ADR-099 §D-3 Tier 4 — additive NEW genuine `<Sparkline>` consumer:
the intraday true-range (high−low) amplitude micro-trend in
`BriefingHeader`, a 2nd DISTINCT proven-live series on the r112 generic
`<Sparkline>` (the r105 `xLinear`+`linScale`+`svgCoord` SSOT). Doctrine
#8 "more coverage", NOT de-accumulation (FULLY CLOSED r111). The
literal default (A) regime-timeline R59-DISPROVED → reshaped to (B).**
Branch `claude/friendly-fermi-2fff71`, continued post-r112 (Eliot
`continue` overrode `/clear` — lesson #17, context-frugal). Voie D +
ADR-017 held (pure descriptive geometry, no signal) ; ZERO backend /
ZERO migration (alembic 0050) ; NO new ADR (doctrine #9 — dated
`## Implementation (r113)` append) ; ZERO new component, ZERO new
coord math (doctrine #9 — the r112 `<Sparkline>` reused as-is).

## R59-first — the default is itself R59-subject (meta-r110/r112)

The r112-close binding default offered two candidates: (A) a NEW
regime-timeline component (reusing `regime-quadrant`
`RegimeId`/`QUADRANTS`) OR (B) further `<Sparkline>` consumers. Per
meta-r110/r112 (a "continue" default is a HYPOTHESIS, including an
additive one), it was R59-checked, not blindly executed. A read-only
researcher sub-agent + direct orchestrator file:line verification
**DISPROVED (A) as worded**:

- Repo-wide grep `regime_history|regime_timeline|regime_series` in
  `apps/web2` → **zero matches**.
- `SessionCard` (`lib/api.ts:195`) projects exactly ONE regime field:
  `regime_quadrant: string | null` — a single scalar, NOT a series.
  Consumed as one value only (`BriefingHeader.tsx:128-137` one chip,
  `page.tsx:248` `PocketSkillBadge`).
- `RegimeQuadrant.history?` is a `{x,y,ts}[]` macro-coordinate trail
  (NOT a regime-id series) AND `RegimeQuadrant` is **not rendered on
  the briefing page at all**. `QUADRANTS` is also a module-local const
  inside the `"use client"` `components/ui/regime-quadrant.tsx`
  (`:24,47`) — not even exported.
- ⇒ a regime-timeline frieze would have **no real series to render**:
  a fake-SSOT / SHIPPED≠FUNCTIONAL by construction (the r106/r108
  type-only trap). Per meta-r110/r112 the honest move is NOT to force
  it — it is to execute (B) on a series R59-proven projected AND
  populated.

## R59 verified consumption site + R53 real populated data (#1)

`recentBars: IntradayBarOut[]` (`page.tsx:189` `intraday.slice(-90)`,
endpoint `/v1/market/intraday/{asset}` `lib/api.ts:304-310`).
`IntradayBarOut` (`lib/api.ts:1189-1196`) carries
`open`/`high`/`low`/`close: number` + `volume: number | null`.
`close` is on screen (r112 Sparkline) and `volume` is on screen
(`VolumePanel`) — but `high`/`low` are charted nowhere, and
**type-presence ≠ runtime-populated (#1)**. R53 live-verified the
prod API directly (ONE consolidated throttle-aware SSH,
`curl 127.0.0.1:8000/v1/market/intraday/{EUR_USD,XAU_USD}?hours=24&limit=12`,
2026-05-19): real OHLC bars with genuinely distinct, non-degenerate,
varying high/low — EUR_USD bar 1 `open 1.16526 / high 1.16543 / low
1.1652 / close 1.16538` (12 bars, true-range 0.00023→0.0005) ; XAU_USD
bar 1 `open 4578.28 / high 4580.34 / low 4577.76 / close 4579.39`
(12 bars, true-range 2.35→4.58). `high − low` is **projected AND
empirically populated on real prod across 2 assets** —
SHIPPED≠FUNCTIONAL avoided BY CONSTRUCTION, the r112 discipline.

## What r113 implemented

1. **`apps/web2/components/briefing/BriefingHeader.tsx`** — a new
   optional `rangeTrend?: number[]` prop (decoupled `number[]`, mirror
   of the r112 `priceTrend?`) ; a 2nd `<Sparkline>` rendered under the
   r112 price one with its own neutral aria-label
   ("Amplitude intrajournalière (haut−bas) {asset}, {N} dernières
   barres") and a factual "Amplitude intraday · N barres" label ;
   self-guarding (`>= 2`) ; the `Renders :` docstring enumeration
   extended (anti-lesson-#5 drift).
2. **`apps/web2/app/briefing/[asset]/page.tsx`** — one line:
   `rangeTrend={recentBars.map((b) => b.high - b.low)}` (the SAME
   `recentBars` already derived for `VolumePanel`/the r112 Sparkline —
   ZERO new fetch, ZERO backend).
3. **`apps/web2/__tests__/microchart.test.ts`** — additive describe
   block (3 tests) pinning the r113 CONSUMER contract (NOT a
   byte-identical-vs-prior proof — NEW consumer, the honest
   distinction, r112-class): the high−low derivation ≥ 0 (the OHLC
   invariant) ; the amplitude series is a well-formed SSOT-composed
   Sparkline input (1-dp, x strictly increasing, in-viewBox) ; a
   perfectly steady market (constant range) → degenerate flat
   amplitude maps to the baseline, no NaN.
4. **ADR-099 `## Implementation (r113, 2026-05-19)`** — dated §Impl,
   NO new ADR (doctrine #9). Reviews / Verification written as
   placeholders then RECONCILED to the MEASURED outcomes (lesson #1 —
   no forecast).

## Honest scope / ledger (#11, NOT thinned)

r113 = ONE NEW genuine `<Sparkline>` consumer (intraday amplitude) +
the page wiring + the consumer contract test + the consolidated
review fixes. "More coverage" (doctrine #8), explicitly NOT
de-accumulation (FULLY CLOSED r111). DEFERRED, NOT thinned: the
regime-timeline NEW component (R59-disproved on the briefing page
this round — needs a NEW backend-projected regime series first, the
#1 Pydantic-projection class, a separate increment, NOT a
frontend-only Tier-4 item) ; further `<Sparkline>` consumers ; T4.2
(uncertainty band / calibration overlay / degraded+empty /
`prefers-reduced-motion` / no-truncated-axis) ; T4.3 (responsive).
PRE-EXISTING, NOT r113's, NOT re-scoped (flag-not-fix #11 / r106-a):
the r111-flagged app-wide console defects (vendor-chunk `TypeError`,
`/` CSP `localhost:8001`, React #418) + favicon-404 (r111
spawn-task) ; the r112-flagged header-wide `text-muted` ≈3.5:1
contrast (ADR-099 §T4.2 / `globals.css` §5 backlog) ; a NEW
PRE-EXISTING note surfaced this round (a11y) — the UNCHANGED r112
`Sparkline.tsx` `role="img"` + `aria-label` + `<title>` mirroring
causes an SR double-announce on some NVDA/JAWS, a component-wide
pre-existing item inherited by r113, routed to the same a11y backlog,
NOT a r113 regression.

## Reviews (consolidated single pass — doctrine #14 ; all 3 dispatched

— a NEW visual surface (a 2nd header micro-chart + a promoted label
word) genuinely changes the trading-boundary, design AND a11y surface,
protocol not FOMO #17 ; verdicts MEASURED not forecast, lesson #1)

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only)
  APPLIED.** ADR-017 frontend boundary held: the reviewer read
  `Sparkline.tsx:91` **directly** — neutral
  `stroke=var(--color-text-secondary)` **VERIFIED-TRUE, not asserted**
  (not direction-tinted, same neutral stroke for both price and
  amplitude — no per-series tinting) ; `high − low` is a non-negative
  scalar amplitude that **structurally cannot encode a directional
  call** ; labels factual-only (no BUY/SELL/imperative/order/sizing/
  direction word) — descriptive volatility context, equivalent to the
  existing `VolumePanel` "Activité intraday" overlay. Conviction cap
  untouched. SHIPPED≠FUNCTIONAL genuinely avoided (R53 ground-truth).
  Doctrine #8-vs-#9 ACCURATE (NEW consumer, zero new component, zero
  new coord math — verified `Sparkline.tsx:36,68,71` = the r105 SSOT).
  Backward-compat OK (optional prop, self-guarding, single call site).
  Cross-file drift: NONE (the `Renders :` docstring correctly
  updated, no stale price-only wording — the r112 ichor-trader-YELLOW
  class avoided). **YELLOW-1 (doc-only) APPLIED**: the ADR
  Reviews/Verification placeholders reconciled to the MEASURED
  verdicts.
- **ui-designer — MERGE-with-changes, 0 Critical ; 1 Important + 2 Nit
  APPLIED.** Important (the two charts visually indistinguishable —
  identical neutral stroke/dims/wrapper, a 10px label the sole
  differentiator ; exact-mirror right at r112 sibling-less but a
  sibling of a _different physical quantity_ makes parity hurt the
  instant read) → the differentiating first word of each label
  (`Prix` / `Amplitude`) promoted to a `font-medium
text-[var(--color-text-secondary)]` eye-lock token (no component
  change, zero new coord math #9 ; the factual word ichor-trader
  cleared — ADR-017-safe ; visible text content + reading order
  unchanged). Nit-1 (4 consecutive `mt-3` collapse the hierarchy) →
  amplitude row `mt-3`→`mt-2` (pairs the two sparklines as a unit) +
  thesis `mt-3`→`mt-4` (the in-file `mt-4` regime-chip precedent).
  Nit-3 subsumed by the Important fix. Empty/short zero-layout-shift,
  responsive, parity mechanics PASS.
- **accessibility-reviewer — 0 MUST-FIX ; SHOULD-FIX all PRE-EXISTING
  → existing backlog (flag-not-fix #11 / r106-a, NOT re-scoped).**
  WCAG 2.2 AA clean for what r113 introduces. 1.1.1 PASS (distinct
  meaningful aria-label, supplementary, two adjacent `role="img"`
  with distinct labels unambiguous to SR). 1.4.1 PASS (single neutral
  monochrome). 1.4.11 PASS (stroke ≈6.5:1 over `#0F1828`, reused
  unchanged). 2.3.3 PASS (opacity-only). Structure/reading-order
  PASS. 1.4.3 — the `text-[10px] --color-text-muted` tail ≈3.4–3.6:1
  is the PRE-EXISTING header-wide pattern (already §T4.2 backlog),
  r113 reuses verbatim and does NOT worsen it ; the ui-designer
  Important fix incidentally _improves_ the load-bearing differentiator
  word to ≈6.5:1 without re-scoping the backlog. Pre-existing r112
  `Sparkline.tsx` SR double-announce noted → same a11y backlog, NOT a
  r113 regression.

## Verification — build gate / deploy / real-prod witness (MEASURED)

- **Build gate** (re-run post-review-apply on the committed shape,
  doctrine #14): `tsc --noEmit` **0** · `eslint --max-warnings 0`
  (BriefingHeader.tsx + page.tsx + microchart.test.ts) **0** · vitest
  **7 files / 127 tests pass** (r112 baseline 124 + 3 new r113 = 127,
  zero regression) · `next build` **OK** — the local Windows first
  run hit a transient `Collecting build traces` ENOENT on
  `_not-found/page.js.nft.json` (a Windows file-lock artifact in a
  route r113 never touches ; static-gen 38/38 ✓, tsc/eslint/vitest
  all green) ; a non-destructive re-run on the unchanged tree
  succeeded (lesson #13 — env artifact, not a r113 defect) ; the
  Hetzner **Linux** deploy build (the authoritative one) is clean.
- **Deploy**: `redeploy-web2.sh` additive — Hetzner Linux build clean
  (no `.nft.json` ENOENT — confirms #13), `local=200 public=200`,
  `DEPLOY OK`, LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel NOT restarted, legacy 3030 untouched), no SSH throttle.
- **Real-prod witness** — Playwright on the deployed public
  `/briefing/EUR_USD` (doctrine #7 ; REAL data, REAL asset). The
  `BriefingHeader` renders TWO `role="img"` `<Sparkline>` SVGs:
  (1) r112 price UNCHANGED (no regression) — 90 points, viewBox
  `0 0 160 36`, svg-owns-box, neutral stroke, `first=2.0,9.1`
  `last=158.0,21.9`, allOneDp/strictlyIncX/inViewBox ✓,
  title===aria-label ✓ ; (2) NEW r113 amplitude — aria-label
  "Amplitude intrajournalière (haut−bas) EUR/USD, 90 dernières
  barres", **90 real `high − low` points**, viewBox `0 0 160 36`,
  svg-owns-box, **the SAME neutral `var(--color-text-secondary)`
  stroke as the price chart (no per-series tinting — ADR-017
  VERIFIED-TRUE confirmed live)**, endpoints exact (`x[0]=2.0`,
  `x[89]=158.0`), **allOneDp ✓ strictlyIncX ✓ inViewBox ✓**
  (genuine point-to-point `xLinear` — the SSOT composition),
  title===aria-label ✓. The two promoted lead words ("Prix" /
  "Amplitude") render in the `font-medium text-secondary` eye-lock
  token (the ui-designer Important fix, live-confirmed).
  **`priceVsAmplitudeIdenticalPoints = false`** — price
  (`2.0,9.1→158.0,21.9`) vs amplitude (`2.0,31.8→158.0,14.4`) are
  GENUINELY DISTINCT series: empirical proof r113 is NOT an on-screen
  duplicate (the anti-pattern the r112 reshape avoided) but a real
  distinct data dimension from real prod data —
  **SHIPPED≠FUNCTIONAL empirically avoided, not asserted**.
  Screenshot captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO
  fabricated causation, NOT over-claimed on the up-side)**: exactly
  **1 error: `favicon.ico` 404** — a PRE-EXISTING trivial app-wide
  404 already on the hygiene backlog / the r111 spawn-task, NOT
  r113's. The r111-witnessed PRE-EXISTING app-wide defects
  (vendor-chunk `TypeError ×9`, React #418, `/` CSP `localhost:8001`)
  were NOT observed on this load (load/timing-dependent — the
  r109/r112 "warm" precedent). **r113 is purely additive — it
  NEITHER caused NOR fixed any console defect** ; the r111 spawn-task
  - the r112-flagged §T4.2 backlog remain the owners (NOT re-scoped,
    NOT re-claimed as a r113 win — a witnessed near-clean console is
    not the increment that fixes a pre-existing defect it never
    touched). The r113 surface itself emits zero r113-related console
    output.

## NEW r113 lesson

When the prior round's binding default offers a MENU of candidates
(here: (A) regime-timeline vs (B) more Sparkline consumers), the
meta-r110/r112 "the default is itself R59-subject" applies to the
_menu selection itself_ : R59 must DISPROVE-or-CONFIRM each candidate
against real projected-AND-populated data BEFORE picking — picking (A)
because it sounds higher-value, without first proving its data exists,
would have shipped a fake-SSOT frieze (no regime time-series is
projected — the #1 Pydantic-projection trap). The honest increment is
the candidate the data supports (B, R53-verified), and the disproof of
(A) is itself recorded as a verified part of the round (not silently
dropped — lesson #11 ledger). A second, distinct genuine SSOT consumer
must also be proven NOT an on-screen duplicate of an existing series
(the r112 reshape concern) — here empirically, via
`priceVsAmplitudeIdenticalPoints = false` on real prod data, not
asserted.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR ; doctrine #8 "more coverage" (a NEW genuine SSOT consumer + a NEW
distinct data dimension), explicitly NOT de-accumulation (closed at
r111) ; the literal default (A) regime-timeline R59-DISPROVED on the
briefing page → reshaped to (B), the honest meta-r110/r112 move.
