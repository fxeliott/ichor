# ADR-043: DOLLAR_SMILE_BREAK alert — US-driven instability detector

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP E.3 (Phase E innovations)

## Context

Stephen Jen's classic Dollar Smile framework (2001) holds that USD
strengthens at two extremes :

- **Left side** : USD strong on global fear (capital flight to safe haven)
- **Middle** : USD weak on moderate US growth
- **Right side** : USD strong on US outperformance

For 22 years this was the canonical mental model for the dollar. In
**April 2025** (per Wellington research), a new regime emerged that the
classic smile cannot explain : **USD fell WITH stocks during tariff
panic**. The broken / "crooked" smile reflects a **US-DRIVEN**
instability — where the source of stress is the US itself (fiscal
deterioration, tariff shocks, Fed independence threats, de-dollarization)
rather than the world running TO the US for safety.

Stephen Jen himself warned in a Bloomberg interview 2025-11-12 that USD
could fall ~13.5% during Trump's second term, and that _"continued US
fiscal imprudence and a return to quantitative easing could jeopardize
the global standing of US Treasuries and undermine the left side of the
dollar smile."_

Key structural risk : $26T unhedged foreign-held US assets create a
self-reinforcing exit loop — dollar weakness triggers hedging, which
triggers more selling, which triggers more weakness. This is precisely
the regime the classic smile misses.

This ADR adds **DOLLAR_SMILE_BREAK** — a composite alert that detects
when these 4 conditions align simultaneously :

1. Term premium expanding (fiscal stress emerging)
2. DXY weakening (USD losing haven bid)
3. VIX not panicking (NOT classic left-side smile)
4. HY OAS not blowing out (NOT funding-stress regime)

When all 4 hold simultaneously, the regime is **US-driven instability**.

## Decision

Wire one new catalog alert :

```python
AlertDef("DOLLAR_SMILE_BREAK", warning,
         "Dollar smile broken — US-driven instability ({value:.0f}/4)",
         "dollar_smile_conditions_met", 4, "above", ...)
```

Fires when all 4 of 4 composite conditions hold (`current_value >= 4`).

### Implementation : 4-condition AND gate

`services/dollar_smile_check.py` :

- 4 input series : `THREEFYTP10` (KW term premium), `DTWEXBGS` (DXY),
  `VIXCLS` (VIX), `BAMLH0A0HYM2` (HY OAS).
- Per-dim z-score on rolling 90d window (same as TERM_PREMIUM_REPRICING
  - MACRO_QUARTET_STRESS).
- 4 conditions :
  - `term_premium_z > +2.0` (expansion threshold matches Phase E.2)
  - `dxy_z < -1.0` (DXY weakening — looser than ±2 because directional
    bias is the signal)
  - `vix_z < +1.0` (not panic — distinguishes from classic left smile)
  - `hy_oas_z < +1.0` (no credit stress — distinguishes from funding
    stress)
- Composite gate : count_passing >= 4 → fire.

### Why 4-of-4 strict AND (not 3-of-4)

The composite signal is **specifically about misalignment** between
fiscal stress (term premium up) and USD strength (which classic smile
predicts). All 4 must hold for the regime to be unambiguous :

- 3-of-4 with VIX panic = classic left-side smile (USD strong on global
  fear) — not us-driven
- 3-of-4 with HY OAS spike = funding stress (March 2020-style) — not
  us-driven
- 3-of-4 with term premium expansion missing = noise without the fiscal
  driver

The 4-of-4 gate ensures we catch the SPECIFIC pattern Wellington
identified in April 2025 + Stephen Jen warned about in 2025-11-12.

### Per-condition direction interpretation

| Condition              | Threshold | Direction       | Meaning                                       |
| ---------------------- | --------- | --------------- | --------------------------------------------- |
| term_premium_expansion | z > +2.0  | strict positive | Fiscal stress / term premium expansion regime |
| dxy_weakness           | z < -1.0  | strict negative | USD weakening relative to 90d baseline        |
| vix_not_panic          | z < +1.0  | strict negative | Equity vol moderate / no panic                |
| hy_oas_not_stress      | z < +1.0  | strict negative | Credit spreads tight / no systemic stress     |

