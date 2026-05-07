# ADR-046: YIELD_CURVE_INVERSION_DEEP — T10Y2Y level threshold recession leading indicator

- **Status**: Accepted (post-implementation, wave 9 PR #43 SHA `7e8af92`)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase E recession-signal coverage

## Context

The 10Y-2Y Treasury spread (FRED:T10Y2Y) inversion is the **most reliable
recession leading indicator since 1976** (NY Fed + Cleveland Fed research).
Every US recession since 1976 was preceded by a T10Y2Y inversion. Median
lead time : 14 months (range 6-24).

2022-2024 cycle saw the **2nd-deepest inversion in history** : -108 bps
trough, 25 months of continuous inversion — anomaly **not yet followed by
recession** as of 2026-05. Curve un-inverted to +49 bps as of 2026-05-06.

A z-score-based alert (per Phase E pattern) is inappropriate for T10Y2Y
because :
- The series has **secular drift** (2010s mean ~+150 bps, 2024 mean -50 bps)
- 90d z-score loses sensitivity at the bottom of cycle (baseline catches up)
- The TRADER-RELEVANT signal is **absolute level** (recession risk threshold)

This ADR adopts a **level threshold** alert instead : fire when T10Y2Y
crosses below -50 bps (deep inversion territory).

## Decision

```python
AlertDef("YIELD_CURVE_INVERSION_DEEP", warning,
         "T10Y2Y deep inversion {value:+.2f}pp",
         "t10y2y_spread_pct", -0.50, "below", ...)
```

Fires when latest T10Y2Y reading <= -0.50 pp (= -50 bps). 5-tier regime
classifier in payload : `severe` (<= -1.0), `deep` (<= -0.5), `shallow`
(< 0), `flat` (< 0.25), `normal` (>= 0.25).

### Threshold rationale : -50 bps

- Historical : NY Fed paper "Yield Curve as Leading Indicator" — recession
  probability rises sharply when T10Y2Y < 0 ; "deep" classification
  conventionally at -50 bps where recession lead time tightens to 12-18mo
- 2026-2027 forecast skews dovish (GS expects 50bp Fed cuts) — re-inversion
  unlikely near-term, but threshold remains active for tail-risk events
  (debt-ceiling cliff, Fed independence shock, fiscal stress repricing)

### Implementation : pure FRED query

`services/yield_curve_inversion_check.py` :
- `_fetch_latest()` — pull last observation from `fred_observations`
  WHERE series_id='T10Y2Y'
- `_classify_regime(spread_pct)` — 5-tier mapping
- `evaluate_yield_curve_inversion(session, persist)` — fire when level
  threshold crossed

### Cron : daily 22:50 Paris

Last in nightly chain (after VIX_TERM 22:45). FRED T10Y2Y publishes daily
with 1-day latency.

## Consequences

### Pros
- Trader-actionable level signal (recession risk threshold)
- Cheap : 1 SQL query per day
- Source already collected in `fred_extended.py`
- Self-documenting via 5-tier regime tag

### Cons
- Will fire daily during inversion periods (no built-in cross_down event
  detection — see ADR-047 for sister un-inversion event alert)
- 2026-05 in `normal` regime (+49 bps) — alert fires zero until next
  inversion cycle

## Alternatives rejected
- **A: Z-score (Phase E convention)** — secular drift breaks calibration
- **B: Daily delta (cross_down direction)** — misses ongoing-deep-inversion regime
- **C: Multi-tenor curve (T10Y3M sister)** — premature abstraction
- **D: ML-classified recession probability** — black box, not source-stamped

## Implementation
Shipped in PR #43 (SHA `7e8af92`). 14 tests covering 5-tier classifier +
all regime fire paths. Catalog assert 48 → 49.

## Related
- ADR-017 boundary preserved
- ADR-047 (sister UN_INVERSION_EVENT cross_up event)
- NY Fed Yield Curve as Leading Indicator FAQ
- Cleveland Fed Yield Curve and Predicted GDP
