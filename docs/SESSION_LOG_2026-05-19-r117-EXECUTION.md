# SESSION_LOG 2026-05-19 — r117 EXECUTION

**ADR-099 §D-3 Tier 4 — a 2nd `<BarSeries>` consumer on
`/hourly-volatility/[asset]`: the `p75_bp` upper-quartile
intraday-volatility envelope (doctrine #8 PURE "more coverage" — a NEW
genuine consumer of the r116 generic SSOT `<BarSeries>` for a NEW
DISTINCT proven-live series ; NOT a doctrine-#9 site, no scalar
migration). The (D) yield-curve `CurveChart` candidate was
R59-DISPROVED-as-viable (a genuine log-x trap — recorded,
flagged-not-forced, meta-r110).** Branch `claude/friendly-fermi-2fff71`,
continued post-r116b (Eliot `continue` overrode `/clear` — lesson #17,
context-frugal ; this conversation ran r113 + r116b + r117 + 3
concordance audits). Voie D + ADR-017 held (pure descriptive
volatility-envelope geometry, no signal) ; ZERO backend / ZERO
migration (alembic 0050) ; NO new ADR (doctrine #9 — dated
`## Implementation (r117)` append after §Impl(r116b), the §Impl headers
RE-GREP'd immediately before the append — the r116 lesson).

## Continuity / concurrency (verified — r117-start RE-GREP, the r116 lesson)

At r117-start the live battery + a RE-GREP of the §Impl headers
confirmed: HEAD == origin/branch == `b95a563` (r116b, unchanged), 82
ahead origin/main, §Impl headers all UNIQUE (r113/r114/r115/r116a/
r116b — the YELLOW-1 disambiguation held), NO new concurrent commit,
NO duplicate, branch STABLE, the r111-spawn-task DONE. Concurrency
fully resolved. (One ADR Edit-precondition failed once mid-round —
ground-truthed as a benign Read-tool-vs-Bash-tail tracking artifact,
NOT a content change [§Impl headers/wc/tail all byte-identical, no
git/concurrency movement] ; re-Read + re-applied the identical append.)

## R59-first — the menu-default is itself R59-subject (meta-r110/r112/r113/r116)

A read-only researcher R59 evaluated (D) yield-curve `CurveChart` fix /
(B′) more consumers / (E) hourly-vol-on-briefing / T4.2. **(D)
R59-DISPROVED-as-viable**: `app/yield-curve/page.tsx:149-152` is a
GENUINE log-x map (`(log(x+0.01)−log(xMin+0.01))/(log(xMax)−…)`,
self-labels "log-x tenor") + `:147-148` a non-zero/truncated y-baseline
(`yMin=min−0.1`). The r105 SSOT has NO log primitive
(`microchart.ts:42-44` `linScale` is linear-only) ; a faithful
migration would require inventing a NEW log-scale coord primitive =
new coord-math = exactly the **r110-class forced-bad-migration the
project rejects** → (D) DEFERRED flagged-not-forced (the yield-curve
truncated-axis + out-of-SSOT coord-math stays an honest backlog item ;
the disproof itself is a verified part of this round, ledger #11,
meta-r110 "an accurate skip beats a forced bad migration"). (E) = HIGH
SHIPPED≠FUNCTIONAL risk (NEW briefing SSR fetch, redundant). (T4.2) =
non-defects/speculative. **(B′) is the R59-sound pick**:
`HourlyVolEntry.p75_bp` (`lib/api.ts:1074`, directly re-verified) — a
DISTINCT proven-live series ALREADY fetched by the
`/hourly-volatility/[asset]` page (the SAME `HourlyVolOut` the r116
`<BarSeries>` consumes for `median_bp`) but until r117 rendered ONLY as
per-bar `<title>` tooltip text, NEVER charted.

## R53 live-verified (the SHIPPED≠FUNCTIONAL gate, ONE consolidated SSH)

`/v1/hourly-volatility/{EUR_USD,XAU_USD}?window_days=30`: `p75_bp`
24/24 populated — EUR_USD 0.6→1.28 (median 0.34→0.77), XAU_USD
0.03→6.35 (median 0.0→3.8) ; `p75 ≥ median` for ALL 24/24 on BOTH
assets (the statistical invariant) ; **p75 GENUINELY DISTINCT from
median — 0/24 identical on BOTH assets, max(p75−median)=0.52 (EUR) /
2.55 (XAU)** (the per-hour p75/median ratio varies — that IS the new
information : median = the typical hourly rhythm, p75 = the
upper-quartile "how big the busy hours get" envelope, pre-session
risk-calibration relevant). Series projected AND populated AND
non-degenerate AND empirically NOT-a-duplicate of the r116 median
chart — SHIPPED≠FUNCTIONAL avoided BY CONSTRUCTION (same page, same
fetch, same proven-rendering `<BarSeries>`, just a 2nd distinct
series).

## What r117 implemented

1. **`apps/web2/app/hourly-volatility/[asset]/page.tsx`** — a NEW
   `Percentile75Bars` section (between the r116 `HeatmapBars` and
   `SessionAverages`) rendering a 2nd `<BarSeries>` fed
   `entries[].p75_bp`, `max`=max p75 over populated, a SINGLE uniform
   neutral tone (the `<BarSeries>` documented `defaultFill`
   **`var(--color-text-secondary)`** — the ui-designer Important-1
   review removed an initially-drafted `var(--color-accent-cobalt)`
   override because that is the median chart's own normal-bar token,
   so the two stacked bodies were pixel-identical ; the neutral default
   is distinct-from-median, a11y-stronger, ADR-017-most-neutral), NO
   `tones`/`strokes` (no best/worst — a median-only backend construct),
   factual `aria-label` + per-bar `<title>` + a 24-hour `aria-hidden`
   gap-removed label row (the r116 alignment idiom) + a distinct
   `<h2>` (`mb-3` rhythm-parity, ui-designer Important-2) + a tightened
   single-clause factual descriptor (clarity by structure, ADR-017
   #11 ; ui-designer Nit-3). FAIL-SAFE `return null` when no populated
   data (the r116 `HeatmapBars` carries the single user message — no
   double "insufficient"). `SessionAverages` + the r116 median
   `HeatmapBars` byte-untouched (ichor-trader-verified). The file-
   header docstring rewritten to name both charts (ichor-trader
   YELLOW-1, the r101/r103 stale-docstring drift class).
2. **`apps/web2/__tests__/microchart.test.ts`** — additive describe
   block (3 tests) PINNING the r117 p75 CONSUMER contract (NOT
   byte-identical-vs-prior — a NEW consumer): the `p75_bp` derivation
   ≥ 0 AND ≥ median pointwise (the statistical invariant) ; p75 ≠
   median pointwise (the empirical not-a-duplicate property at the
   data level, the r113 discipline) ; the p75 series is a well-formed
   SSOT-composed `<BarSeries>` input (`bandLayout`/`barFromBaseline`/
   `svgCoord`, 1-dp, in-viewBox, TRUE 0-baseline, max bar tops the
   0.92 fill band). Pre-existing tests unchanged (zero regression).
3. **ADR-099 `## Implementation (r117, 2026-05-19)`** — dated §Impl,
   NO new ADR (doctrine #9), appended after §Impl(r116b) (headers
   RE-GREP'd first — the r116 lesson). Reviews/Verification placeholders
   RECONCILED to MEASURED (lesson #1 — no forecast).

## Honest scope / ledger (#11, NOT thinned)

r117 = ONE NEW genuine `<BarSeries>` consumer (p75 envelope) + 3
contract tests + the consolidated review fixes. PURE "more coverage"
(doctrine #8) — NOT a #9 migration (no scalar ; the doctrine-#9 ledger
`{VolumePanel r105·ScenariosPanel r108·confluence-history r109·I3
r111·HeatmapBars r116}` UNCHANGED). DEFERRED, NOT thinned: **(D) the
`yield-curve` `CurveChart`** log-x + truncated-y + out-of-SSOT
coord-math — a REAL design-integrity gap that needs a sanctioned NEW
log-scale primitive ADR or a deliberate re-scope, NOT a forced
migration (R59-disproved-as-r117-viable, recorded — meta-r110) ; (E)
hourly-vol on the PRIMARY briefing page (NEW fetch wiring + own R59,
separate increment) ; further consumers ; the regime-timeline (still
DEFERRED — needs a NEW backend regime-TIME-series projection, the #1
class) ; T4.2 (`prefers-reduced-motion` already clean — uncertainty-
band / calibration-overlay / degraded+empty remain) → T4.3.
PRE-EXISTING, NOT r117's, NOT re-scoped (flag-not-fix #11): the
r111-spawn-task's r114/r115/r116a (ITS domain) ; the §T4.2
header/label `text-muted` ≈4.0:1 contrast (a11y SHOULD-1, all 3
sibling `<h2>` share it) ; the `<BarSeries>` `aria-label`+child-
`<title>` SR double-announce (r116-origin component-level, a11y
SHOULD-2 = the r113-flagged backlog).

## Reviews (consolidated single pass — doctrine #14 ; all 3 dispatched, verdicts MEASURED not forecast lesson #1)

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only)
  APPLIED.** (1) doctrine-#8 pure-coverage CORRECT (zero coord math,
  `maxP75` is a domain-max not a `(v/max)*100` map, ledger unchanged) ;
  (2) the (D) R59-disproof HONEST not work-avoidance (exact anchors,
  meta-r110 codified, r117 ships a genuine alternative) ; (3) ADR-017
  CLEAN (grep `BUY|SELL|order|…`=ZERO, uniform-neutral tone, factual
  prose). YELLOW-1 (stale `page.tsx:1-5` header docstring) APPLIED.
  Reconcile-not-blindly: ichor-trader reviewed the cobalt draft ; the
  ADR-017 ruling is token-agnostic re uniform-neutral and holds
  _a fortiori_ for the more-neutral `text-secondary` the ui-designer
  Important-1 shipped.
- **ui-designer — MERGE-with-changes, 0 Critical ; 2 Important + 1 Nit
  APPLIED.** Important-1 (the p75 fill = the median's own normal-bar
  cobalt → bodies pixel-identical) → `defaultFill` override removed,
  falls back to the BarSeries neutral default `text-secondary` —
  unmistakably distinct from the median chart. Important-2 (p75 `<h2>`
  no-margin vs median's `mb-4`) → `mb-3` + redundant descriptor `mt-1`
  dropped — section headers now share rhythm. Nit-3 (descriptor
  semicolon-nested mini-méthodologie) → single-clause tighten.
  Confirmed-good: BarSeries contract unchanged, no best/worst legend
  correct, responsive + house-style consistent, empty/short FAIL-SAFE
  verified.
- **accessibility-reviewer — 0 MUST-FIX ; 2 SHOULD-FIX both
  PRE-EXISTING → backlog (flag-not-fix #11, NOT re-scoped).** Central
  ruling: **the single-uniform-tone p75 chart has NO 1.4.1 colour
  concern — BY CONSTRUCTION** (no `tones`/`strokes` ⇒ one fill ⇒ zero
  info encoded by colour). 1.4.11 PASS (uniform fill ≥3:1 over surface
  — re-confirmed for the `text-secondary` Important-1 token at the
  witness). 1.1.1 / 2.3.3 / heading-structure PASS. SHOULD-FIX (a) the
  `<h2>` `text-muted` ≈4.0:1 = the repo-wide §T4.2 backlog on all 3
  sibling headings, NOT r117-introduced ; (b) the `<BarSeries>`
  `aria-label`+`<title>` double-announce = r116-origin component-level
  backlog. Both flag-not-fix #11.

## Verification (real numbers — measured on deployed prod, not forecast)

- **Build gate** (re-run post-review-apply, doctrine #14): tsc **0** ·
  eslint **0** (page.tsx + microchart.test.ts) · vitest **7 files /
  132 tests** (r116 baseline 129 + 3 new r117, zero regression) ·
  `next build` **OK**.
- **Deploy**: `redeploy-web2.sh` additive — Linux build clean,
  `local=200 public=200`, `DEPLOY OK`, LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel not restarted, legacy 3030 untouched), no SSH throttle.
- **Real-prod witness** — Playwright deployed public
  `/hourly-volatility/EUR_USD` (doctrine #7, REAL data, REAL asset):
  TWO `role="img"` `<BarSeries>` SVGs. The r116 median chart
  **BYTE-UNCHANGED — no regression** (24 rects, `[cobalt,bear,bull]`,
  2 stroked extremes, aria "…pic 13:00, creux 02:00"). The NEW r117
  p75 chart: 24 rects, viewBox `0 0 480 128`, **distinctFills =
  [`var(--color-text-secondary)`] — SINGLE uniform neutral (the
  ui-designer Important-1 token LIVE-confirmed, NOT the median's
  cobalt)**, strokedCount = 0, every coord 1-dp, in-viewBox, **TRUE
  0-baseline empirically confirmed** (y+h reaches the 128 baseline —
  the SSOT invariant, not asserted), factual ADR-017-neutral
  aria-label. **`pVsM_identicalYVectors = false`** — the p75 and
  median bar y-vectors RENDER GENUINELY DIFFERENT (median first/lastY
  62.2/76.0 vs p75 49.8/57.2 — p75 bars taller because p75 ≥ median ;
  empirical proof NOT an on-screen duplicate, the r113 discipline on
  rendered prod coords). Headings render structurally distinct.
  Screenshot captured.
- **Console — honestly scoped (lesson #1/#11/r106-a)**: the r117
  surface `/hourly-volatility/EUR_USD` showed **0 errors / 0
  warnings** this load (zero r117-related console output). The
  r111-flagged PRE-EXISTING app-wide defects are on OTHER routes,
  NOT this surface, NOT r117's ; the spawn-task's r114/r115/r116a
  fixes (on origin as ancestors via the r116b push, carried to prod
  by this deploy chain) are the spawn-task's to verify, NOT
  re-claimed (causation ≠ proof — r117 purely additive, neither
  caused nor fixed them).

## NEW r117 lesson

When the prior round's binding default offers a candidate that _sounds_
like the highest-integrity pick (here (D): fixing a genuinely
truncated-axis misleading chart), the meta-r110 discipline still
applies — R59 must verify it can be done HONESTLY before committing.
(D) was a real defect but a faithful SSOT migration was IMPOSSIBLE
without inventing a new log-scale primitive (the r110-class
forced-bad-migration). The honest move is to RECORD the disproof as a
verified increment, DEFER (D) flagged-not-forced (it needs its own
sanctioned-primitive ADR or a re-scope), and ship the R59-sound
alternative (B′ p75) — an accurate "skip + a real alternative" beats
forcing the higher-sounding one into a bad migration. Also: a 2nd
consumer of an existing component must be proven NOT a duplicate at
BOTH the data level (R53: 0/24 identical) AND the rendered level
(witness: `pVsM_identicalYVectors=false`), and the "make it visually
distinct" review fix must use a token genuinely distinct from the
sibling chart's own palette — not that chart's own normal-bar token
(the ui-designer Important-1 catch).

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR ; doctrine #8 PURE "more coverage" (NOT a #9 ledger change) ; (D)
yield-curve R59-DISPROVED-as-r117-viable (a genuine log-x trap — an
accurate flagged-not-forced skip, the disproof a verified increment
per meta-r110).