The 1-of-4 thresholds (term premium expansion @ +2σ) is stricter than
the 3-of-4 thresholds (the "not panic / not stress" conditions @ +1σ).
This asymmetry is intentional : we want strong evidence of the _driver_
(fiscal stress) but only mild evidence of _non-confounders_ (no panic,
no credit stress).

### Source-stamping (ADR-017)

`extra_payload.source = "FRED:THREEFYTP10+DTWEXBGS+VIXCLS+BAMLH0A0HYM2"`.
Plus :

- `smile_regime` : 'us_driven_instability' if fired, '' otherwise
- `n_conditions_passing` : 0-4 count
- `z_term_premium`, `z_dxy`, `z_vix`, `z_hy_oas` (raw z-scores)
- `conditions` : list of `{name, z_score, threshold, operator, passes}`
  for each of the 4 conditions

Trader can re-derive the regime from the payload alone, including
which condition prevented firing (when count < 4).

### Cron schedule

Daily 22:40 Paris. Post NY close + 5 min after MACRO_QUARTET_STRESS
(22:35) so all 3 daily macro alerts (TERM_PREMIUM 22:30 +
MACRO_QUARTET 22:35 + DOLLAR_SMILE 22:40) chain through the same
FRED data freshness window.

## Consequences

### Pros

- **Closes the 'broken smile' detection gap** in Ichor's macro stack.
  Prior alerts (TERM_PREMIUM_REPRICING, MACRO_QUARTET_STRESS) detect
  COMPONENTS of the regime ; DOLLAR_SMILE_BREAK detects the SPECIFIC
  alignment that defines the US-driven instability.
- **High specificity** : 4-of-4 AND gate is rare (the conjunction of
  a +2σ term-premium move AND a <-1σ DXY move AND VIX/HY OAS staying
  benign all simultaneously). When it fires, it's unambiguous.
- **Differentiated from sister alerts** : MACRO_QUARTET catches "all
  stressed" or "all complacent" ; DOLLAR_SMILE catches "stress is
  building but USD is FALLING" — a directional misalignment specific
  to the broken-smile regime.
- **Reuses existing FRED collector** : 4 series all already polled.
- **Cheap** : 4 SQL queries × 90 numbers averaged. Sub-second per
  execution.
- **Self-calibrating** : 90d rolling baselines absorb steady-state
  drift. Catches _acceleration_ + _misalignment_.
- **2026 trader-actionable** : per Stephen Jen 2025-11-12 + Eurizon
  SLJ outlook, this regime is THE story for 2026 USD trading.

### Cons

- **AND gate strictness** : 4-of-4 is more restrictive than 3-of-4. The
  alert may fire less frequently than the regime is genuinely active
  (any one condition transient miss = no fire). Mitigation : the
  alternative MACRO_QUARTET_STRESS fires more loosely on related
  patterns. Both alerts together provide complementary coverage.
- **Threshold sensitivity** : the 4 thresholds (2.0, -1.0, +1.0, +1.0)
  are research-grounded but not extensively backtested. v2 could tune
  via grid search on historical broken-smile episodes (April 2025,
  late 2025).
- **Dependency on rolling baselines** : if the broken-smile regime
  PERSISTS for >90 days, the rolling baseline absorbs it and the alert
  stops firing despite the regime continuing. Mitigation : a 252d
  structural variant (sister to GEOPOL_REGIME_STRUCTURAL) could be
  added in v2.
- **Single-direction bias** : detects "USD weakening despite haven
  conditions absent" but not the reverse "USD strengthening despite US
  outperformance absent." The reverse case is rarer and less
  trader-actionable but exists conceptually.

### Neutral

- The cron fires daily even when no alignment. CLI prints a structured
  status either way for operator visibility.

## Alternatives considered

### A — 3-of-4 OR gate

