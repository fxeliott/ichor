# SESSION_LOG 2026-05-19 — r108 EXECUTION

**ADR-099 §D-3 Tier 4 increment 4 — the probability ladder onto the r105
`linScale` SSOT.** Branch `claude/friendly-fermi-2fff71`. Voie D + ADR-017
held; web2-only additive deploy; ZERO backend / ZERO migration (alembic
still 0050); NO new ADR (doctrine #9 — dated `## Implementation (r108)`
append to ADR-099).

## R59 — stale-prompt reconciliation (the live wins, doctrine #3)

The resume prompt was written at the r106 close and instructed
"continue ⇒ r107 = the probability ladder". **The live repo disproved
the premise**: HEAD was `e8776e9` (72 ahead origin/main), and
`e8776e9` = **r107 = the app-wide Tailwind v4 `[var(--*)]`
token-resolution fix** — a session in between took the r107 slot for the
r106-flagged dedicated task (correctly: it was the highest-value
non-ladder item). r107 was fully closed (committed + pushed +
`ADR-099 §Implementation(r107)` L814 + `SESSION_LOG_2026-05-18-r107` +
reviews trio GREEN + AFTER-witness). **So the ladder is r108, not r107**
(doctrine #10 — the Tier 4 multi-round split: the un-done increment is
next). Concordance battery (git log / origin sync / ADR grep /
SESSION_LOG read) — 0 ambiguity. Memory anchors gap also surfaced: the
r107-Tailwind session did NOT bump pickup v26 (still "r106 close") or
MEMORY.md (still "sync r106") — reconciled at this r108 close
(r106→r108, r107 captured accurately so the chain is not thinned).

## R59 — the SHIPPED≠FUNCTIONAL trap did NOT materialize (design reshaped)

The prime anticipated risk (the r106 lesson): an empty `card.scenarios`

- a truthy-fallback precedence ⇒ the ladder renders on zero assets,
  with the prompt instructing a live `/v1/scenarios/{a}` fallback. Real
  shapes, inspected first (`apps/web2/lib/api.ts` + live prod Playwright):

* `card.scenarios` = `Scenario[]` `{label(7-enum
crash_flush..melt_up), p, magnitude_pips:[lo,hi], mechanism}` —
  migration 0039, ADR-085 Pass-6, `[]` for legacy/pre-Pass-6 cards.
  `ScenariosPanel.tsx` (mounted `app/briefing/[asset]/page.tsx:296`,
  gated `{card && …}`) ALREADY renders it as a diverging probability
  ladder (bear/base/bull rows, `width ∝ p`, skew header, mechanism).
* **Live prod (`/v1/sessions/{a}?limit=1`): all 5 priority assets carry
  a fully populated 7-bucket `card.scenarios`** — EUR_USD `1750e73a`
  ny_mid, GBP_USD `c7bdd81c` ny_mid, XAU_USD `96f36fad` pre_londres,
  SPX500_USD `f544725b` ny_mid, NAS100_USD `61ee0bea` ny_mid (each
  `scenarios.length === 7`). The ladder is ALREADY functional on every
  priority asset via the existing path.
* `/v1/scenarios/{a}` = the **shape-incompatible** `ScenariosResponse`
  `scenarios: ScenarioRow[]` 3-kind (`continuation`/`reversal`/
  `sideways`, `probability`, `triggers[]`) — NOT the 7-bucket Pass-6
  distribution; `api.ts` wires NO `getScenarios()` client. (Live
  confirmed: EUR_USD n=3, GBP_USD n=3.)

