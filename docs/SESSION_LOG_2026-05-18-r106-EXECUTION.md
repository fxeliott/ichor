# SESSION_LOG 2026-05-18 — r106 EXECUTION

**ADR-099 §D-3 Tier 4 increment 3 — the correlation heat-strip.**
Branch `claude/friendly-fermi-2fff71`. Binding r105-close default executed
verbatim (doctrine #10, no pivot). Voie D + ADR-017 held; web2-only
additive deploy; ZERO backend / ZERO migration (alembic still 0050).

## What shipped

- **`apps/web2/app/globals.css`** — NEW Layer-1 `--p-chartdiv-{50,200,350,500,650,800,950}`
  OKLCH diverging primitives + Layer-2 `--color-chart-div-{neg-strong,
neg-mid,neg-weak,neutral,pos-weak,pos-mid,pos-strong}` semantic
  (r104 two-layer convention). Constant **L=0.72** (magnitude via
  chroma+hue, never lightness — no bar-length confound, a11y-upheld).
  **Symmetric |C|** both poles: `C_STRONG=0.155` = max chroma in sRGB
  gamut common to H25° (bear) & H163.22° (bull) at L0.72 (ui-designer
  UD-2). Each value the exact CSS Color 4 OKLCH coord (pure-Python
  Ottosson reference, self-checked: round-trips r104's verified
  `#F87171 → oklch(0.7106 0.1661 22.22)` exactly). Header §2 hygiene note
  updated. Consumer-backed (every token referenced this round).
- **`apps/web2/lib/correlationHeat.ts`** (NEW, pure RSC-safe — doctrine #5
  / r96 `dataIntegrity.ts` idiom): `DIV_STOPS`, `divergingStop` (ρ→token,
  **signed-offset symmetric** composition of the r105 SSOT `linScale(0,1,
0,_CENTER)`, `_CENTER=(N−1)/2`, clamp [-1,1]), `trendGlyph` (▲/▼/◆),
  `NEAR_ZERO=0.05`. Unit-testable without pulling `motion/react` (r105
  lesson).
- **`apps/web2/components/briefing/CorrelationsStrip.tsx`** — extended in
  place (anti-doublon #9, NOT a new file): SSR SVG heat-strip row
  (`bandLayout`/`svgCoord` SSOT geometry, rect fill = ρ→`--color-chart-div-*`
  inline `var()`) ; `aria-hidden` decorative (ADV-2) ; HTML `flex-1`
  glyph overlay (UD-1 — SVG `<text>` would smear under
  `preserveAspectRatio="none"`) ; the labelled `<ul>` is the single
  authoritative SR source, bar recolored to the ramp + `opacity-90` (UD
  nit) ; `▲`/`▼`/`◆` glyph added → SPEC §14-row3 closed (quintuple
  signal) ; in-component ADR-017 disclaimer ; legend re-pointed off binary
  bull/bear onto the ramp endpoints (IT-c).
- **`apps/web2/app/briefing/[asset]/page.tsx`** — minimal additive
  precedence fix (R59-reshape, see below).
- **`apps/web2/__tests__/correlationHeat.test.ts`** (NEW, 11 tests):
  anchors, symmetry, monotonicity, clamp, NaN→neutral, glyph/near-zero.
- **`docs/decisions/ADR-099-…md`** — dated `## Implementation (r106,
2026-05-18)` appended (NO new ADR, doctrine #9).

## Reviews (3 mandatory, parallel, consolidated 1-pass — all applied)

- **ichor-trader R28: 0 RED / 3 YELLOW.** IT-a (ΔsRGB=0 asserted-not-
  verified → resolved empirically: Ottosson self-check vs r104's `#F87171`
  = MATCH ⇒ CSS Color 4 reference confirmed, web converter is the
  outlier ; real per-stop + WCAG numbers in the ADR Verification) ; IT-b
  (literal `linScale(0,1,0,3)` → track `_CENTER=(N−1)/2`) ; IT-c (legend
  binary→ramp endpoints). GREEN: ADR-017, economic soundness, Voie D N/A,
  symmetry/monotonicity/clamp test-proven, doctrine-#9.
- **ui-designer: 3 Important + 2 nits.** UD-1 (SVG text smear → HTML
  overlay) ; UD-2 (asymmetric pole chroma → symmetric C_STRONG=0.155) ;
  UD-3 (label `truncate`+`title`) ; nits (bar `opacity-90` ; small-N
  docstring pin). Constant-L / token naming / extraction validated.
- **accessibility-reviewer (MANDATORY): 0 MUST-FIX / 0 SHOULD-FIX, PASS,
  3 ADVISORY.** ADV-1 (strip↔list coupling = docstring load-bearing
  invariant) ; ADV-2 (SVG `aria-hidden` decorative — no double-announce) ;
  ADV-3 (no `@media forced-colors` = pre-existing, N/A r106). Constant-L
  CVD choice explicitly upheld. Computed contrast all PASS.

## The witness reshaped scope twice (lesson #1 forecast≠preuve / #2 SHIPPED≠FUNCTIONAL)

1. **SHIPPED≠FUNCTIONAL.** First deployed witness: the heat-strip rendered
   on ZERO priority assets. `/v1/correlations` is LIVE+rich (8×8, n=257)
   but every priority card carries an empty `{}` `correlations_snapshot`,
   and the pre-existing r82 page precedence `cardCorr ?? liveCorrRow`
   pinned the truthy-but-empty object → `CorrelationsStrip` returned
   `null` everywhere. **Pre-existing r82 defect, not an r106 regression.**
   Minimal additive fix (`page.tsx`): a card snapshot counts only with ≥1
   numeric ρ entry, else treated absent → precedence falls through to the
   rich live `deriveCorrelationRow` (r69 dead-live-path-completion class ;
   `correlationSource` then honestly reads "Live …"). Re-gated, re-deployed.
2. **A pre-existing app-wide defect surfaced.** Second witness: legend +
   overlay glyph computed to slate-100 (not the intended colours). Ground
   truth (lesson #13, not theory): all 7 `--color-chart-div-*` + 7
   `--p-chartdiv-*` ARE in `:root` (NOT tree-shaken) — but **the Tailwind
   v4 `text-[--color-*]` bracket-arbitrary class produces no working
   colour rule app-wide** (proven identically on UNTOUCHED `page.tsx:242`
   caption + `:377` footer ; tokens defined but the bracket form doesn't
   apply ; v3-era syntax, v4 wants `text-(--x)`). r106's NEW colour-
   critical elements (overlay glyph, legend) re-pointed to inline `style`
   `var()` (the mechanism empirically proven this round — rect `fill` /
   bar `backgroundColor` resolve to exact OKLCH). The pre-existing
   app-wide issue is OUT OF SCOPE (codebase-wide, touches r104 tokens,
   own R59 + per-route visual-diff round) — flagged as a dedicated task,
   NOT silently rewritten, NOT claimed fixed (calibrated honesty #11).

## Final real-prod witness — GREEN (deployed public URL, live data)

`https://latino-superintendent-restoration-dealtime.trycloudflare.com/briefing/EUR_USD`
(stable URL, r75 fix held ; legacy 3030 untouched ; deploy clean, no
rollback): source "Live · fenêtre 30 j" ; 7 rects exact OKLCH live ramp ;
dark glyphs `oklch(0.1268 0.0141 254.03)` (a11y ≥7.59:1 restored) ; SVG
`aria-hidden` ; legend = the 3 ramp endpoints ; 7 `<ul>` rows real
correlations GBP/USD +0.77 ▲ … SPX500 +0.28 ▲ sorted by |ρ|, quintuple
signal ; ADR-017 footer ; console = only pre-existing 404 favicon.
Screenshot confirms the premium heat gestalt + non-smeared glyphs.

## Verification numbers

- OKLCH self-check: `#F87171 → oklch(0.7106 0.1661 22.22)` MATCH.
- Ramp (all in-gamut, round-trip ΔsRGB=0): neg-strong `0.155 25 #F67972`
  · neg-mid `0.1061 25 #DF8A83` · neg-weak `0.0572 25 #C69793` · neutral
  `0.019 256.79 #9DA5B1` · pos-weak `0.0572 163.22 #84B09B` · pos-mid
  `0.1061 163.22 #5FBA92` · pos-strong `0.155 163.22 #01C289`.
- WCAG: glyph #04070C on every stop ≥ **7.59:1** ; list value 15.85:1 ;
  legend endpoints 7.04 / 7.53 / 8.09:1 — all clear 1.4.3.
- Build gate (post-review, post-prettier shape, doctrine #14): `tsc` 0 ·
  `eslint --max-warnings 0` 0 · vitest **7 files / 95 tests** (r105 6/84
  - correlationHeat 11, zero regression) · `next build` OK.

## NEW lessons

- A frontend "ship" is not functional until a deployed witness shows it
  rendering from REAL data on a REAL asset — an empty-`{}` upstream +
  a truthy-fallback precedence can make a correct component render nothing
  everywhere (SHIPPED≠FUNCTIONAL, r69-class — the dead live path IS the
  task).
- A new colour encoding is the perfect probe for latent token/CSS-class
  defects: r106's vivid ramp exposed an app-wide Tailwind-v4
  `text-[--color-*]` regression that subtle dark-on-dark muted text had
  hidden for many rounds. The contract is what the BUILD APPLIES, not what
  the source class says (the r104 tree-shake lesson, one layer up — class
  syntax form, not just token emission).
