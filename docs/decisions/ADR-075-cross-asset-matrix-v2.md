# ADR-075: Cross-asset matrix v2 — 6-dimension macro state + per-asset bias tags

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-017 (research-only), ADR-022 (probability bias under
  Critic gate), ADR-069 (NY Fed MCT), ADR-070 (Cleveland Fed Nowcast),
  ADR-073 (NFIB SBET)

## Context

After waves W71 (NY Fed MCT), W72 (Cleveland Fed Nowcast), W74 (NFIB
SBET) added three new macro pillars to the data_pool, the surface
became fragmented: each pillar surfaced its own section, but the
aggregate "what is the current macro state" view was scattered across
6+ sections. Pass 1 régime classifier and Pass 2 mechanism citation
both had to re-aggregate by reading multiple sections.

The `executive_summary` at the top of data_pool already provides a
narrative régime classifier, but it's qualitative (5-bullet synthesis
+ régime label). It doesn't expose the underlying band values, so
Claude can't reason about "how far from regime boundary" or "which
dimension is driving the régime label".

W79 closes this gap with a structured 6-dimension matrix that
complements `executive_summary` rather than duplicating it.

## Decision

Add `_section_cross_asset_matrix(session)` to `services/data_pool.py`
that surfaces:

### Dimension table (6 rows × 4 cols)

| # | Dimension | Source | Bands |
|---|---|---|---|
| 1 | Inflation persistence | NY Fed MCT trend (W71) | anchored / near-target / above-target / unanchored |
| 2 | Inflation surprise | Cleveland CorePCE YoY − MCT (W72) | downside-strong / downside / neutral / upside / upside-strong |
| 3 | Liquidity / financial conditions | FRED NFCI (W42) | loose / mild-loose / mild-tight / tight |
| 4 | Tail risk | CBOE SKEW (W24) | calm / normal / elevated / tail-fear |
| 5 | Volatility | FRED VIXCLS | complacent / normal / elevated / panic |
| 6 | Small-business sentiment | NFIB SBOI (W74) | recession-pre / below-avg / soft / expansionary |

Band thresholds anchored on:
- **Inflation persistence** Powell 2024-Q3 cited "tolerable upper band
  2.5 %" + Fed 2 % target → 2.25 / 2.75 / 3.25
- **Inflation surprise** ±0.10 pts noise band, ±0.50 pts material
- **NFCI** ±0.5 sigma (~85th percentile)
- **SKEW** 135 / 145 / 155 (CBOE empirical regime breakpoints)
- **VIX** 15 / 22 / 30 (long-run quantile regime breakpoints)
- **SBOI** 95 / 98 / 102 anchored on 52-year average ≈ 98.0

### Per-asset directional-bias guide (8 Ichor pairs)

Heuristic mapping reads the 6 dimension bands and projects qualitative
pressure tags per asset (e.g. EUR_USD inflation_pressure_up + tight
NFCI → "USD-bid (NFCI tight) · Fed-on-hold supports USD"). Each tag
is a research-framing observation, not a trade signal. Output is a
list of bullet points per asset, joined by `·`. When no dimension
triggers, the asset shows `balanced`.

The mapping is intentionally **conservative**: only triggers a tag
when its dimension hits a clear band (e.g. NFCI ≥ 0 for tight,
SKEW elevated/tail-fear for tail_fear). Avoids spurious bias on
balanced regimes.

ADR-017 boundary preserved: the section header includes
"(research only, ADR-017)" and the docstring explicitly states "Bias
is a qualitative tag (`+`/`-`/`?`) anchored on macro theory, not
curve-fitting — the orchestrator's Critic re-weights it."

## Consequences

### Positive

- **Pass 1 régime classifier** now consumes a structured 6×4 table
  instead of re-aggregating 6 separate sections. Every dimension is
  classified into its own band with thresholds embedded in the data
  pool.
- **Pass 2 mechanism citation** has direct access to per-asset bias
  hints with their underlying dimensional drivers — citation
  becomes "USD_JPY → JPY-bid (safe haven), driven by SKEW
  tail-fear + VIX panic" rather than ad-hoc reasoning.