⇒ **No live fallback shipped** (calibrated honesty #11): adding a
shape-wrong, unneeded fallback to satisfy a forecast-trap the real data
disproved would be over-engineering + a data-misrepresentation. R59
reshape > prompt.

## What r108 implemented (the honest atomic increment)

The doctrine-#9 anti-accumulation step the r105 SSOT was built for. The
ladder's ONE hand-rolled proportional scalar
`Math.max((s.p / maxP) * 100, 2)` is the 3rd hand-rolled coord-math
site; `microchart.ts:13-15` names "proportional ladder/heat-strip
scalars" as an announced `linScale` consumer → r108 makes it consume the
SSOT, validating the r105 foundation across a 2nd independent consumer
(the r105 fake-SSOT lesson: proven not-fake).

1. **`ScenariosPanel.tsx`** — `import { linScale } from "@/lib/microchart"`;
   `const pWidth = linScale(0, maxP, 0, 100)` built once per render (the
   r106 `divergingStop` compose idiom); per-row `Math.max(pWidth(s.p), 2)`.
   The `Math.max(_, 2)` min-visible-bar clamp kept inline (presentational,
   single-site — anti-over-extraction, r96 reconcile-not-blindly;
   `linScale` is the general primitive, the clamp is not — ui-designer
   confirmed). `maxP = Math.max(…, 0.01)` floor unchanged (guarantees
   `linScale` span ≠ 0).
2. **`__tests__/microchart.test.ts`** — a new describe block (the r105
   embedded-verbatim idiom): verbatim pre-r108 `(p/maxP)*100` + the
   end-to-end `Math.max(_,2)` composition asserted equal to the
   `linScale` form to 9 decimals, exact `===` only at `p=0`, across a
   realistic 7-bucket + edges (`p=maxP`, clamp, `maxP=0.01` floor).
3. **Docstring + ADR §Impl(r108)** — record the migration, doctrine-#9
   rationale, the honesty disclosure, and the R59 finding.

### Numerical honesty (the central point — NOT byte-identical)

`linScale(0, maxP, 0, 100)(p)` = `p*(100/maxP)` (the r105 SSOT's fixed
`rangeMin + (v-domainMin)*k` form), whereas pre-r108 was `(p/maxP)*100`.
SAME real number, DIFFERENT IEEE754 multiply order → ≤ 1 ULP
(≤ ~4e-14 absolute on [0,100], ~1.4e-14 relative at ≈100 — far below any
sub-pixel / CSS-serialized threshold), NOT bit-identical. This is exactly
the "float-order risk" r105 flagged when it deferred the I3
`bandSeriesPolyline`-atop-`linScale` re-expression; r108 is the first
genuine `linScale`-replaces-an-existing-inline consumer, so the
equivalence is re-proven HERE at full double precision, the multiply-order
delta DISCLOSED, NOT over-claimed as "byte-identical" (the r105/r106
byte-identical precedent does NOT transfer — those were same-order
extractions; this is a scale-primitive substitution). Lesson #1 / #11.

## Honest non-atomic scope (deferred, flagged not thinned)

r108 = the `linScale` SSOT migration of the ladder scalar ONLY. Deferred:
(i) **the Tier 4 SSOT-migration ledger carried forward in full from
r105, NOT thinned** (doctrine #11) — the r105 **I3**
`bandSeriesPolyline`-atop-`linScale`, `confluence-history` `xAt/yAt`,
`regime-quadrant` `pathFromHistory` (each its own future increment
re-proving equivalence at its gate); the non-Tier-4 r107-deferred items
(`globals.css` §5 border-α §1.4.11, `NarrativeBlocks` `/10` chip) remain
tracked under §Impl(r107)/ADR-099 residuals — orthogonal, not dropped;
(ii) any visual/structural ladder redesign (the ladder is already
polished + ADR-017-clean — a rebuild = accumulation/regression risk for
marginal gain, not atomic); (iii) the `SentimentPanel`↔`ScenariosPanel`
empty-state text-tier inconsistency (the r107-deferred cross-panel
convention).

## Reviews (consolidated 1-pass, doctrine #14)

- **ui-designer — APPROVE, 0 Critical / 0 Important / 2 non-blocking
  nits** (docstring density + call-site comment; both explicitly
  not-to-apply, defensible per the float-order-honesty doctrine). SSOT
  closure idiom confirmed correct; clamp-inline confirmed correct;
  visually inert confirmed.
- **ichor-trader R28 — GREEN to merge, 0 RED, 2 YELLOW (doc/comment-only,
  APPLIED)**. ADR-017 intact; numerical-honesty framing "the strongest
  part of this change"; math independently re-derived; R59 honesty
  correctly scoped; no cross-file drift. **YELLOW-1 applied**:
  `microchart.ts:13-17` → `13-15` (3×: docstring, inline comment, ADR)
  — the linScale-consumer sentence ends L15. **YELLOW-2 applied**:
  Deferred (i) reworded into an explicit carried-forward-NOT-thinned
  Tier 4 ledger.
- **accessibility-reviewer — N/A-with-reason** (the r105 byte-identical
  a11y-N/A precedent): no new colour/encoding, no DOM/aria change, render
  numerically/visually unchanged, post-r107 working `[var(--color-*)]`
  form already in place.

## Verification (real numbers — measured on deployed prod)

- **Build gate** (final post-prettier shape, re-GREEN after the 2 YELLOW
  doc fixes): `tsc` **0** · `eslint --max-warnings 0` **0** · vitest
  **7 files / 105 tests** (95 r107 baseline + 10 new r108 = 105, zero
  regression) · `next build` **OK**.
- **Deploy**: `redeploy-web2.sh` additive → **local=200 public=200,
  DEPLOY OK**; legacy `ichor-web` 3030 untouched; tunnel not restarted →
  public URL stable; ONE consolidated SSH (no throttle).
- **Real-prod witness** (Playwright, deployed public URL, doctrine #7;
  the SHIPPED≠FUNCTIONAL gate — REAL data on REAL assets, 2 distinct
  assets/distributions/windows):
  - **`/briefing/EUR_USD`** (`1750e73a`, ny_mid, maxP=0.30): 7 canonical
    rows; `linScale` path EXACT — Base `p=0.30`→100 % (1046 px), Baisse
    modérée `0.22`→73.33 % (767.06 px), Forte baisse `0.18`→60 %
    (627.6 px), Crash `0.02`→6.67 % (69.72 px); every bar = `p·(100/
maxP)` to sub-pixel; tones exact OKLCH (bear `0.7106 0.1661 22.22`,
    neutral `0.7107 0.0351 256.79`, bull `0.7729 0.1535 163.22` —
    r107+r108 working together); skew "−14 pts" arithmetically correct.
  - **`/briefing/XAU_USD`** (`96f36fad`, pre_londres, distribution
    2/12/22/34/20/8/2, maxP=0.34): all 7 rendered widths match expected
    `max(p/maxP·100, 2)` to sub-pixel (programmatic check, every row
    `match:true`); skew "−6 pts" correct; exact OKLCH tones.
  - **Console**: warm reload **0 errors / 0 warnings** (cleaner than
    r107's documented cold-load 404-favicon + transient preload — a
    scalar swap introduces nothing).
  - Element screenshot of the EUR_USD ladder captured.

## NEW lessons

- A stale resume prompt + a slot-shifted prior round (r107 = the
  flagged Tailwind dedicated task, not the forecast ladder) is the
  routine R59/concordance case: derive the true next round from the LIVE
  repo (git log + ADR + SESSION_LOG), not the prompt's "continue ⇒ X";
  the un-done Tier-4 increment is next, and the memory chain must capture
  the actually-executed round (r107=Tailwind) so it is not silently
  thinned.
- The r105 "float-order risk" is real and surfaces at the FIRST genuine
  `linScale`-replaces-inline consumer: a scale-primitive substitution is
  numerically equivalent (≤1 ULP, sub-pixel) but NOT bit-identical — the
  honest claim is "equivalent to full precision, multiply-order
  disclosed", and the r105/r106 byte-identical precedent must be
  explicitly refused, not reflexively reused.

Voie D + ADR-017 held; additive web2-only deploy; zero backend / zero
migration (alembic 0050); doctrine #9 dated append, no new ADR.
