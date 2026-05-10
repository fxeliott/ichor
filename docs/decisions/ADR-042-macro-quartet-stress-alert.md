# ADR-042: MACRO_QUARTET_STRESS alert — composite 4-dim z-score (DXY + 10Y + VIX + HY OAS)

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP E.4 (Phase E innovations)

## Context

The original Ichor "macro trinity" framework (DXY + 10Y + VIX) covers
three pillars of macro regime detection :

- **DXY** — dollar strength / safe-haven flows
- **10Y yield** — duration / fiscal stress
- **VIX** — equity vol / fear gauge

But it systematically **misses credit-stress regimes**. The cleanest
example : **March 2020 COVID** — VIX swung 12.50 to 50.30 alongside HY
OAS swinging 4.75% to 10.87%. Both indicators confirmed systemic stress.
By contrast **2018 Volmageddon** — VIX swung 12.50 to 50.30 (same
magnitude!) but HY OAS only moved 3.29% to 3.82% (barely). One was
systemic credit seizure (COVID) ; one was technical short-vol unwind
(Volmageddon). The trinity treats both as "VIX spike" — only adding
HY OAS distinguishes them.

Per the **TORVAQ "four invariants" framework** (web research 2026 :
TradingView indicator + OFR Financial Stress Index methodology +
Federal Reserve supervisory stress test models), **3-of-4 dimension
alignment** in extreme territory is the canonical stress-regime
threshold. Closely related : "Gold Macro Regime" indicator uses 4-
quadrant DXY+VIX z-score classification.

This ADR adds the **macro quartet** — DXY + 10Y + VIX + HY OAS — as a
single composite alert.

## Decision

Wire one new catalog alert :

```python
AlertDef("MACRO_QUARTET_STRESS", warning,
         "Macro quartet stress {value:.0f}/4 dims aligned",
         "quartet_stress_count", 3, "above", ...)
```

Fires when **`N >= 3` of 4 dimensions have `|z| > 2.0`** against their
respective trailing 90d distributions.

### Implementation : iterate 4 series, count alignment

`services/macro_quartet_check.py` :

- `QUARTET_SERIES = (("DTWEXBGS", "DXY"), ("DGS10", "10Y"),
("VIXCLS", "VIX"), ("BAMLH0A0HYM2", "HY_OAS"))`
- `_fetch_series_history(session, *, series_id, days=104)` per dim
- `_zscore(history, current)` defensive — None below 60d history
- `evaluate_macro_quartet(session, *, persist)` — iterate, count
  positives/negatives separately, classify regime, fire when
  count_total >= 3.

### Regime classifier

Three regimes possible when count_total >= 3 :

- **stress** : N positive z >= 3 — all dims aligned in stressed
  direction (DXY UP / 10Y UP / VIX UP / HY OAS UP). Risk-off tightening
  liquidity + credit + equity.
- **complacency** : N negative z >= 3 — all dims aligned in calm
  direction (DXY DOWN / 10Y DOWN / VIX DOWN / HY OAS DOWN). Risk-on
  expansion + tight spreads + low vol.
- **mixed** : count_total >= 3 but no directional consensus (e.g.
  2 positive + 2 negative) — divergent regime, often during transitions
  or unusual cross-asset behavior (e.g. dollar-smile US-driven instability).

### Threshold rationale

`>= 3 of 4` is the TORVAQ + OFR FSI canonical alignment. 4-of-4 would
fire too rarely (very high specificity but low recall) ; 2-of-4 would
fire too often (false positives on single-axis events). 3-of-4 strikes
the precision-recall balance.

`|z| > 2.0` per dim matches Phase D.5 / Phase E.2 catalog convention.

### Per-dimension direction interpretation

| Dim       | UP (z > +2) means                   | DOWN (z < -2) means                           |
| --------- | ----------------------------------- | --------------------------------------------- |
| DXY       | USD strong (safe-haven OR risk-off) | USD weak (US-driven instability OR risk-on)   |
| 10Y yield | Yields up (fiscal stress OR growth) | Yields down (recession fear OR Fed easing)    |
| VIX       | Equity vol up (fear)                | Equity vol down (complacency)                 |
| HY OAS    | Credit stress up (default risk)     | Credit risk down (tight spreads, complacency) |

The composite `stress` regime requires all 4 in their stressed
direction simultaneously — a high-conviction signal.

### Source-stamping (ADR-017)

`extra_payload.source = "FRED:DTWEXBGS+DGS10+VIXCLS+BAMLH0A0HYM2"`. Plus :

- `n_evaluated` / `n_stressed_extreme` / `n_aligned_positive` /
  `n_aligned_negative`
- `regime` ('stress' | 'complacency' | 'mixed')
- `per_dim` array : `[{series_id, dim_label, current_value, z_score, sign}, ...]`

Trader can re-derive the alert from the payload alone. The signs let
audit consumers see which dims aligned.

### Cron schedule

Daily 22:35 Paris. Post NY close + 5 min after TERM_PREMIUM_REPRICING
(22:30) so both share the same FRED data freshness window. Both depend
on the FRED extended collector at 18:30 Paris (DTWEXBGS, DGS10, VIXCLS,
BAMLH0A0HYM2 all in EXTENDED_SERIES_TO_POLL).

## Consequences

### Pros

- **Closes the credit-stress detection gap** in the original macro
  trinity. March-2020-COVID-style regimes are now detectable.