- **Verified live 2026-05-09 12:29 CEST**: section rendered in
  data_pool for EUR_USD with all 6 dimensions populated:
  - Inflation persistence: MCT 2.74 % near-target
  - Inflation surprise: +0.58 pts upside-strong
  - Liquidity: NFCI -0.51 loose
  - Tail risk: SKEW 138.21 normal
  - Volatility: VIX 17.08 normal
  - Small-biz sentiment: SBOI 95.80 below-avg
  - Per-asset tags: EUR_USD balanced, GBP_USD UK growth-tail downside,
    SPX500_USD earnings-tail downside, others balanced.
- **No new collector, no new migration**. Pure-leverage section that
  reads existing tables. Zero deploy risk.
- **No external dependencies, no licensing** — all sources are
  already Voie D-compliant collectors.

### Negative

- **Heuristic per-asset mapping is uncalibrated**. Future enhancement
  via Brier optimizer V2 (ADR-025) — collect realized outcomes vs
  predicted bias tags over 60 days, regress weights. For now, the
  mapping is conservative enough that uncalibrated weights are
  documented as "research framing" not a trade signal.
- **Section length** adds ~20 lines to data_pool markdown (≈600
  chars). Acceptable — the matrix is high-signal-density and
  Claude reads it in <1 second.
- **Some dimensions return n/a when collectors haven't run**
  (e.g. SBOI shows n/a if NFIB collector hasn't fetched yet). The
  table gracefully shows "n/a" + band="n/a" and per-asset hints
  fall back to "balanced". No crash, no data fabrication.

## Alternatives considered

- **Add bands directly to `executive_summary`** — rejected: would
  inflate the narrative section past its readable ceiling. Better
  to keep narrative + structured matrix separated.
- **One section per dimension with its band** — rejected: explodes
  data_pool sections from 41 to 47, dilutes signal density.
- **Numerical Z-scores instead of qualitative bands** — rejected for
  v1: bands are easier for Claude to reason about ("near-target" vs
  "+0.74 σ") and easier for humans to audit. Future v3 can add
  rolling Z-score columns alongside bands.
- **Computational heatmap (cross-asset correlation matrix)** —
  separate concern, already exists at `_section_correlations`. The
  cross-asset MATRIX (W79) is a pressure matrix per dimension,
  not a correlation matrix.

## Verification (live 2026-05-09)

```
sections_emitted: [..., 'cleveland_fed_nowcast', 'nfib_sbet',
                   'cross_asset_matrix', 'labor_uncertainty', ...]

Cross-asset matrix (W79)
| # | Dimension | Value | Band |
|---|---|---|---|
| 1 | Inflation persistence (MCT) | 2.74% | near-target |
| 2 | Inflation surprise (CorePCE - MCT) | 0.58 pts | upside-strong |
| 3 | Liquidity (NFCI) | -0.51 | loose |
| 4 | Tail risk (SKEW) | 138.21 | normal |
| 5 | Volatility (VIX) | 17.08 | normal |
| 6 | Small-biz sentiment (SBOI) | 95.80 | below-avg |

### Per-asset macro-pressure tags (research only, ADR-017)
- EUR_USD : balanced
- GBP_USD : UK growth-tail downside
- USD_JPY : balanced
- AUD_USD : balanced
- USD_CAD : balanced
- XAU_USD : balanced
- NAS100_USD : balanced
- SPX500_USD : earnings-tail downside (-)
```

The May 2026 macro state is a "soft-yet-not-broken" regime: liquidity
loose + sentiment below-avg + inflation surprise upside but trend
near-target. The matrix surfaces this conflict cleanly — exactly the
ambiguity Pass 1 régime classifier should detect and flag as
"transitional".

## References

- `apps/api/src/ichor_api/services/data_pool.py:_section_cross_asset_matrix`
- `apps/api/src/ichor_api/services/data_pool.py:_band` (helper)
- ADR-017 (research-only boundary), ADR-022 (probability bias under
  Critic gate), ADR-069/070/073 (the underlying collectors)
- Brier optimizer V2 (ADR-025) — future calibration path
