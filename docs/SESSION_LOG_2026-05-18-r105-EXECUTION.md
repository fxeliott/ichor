# SESSION_LOG 2026-05-18 — r105 EXECUTION (ADR-099 Tier 4 increment 2 — the microchart SSOT foundation ; doctrine-#9 anti-accumulation, byte-identical)

**Round type:** ADR-099 §D-3 Tier 4 (premium UI), the r104-close binding
default (no pivot, doctrine #10). The r104 close recommended `/clear`;
Eliot replied `continue` (override). Per lesson #17 + the r101 precedent:
honored context-frugally, scoped to the **R53-safe slice**, `/clear` NOT
re-proposed.

**Honest scope (the deliberate context-frugal slice for a deep session).**
r105 = the **microchart SSOT foundation only** — NOT the 4 visible
primitives. A pure-function extraction provably byte-identical has zero
token/data/visual hallucination surface; a multi-primitive build in an
already-deep session would be the degradation the standing prompt forbids.
The 4 primitives + the `--p-chart-*` ramp are announced, consumer-backed
increments (r106+). No new visible UI this round = correct anti-accumulation
foundation, honestly scoped (not optics).

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API.** Frontend
web2-only, additive Hetzner deploy, **ZERO backend / ZERO migration**.
ADR-017 N/A by construction (pure geometry) — ichor-trader R28 confirmed
exhaustively.

## R59 reshaped the plan (doctrine #3 — caught before code)

- ONE consolidated read-only SSH (R53 — live re-verify, not the r104 cache)
  confirmed all 4 microchart data sources have real, populated prod shapes
  (`/v1/correlations` 8×8 matrix · `/v1/scenarios/{a}` 3 scenarios ·
  `/v1/market/intraday/{a}` 479 OHLCV bars · `/v1/sessions/{a}` 20-card
  regime history) — zero backend work needed for any future primitive.
- The anti-doublon navigator found: **no shared microchart SSOT exists** —
  3 hand-rolled DUPLICATE coordinate-math impls (`VolumePanel` slot/volH,
  `app/confluence/history` xAt/yAt, `regime-quadrant` pathFromHistory) =
  the exact doctrine-#9 accumulation r105 must resolve ; `CorrelationsStrip`
  (r82) / `ScenariosPanel` already render diverging-bar / ladder forms →
  those primitives must **EXTEND**, never duplicate ; the "RSC-clean"
  wording is half-true (the panels are `"use client"` for motion) → the
  SSOT must be a **pure plain module** consumed by client panels
  (doctrine-#5 split).

## What r105 implemented

1. **NEW `apps/web2/lib/microchart.ts`** — pure, RSC-safe, zero-dependency
   SSOT: `svgCoord` (1-dp formatting authority), `linScale` / `xLinear`
   (canonical linear-scale base — added per ui-designer C1), `bandLayout`,
   `barFromBaseline` (0-baseline, no truncated axis — fail-loud enforced,
   I2), `bandSeriesPolyline` (band-coupled VolumePanel helper, N4). No
   `"use client"`/React; `Math`+string only (the `lib/verdict.ts` idiom).
2. **`VolumePanel.tsx` refactored** onto the SSOT — render byte-identical
   (unused `pMin/pMax/pSpan` removed; geometry → SSOT; bar map →
   `barFromBaseline`).
3. **NEW `__tests__/microchart.test.ts`** — the byte-identical proof: the
   test **embeds the verbatim pre-r105 VolumePanel inline expressions** and
   asserts exact string / deep equality (realistic + edge fixtures:
   equal-closes span-fallback, n=2, large values) + specs pinning the
   `linScale`/`xLinear` primitives and the `barFromBaseline` guard.
4. **`components/ui/regime-quadrant.tsx:14-15`** stale "Phase A peut migrer
   sur d3" tech-debt note retired (r105's zero-dep mandate forecloses d3;
   replaced with the SSOT-migration pointer — prompt-decomposer + navigator
   flag #3).
5. **ADR-099 `## Implementation (r105, 2026-05-18)`** dated append — no new
   ADR (doctrine #9, ADR-099 §D-3 Tier 4 is the spec) — incl. the honest
   foundation-only scope, the deferred consumer-backed split, and the
   Review-fixes record.

## Review pair (consolidated, single atomic apply pass)

- **ichor-trader R28: 4 GREEN + 1 doc-only YELLOW.** ADR-017 / Voie D N/A
  exhaustive ; framework axes (VPIN/GEX/dollar-smile/macro/FX-peg/Tetlock/
  conviction/source-stamp) N/A exhaustive ; over-claim GREEN
  (foundation-only honestly stated, not rounded up) ; **byte-identical
  three-way agreement VERIFIED** (SSOT ≡ test `old*` verbatim ≡ VolumePanel
  call-site ; float order identical ; the `,1` maxVol floor correctly at
  the call site, not in the lib). **YELLOW-1 applied**: the
  `lib/microchart.ts` header was present-tense "is DUPLICATED 3×" but
  r105's own change made VolumePanel no longer a duplicate (2 still-inline)
  → rewritten past-tense ("the math **was** DUPLICATED … r105 migrates
  VolumePanel … the remaining two follow"). The ADR R59-finding text is
  correctly historic, no edit (ichor-trader-cleared).
- **ui-designer: C1 (Critical) applied.** My first SSOT generalized only
  _VolumePanel's_ band case; the announced r106 consumers (confluence-
  history xAt/yAt, sparkline, regime timeline, proportional ladder/heat-
  strip scalars) need a **linear scale** — omitting it would force an r106
  SSOT retrofit = the doctrine-#9 outcome to forbid. Reconcile-not-blindly
  (the r96 lesson): the reviewer's concrete file:line evidence overrode my
  YAGNI instinct — `linScale`/`xLinear` are the canonical base with 3+
  named consumers, non-speculative. **I2 applied** (fail-loud
  `barFromBaseline` guard — truncation attempt throws at the SSOT, not
  silently at pixels ; VolumePanel inputs never trip it ⇒ byte-identical
  preserved). **N4 applied** (`seriesPolyline` → `bandSeriesPolyline`).
  **I3 deferred with reason** (recomposing `bandSeriesPolyline` atop
  `linScale` = a float-order byte-identical _risk_ for zero r105 consumer ;
  done at the confluence-history migration r106+ with a re-proven gate).
- **accessibility-reviewer: N/A-with-reason** — the VolumePanel render is
  proven byte-identical, so DOM/colours/contrast are definitionally
  unchanged. MANDATORY at the r106 heat-strip's _new_ colour-encoding.

All applied items preserve byte-identity by construction: `linScale`/
`xLinear` are additive (VolumePanel doesn't call them) ; the rename is
impl-unchanged ; the guard is unreachable for VolumePanel's inputs.

## Verification (re-run on the post-review consolidated shape, doctrine #14)

- **vitest 6 files / 84 tests** (r104 baseline 5/68 + `microchart.test.ts`
  16 = 9 verbatim-embedded byte-identical assertions [**stayed green on the
  renamed `bandSeriesPolyline` ⇒ the consolidated review fixes preserved
  byte-identity, proven**] + 7 `linScale`/`xLinear`/guard specs).
- `tsc --noEmit` 0 + `eslint --max-warnings 0` 0 + `next build` OK.
- Deploy: vetted additive `redeploy-web2.sh` (server build, restart
  `ichor-web2` only — LIVE URL stable r75, legacy 3030 untouched ;
  local=200 public=200).
- **Real-prod witness** (deployed `/briefing/EUR_USD`, Playwright): the
  SSOT-refactored VolumePanel renders a real SVG chart from live prod data
  — viewBox `0 0 640 150`, 90 volume rects + 90-point price polyline +
  baseline, **every coordinate a well-formed 1-dp pair** (the
  `svgCoord`/`bandSeriesPolyline`/`barFromBaseline` SSOT contract holds
  end-to-end on prod), bar fill = `oklch(0.7106 0.1661 22.22)` = r104's
  `--color-bear` (r104 OKLCH + r105 SSOT working together). Visual
  screenshot: page premium/coherent, zero breakage. Console: only the
  pre-existing `404 favicon.ico` (non-r105 — lesson #13 triaged).

## Net

Pure doctrine-#9 anti-accumulation: the reusable, fail-loud, byte-identical-
proven SSOT every future microchart primitive builds on. `VolumePanel`
migrated (1 of 3 dup sites collapsed). Emission/visual-neutral vs pre-r105.

## Lessons

- Reinforced **#17** (Eliot overrides `/clear` → context-frugal R53-safe
  slice, no re-propose) + **#9** (extract-to-SSOT + prove byte-identical,
  the r71 pattern sharpened to _verbatim-embedded exact-string_ assertions
  — stronger than DOM-length).
- Reinforced the **r96 reconcile-not-blindly-apply**: a reviewer's
  concrete-evidence **Critical** (ui-designer C1) overrode my deliberate
  YAGNI scoping — `linScale` was foundational, not speculative.
- **NEW:** a "SSOT" scoped to a single consumer's specifics is a
  _fake-SSOT_ — a genuine foundation must expose the general primitive its
  _announced next consumers_ need, or the next round retrofits it = the
  accumulation doctrine #9 forbids (the same anti-pattern as r104's
  "ramp without a consumer", one layer up).

## Default sans pivot → r106

**ADR-099 Tier 4 increment 3 = the correlation heat-strip** = **extend**
`CorrelationsStrip` (r82, anti-doublon — NOT a new file) into a colored-cell
heat encoding + ship the **`--p-chart-div-*` OKLCH diverging ramp it
consumes** (consumer-backed — the r104 tree-shake lesson applied
proactively) on the r105 SSOT. accessibility-reviewer MANDATORY (new
colour-encoding ; CVD/triple-signal per SPEC §14). R59-first against the
live `/v1/correlations` 8×8 matrix (re-verified this round). Then ladder
(extend ScenariosPanel) / sparkline / regime-timeline / the confluence+
regime-quadrant SSOT migrations (with I3). Session DEEP (full r104 + r105
incl. 2 multi-deploy rounds, ~13 sub-agents) — **`/clear` STRONGLY
RECOMMENDED before r106** ; pickup v26 + SESSION_LOG r95→r105 = the
zero-loss anchor.
