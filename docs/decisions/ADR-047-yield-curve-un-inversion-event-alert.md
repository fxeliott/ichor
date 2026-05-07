# ADR-047: YIELD_CURVE_UN_INVERSION_EVENT — recession imminent trigger

- **Status**: Accepted (post-implementation, wave 10 PR #45 SHA `5045a4b`)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase E recession-signal completeness

## Context

ADR-046 ratified YIELD_CURVE_INVERSION_DEEP (level threshold -50 bps, severity
warning). However, this captures the **leading** signal (median 14mo lead-time
to recession) but misses the **imminent** signal.

**Counterintuitive insight from NY Fed + Cleveland Fed empirical research** :
US recessions since 1976 do NOT begin during inversion. They begin **AFTER
the curve re-steepens** (un-inversion event). The mechanism :
- Inversion = market expects future short rates < current short rates
- Un-inversion = market now expects aggressive Fed easing imminently → only
  happens when recession is priced in
- Therefore : un-inversion is the **0-3 month imminent-recession trigger**

A simple level-threshold alert can't detect an **event** (state transition).
This ADR adds an event-detection sister alert.

## Decision

```python
AlertDef("YIELD_CURVE_UN_INVERSION_EVENT", critical,
         "Yield curve un-inversion event T10Y2Y={value:+.2f}pp",
         "yield_curve_un_inversion_conditions", 2, "above", ...)
```

Fires when **BOTH** :
1. Today's T10Y2Y > 0 (curve currently positive)
2. Any day in prior 60d had T10Y2Y <= -0.30 (deep inversion confirmation)

Condition count = 2 (= AND gate of both conditions). Threshold = 2 means
both must align.

### Severity : `critical` (escalates from sister DEEP at warning)

Imminent (0-3 month) recession trigger warrants critical severity. Distinct
from CRISIS_TRIGGERS list : `crisis_mode=False` because un-inversion is a
**probabilistic recession warning**, not a Crisis Mode (composite N>=2)
trigger event. The trader uses this as a regime-change signal, not as a
panic-mode trigger.

### Implementation : 60d window state-transition detection

`services/yield_curve_un_inversion_check.py` :
- `_fetch_last_n_days(session, days=60)` — pull last 60d observations
- `_check_conditions(history)` — verify (a) latest > 0 AND (b) min(60d) <= -0.30
- `evaluate_yield_curve_un_inversion(session, persist)` — fire when both
  conditions met

### Re-fire behavior

Will re-fire daily during the post-un-inversion window (until 60d from the
last deep-inversion day passes). This is **intentional** — Eliot needs daily
reminder during the imminent-recession regime. Alert dedup at presentation
layer if needed.

### Cron : daily 22:55 Paris

Last in nightly chain after YIELD_CURVE_INVERSION_DEEP (22:50). 5-min stagger
keeps logs separated.

## Consequences

### Pros
- Captures the **more dangerous** un-inversion signal (per NY Fed empirical)
- Pairs cleanly with sister DEEP alert (leading+imminent coverage complete)
- 60d backward window catches "ended-inversion" condition without manual state
- Source-stamped FRED:T10Y2Y for audit drill-back
- Currently FALSE on 2026-05-08 (T10Y2Y +49 bps, last deep <= -0.30 within
  60d window expired ~Apr 2026 per timeline)

### Cons
- Re-fires daily during 60d post-un-inversion window — noisy if regime is
  long
- Threshold -0.30 for "deep enough to count" is a tunable hyperparam
  (chosen as 60% of YIELD_CURVE_INVERSION_DEEP -0.50 threshold)

## Alternatives rejected
- **A: Z-score un-inversion** — same secular-drift problem as DEEP
- **B: cross_up direction (single-day event)** — misses post-event window,
  trader needs daily reminder during 0-3mo regime
- **C: Skip in v1, defer** — leaves the most-dangerous signal uncovered
- **D: 30d window instead of 60d** — too tight, recent inversions span months
- **E: Severity warning instead of critical** — undersells the signal
  per Cleveland Fed research

## Implementation
Shipped in PR #45 (SHA `5045a4b`). 9 tests covering AND gate + window
+ persist=False contract. Register-cron daily 22:55 Paris. Catalog assert
49 → 50 (milestone reached).

## Related
- ADR-017 boundary preserved
- ADR-046 (sister DEEP level threshold)
- NY Fed Yield Curve FAQ
- Cleveland Fed Yield Curve and Predicted GDP
- Eco3min 2s10s yield curve inversion history 1976-2026