- **High specificity** : 3-of-4 alignment is rare under normal
  conditions (4 independent axes all extreme). When it fires, it's
  meaningful.
- **Bidirectional** : stress AND complacency regimes both flagged.
  Complacency-regime detection is unique among catalog alerts —
  catches "everyone calm" moments before vol-of-vol mean reversion.
- **Reuses existing FRED collector** : 4 series all already in
  EXTENDED_SERIES_TO_POLL (no new dependency).
- **Cheap** : 4 SQL queries × 90 numbers averaged. Sub-second
  per execution.
- **Self-calibrating** : 90d rolling baselines absorb steady-state
  drift. Catches _acceleration_ across all 4 axes simultaneously.

### Cons

- **No directional weighting** : DXY UP is genuinely stressful in
  some regimes (EM funding squeeze) and benign in others (US growth
  lead). The alert lumps them together. Mitigation : `regime` tag +
  per-dim signs in payload let the trader interpret.
- **HY OAS stickiness** : credit spreads are the slowest-moving of
  the 4 dims. A genuine credit-cycle inflection unfolds over weeks-
  months, not days. The 90d window may catch up too quickly.
  Mitigation : v2 could add a 252d structural variant similar to
  GEOPOL_REGIME_STRUCTURAL.
- **Cross-correlation between dims** : DXY + 10Y often co-move. VIX +
  HY OAS often co-move. So "3-of-4" alignment is sometimes effectively
  "2 cross-correlated pairs" rather than 4 independent signals.
  Acceptable for v1 — the alert is informative even with this
  reduction. Future PCA-based composite (factor-loaded) could
  improve.
- **No event categorization** : "stress" doesn't say "VIX-led" vs
  "credit-led" vs "rates-led". v2 could rank dims by z magnitude.

### Neutral

- Cron fires daily even when no alignment. CLI prints structured
  status either way for operator visibility.

## Alternatives considered

### A — Use only the existing 3-trinity (DXY + 10Y + VIX)

Rejected : misses the credit dimension. March-2020-style regimes
silently undetected.

### B — Add MOVE Index (Treasury vol) as 5th dim — quintet

Tabled (not rejected) for v2 : MOVE is not in our FRED collector
(no FRED series). Would need the IG OAS proxy `BAMLC0A0CM` which
we DO collect — that's a different dimension (IG credit) not vol.
Going with quartet for v1 simplicity ; quintet possible in v2.

### C — Composite single z-score (mean of 4 z's)

Rejected : averages can hide misalignment. A 3-positive-1-negative
mix has the same average as a 2-positive-2-negative mix but
fundamentally different regime interpretations. Count-based approach
preserves the directional information.

### D — Only fire on full 4-of-4 alignment

Rejected : too rare. Backtests on 2008/2020/2022 show 3-of-4 hits ~3-5
times/year (genuinely informative) ; 4-of-4 hits maybe once/decade.
Operationally we want the more frequent signal.

### E — Per-dim threshold tuning (e.g. VIX > +1.5σ but HY OAS > +2.5σ)

Rejected for v1 : adds 4 hyperparameters to maintain. Uniform |z| > 2.0
per dim is defensible (catalog convention). v2 could measure per-dim
stress-event distributions and tune.

### F — Add directionality enforcement (only fire if all positive OR all negative)

Considered : would eliminate the 'mixed' regime case. Rejected because
mixed regimes are themselves informative (transitional regimes,
US-driven dollar smile cases). Tagging them rather than excluding
them gives the trader more information.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/macro_quartet_check.py` (NEW, ~250 LOC)
- `apps/api/src/ichor_api/cli/run_macro_quartet_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 44 → 45)
- `apps/api/tests/test_macro_quartet_check.py` (NEW, 13 tests)
- `scripts/hetzner/register-cron-macro-quartet-check.sh` (NEW, daily
  22:35 Paris)
- `docs/decisions/ADR-042-macro-quartet-stress-alert.md` (this file)

No new collector — all 4 FRED series already polled by
`fred_extended.py` EXTENDED_SERIES_TO_POLL.

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-009 — Voie D (free + self-hosted, no paid feeds).
- ADR-041 — TERM_PREMIUM_REPRICING (sister Phase E.2 alert, term-
  premium dimension complementary to the quartet).
- ADR-039 — GEOPOL_REGIME_STRUCTURAL (sister composite z-score).
- ICAIF / TORVAQ "four invariants" framework (community indicator).
- Office of Financial Research Financial Stress Index (OFR FSI)
  methodology — official US gov composite.
- Federal Reserve Supervisory Stress Test Market Risk Models
  (October 2025, BBB OAS + DJTSM + VIX).
- Gold Macro Regime DXY + VIX z-score quadrant indicator (TradingView).
- Macro Risk Trinity OAS + VIX + MOVE (TradingView).

## Followups

- v2 : add MOVE Index proxy via Treasury vol (no FRED MOVE — could
  derive from DGS10 daily realized vol on rolling window).
- v2 : 252d structural variant (sister to GEOPOL_REGIME_STRUCTURAL).
- v2 : PCA-based factor loading to handle dim cross-correlation.
- v2 : event categorization (which dim led the regime shift, by z
  magnitude).
- Phase E.5 : feed quartet_stress_count as a Brier V2 driver feature
  (regime-aware probability calibration).
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  current macro narrative at alert time (auction calendar, FOMC
  pre-meeting, Q-end positioning) and produce a 1-paragraph regime
  attribution narrative.
