# ADR-049: HY_IG_SPREAD_DIVERGENCE — credit-cycle inflection detector

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: Phase E completeness — credit-cycle dimension

## Context

Existing catalog has individual credit alerts :
- HY_OAS_WIDEN (level threshold 50 bps daily change)
- HY_OAS_CRISIS (level threshold 800 bps absolute)
- IG_OAS_WIDEN (level threshold 30 bps daily change)

But no detection of the **HY-IG differential** — the canonical credit-cycle
inflection signal. Per ICAIF + Macrosynergy 2024 + InvestmentGrade Q1 2026
research, the HY-IG spread differential **front-runs HY OAS spikes by 2-4
weeks** because :

- **Compression** (HY tightens > IG, or IG widens > HY) : institutional
  flight-to-quality begins. IG holders rotate to Treasuries while HY remains
  bid by yield-hunters. **Early recession warning** (paradoxical).
- **Expansion** (HY widens > IG widens) : late-cycle credit stress. High-yield
  issuers losing access to capital. Default rate cycle building.

Both source series (BAMLH0A0HYM2 + BAMLC0A0CM) are already collected by
`fred_extended.py` EXTENDED_SERIES_TO_POLL. No new feed required.

## Decision

```python
AlertDef("HY_IG_SPREAD_DIVERGENCE", warning,
         "HY-IG spread divergence z={value:+.2f}",
         "hy_ig_spread_z", 2.0, "above", ...)
```

Fires when `|z| >= 2.0` where z is the 90d-rolling z-score of (HY OAS - IG OAS).

### Methodology

1. Fetch last ~104d of BAMLH0A0HYM2 + BAMLC0A0CM, inner-join by date
2. Compute differential = HY - IG per day (in % units, FRED native)
3. Z-score current diff vs trailing 90d distribution
4. Fire when `|z| >= 2.0`
5. Regime tag : `expansion` (z > +2) | `compression` (z < -2) | ''

### Cron : daily 22:48 Paris

Slot inserted between `treasury-vol` (22:42) and `vix-term` (22:45) actually
chosen 22:48 to avoid clash. Actual slot 22:48.

### Source-stamping

`extra_payload.source = "FRED:BAMLH0A0HYM2-BAMLC0A0CM"` plus :
- `hy_oas_pct`, `ig_oas_pct`, `differential_pct`, `differential_bps`
- `baseline_mean_pct`, `baseline_std_pct`, `n_history`
- `regime`
- `methodology`

## Consequences

### Pros
- Front-runs HY OAS spikes by 2-4 weeks per academic + practitioner research
- Both directions captured (expansion/compression)
- Reuses existing FRED collector — zero new infrastructure
- Phase E convention preserved (90d window, |z|>=2, info/warning split)

### Cons
- Inner-join means pairs are limited to dates BOTH series report
  (typically business days, but holidays may differ)
- 60d minimum history before z-score is credible

## Alternatives rejected

### A — Use HY/IG ratio instead of difference
Ratio is multiplicative; differential is additive. Differential matches
academic literature convention.

### B — Use IG_OAS_WIDEN + HY_OAS_WIDEN combo (existing alerts)
Doesn't capture the **divergence** signal — could have both fire
simultaneously without divergence, or one fire without the other being
informative. The differential is the canonical metric.

### C — Multi-tenor differential (BB - BBB instead of HY - IG)
More granular but requires more series and pairs. v2 if Eliot wants finer
tier resolution.

### D — Daily change z-score (delta of diff)
Noisy; level z-score against 90d baseline is more stable.

### E — Skip in v1
Leaves credit-cycle inflection blind spot.

## Implementation

Shipped wave 12 PR #48. Service `services/hy_ig_spread_check.py` ~210 LOC,
CLI `cli/run_hy_ig_spread_check.py`, register-cron daily 22:48 Paris.
13 tests covering zscore math, regime classifier, no-data noop,
below-threshold no-alert, expansion fire, compression fire, persist=False,
threshold_constant, window=90d, dataclass shape.

Catalog assert 51 → 52.

## Related
- ADR-009 Voie D (free FRED only)
- ADR-017 boundary preserved
- ADR-042 MACRO_QUARTET_STRESS (uses BAMLH0A0HYM2 as one of 4 dims)
- HY_OAS_WIDEN / HY_OAS_CRISIS / IG_OAS_WIDEN (existing complementary level alerts)
- Macrosynergy 2024 credit-cycle research
- InvestmentGrade Q1 2026 Outlook