Rejected : would conflate the broken-smile regime with classic-left-smile
(VIX panic + DXY strong + HY OAS spike) which is the OPPOSITE pattern.
The 4-of-4 AND gate enforces directional specificity.

### B — Use TERM_PREMIUM_REPRICING + manual narrative attribution

Considered : trader could combine TERM_PREMIUM_REPRICING (when in
'expansion' regime) with a separate DXY direction check. Rejected for
v1 because it pushes the composite reasoning to the trader's manual
work, which the alert system is supposed to automate.

### C — ML classifier on (term_premium, dxy, vix, hy_oas) z-scores

Tabled (not rejected) for v2 : a logistic regression or random forest
trained on labeled historical broken-smile episodes would be more
nuanced than the threshold AND gate. Requires labeled training data
which we don't have for v1. Defer until backtests can identify >20
historical episodes.

### D — Weight the conditions (term_premium = 0.5, others = 0.17 each)

Rejected for v1 : equal-weight count is interpretable. Weighted
composite would obscure why an alert fires (which condition led).
The `conditions` payload already exposes the per-dim values for
trader inspection — weighting can be added in v2 if needed.

### E — Add a 5th condition (e.g. term_premium 252d-structural)

Tabled for v2 : the 4 conditions are already research-grounded
(Stephen Jen / Wellington / Eurizon SLJ) ; adding more dilutes the
specificity. v2 could add a 5th condition reflecting Fed-independence
proxy (e.g. consensus probability of Fed chair replacement before 2027) once a clean signal is identified.

### F — Skip the alert because TERM_PREMIUM_REPRICING + MACRO_QUARTET

already cover the regime

Rejected : neither sister alert specifically detects the
**directional misalignment** (term premium up + DXY down). They
detect components, not the alignment itself. A trader looking at
the catalog without DOLLAR_SMILE_BREAK has to manually combine the
sister alerts ; this composite alert closes that gap.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/dollar_smile_check.py` (NEW, ~270 LOC)
- `apps/api/src/ichor_api/cli/run_dollar_smile_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 45 → 46)
- `apps/api/tests/test_dollar_smile_check.py` (NEW, 14 tests)
- `scripts/hetzner/register-cron-dollar-smile-check.sh` (NEW, daily
  22:40 Paris)
- `docs/decisions/ADR-043-dollar-smile-break-alert.md` (this file)

No new collector — all 4 FRED series already polled by
`fred_extended.py`.

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-009 — Voie D (free + self-hosted, no paid feeds).
- ADR-041 — TERM_PREMIUM_REPRICING (input #1 of this composite).
- ADR-042 — MACRO_QUARTET_STRESS (sister composite, broader scope).
- Jen, Stephen and Fatih Yilmaz (2001). Original Dollar Smile
  framework — Eurizon SLJ Capital research.
- Jen, Stephen and Joana Freire (2025-11). "Dollar smile, fiscal
  imprudence and Fed independence" — Eurizon SLJ Capital note.
- Wellington Management (April 2025). "Crooked Smile" research note
  flagging April 2025 regime change.
- Stephen Jen Bloomberg interview (2025-11-12). USD ~13.5% downside
  during Trump 2nd term forecast.

## Followups

- v2 : 252d structural variant (catches PERSISTENT broken-smile regime
  beyond 90d rolling baseline drift).
- v2 : ML classifier replacement for the threshold AND gate, trained
  on labeled historical episodes once we accumulate 20+ broken-smile
  windows.
- v2 : Fed-independence proxy as 5th condition (when a clean signal
  available — Polymarket/Kalshi event probability could work).
- v2 : weighted composite score instead of count (e.g. fed_smile_score
  ∈ [0, 1] with term_premium weight 0.5, others 0.17).
- Phase E.5 : feed `dollar_smile_conditions_met` as Brier V2 driver
  feature (regime-aware probability calibration for FX assets).
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  live USTR/Fed-chair news context at alert time and produce a
  1-paragraph regime attribution narrative grounded in named events.
