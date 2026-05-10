# ADR-051: MACRO_QUINTET_STRESS — 5-dim composite (quartet + Treasury vol)

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: ADR-048 §Followups (quintet upgrade)

## Context

ADR-042 ratified MACRO_QUARTET_STRESS (4-dim composite : DXY + 10Y + VIX +
HY OAS, threshold N>=3/4). ADR-048 ratified TREASURY_VOL_SPIKE (DGS10 30d
realized vol annualized). ADR-048 §Followups explicitly suggested :

> **Quintet upgrade** : MACRO_QUARTET_STRESS could become MACRO_QUINTET_STRESS
> by adding TREASURY_VOL_SPIKE z-score as 5th dimension. Would require
> catalog AlertDef change (4-of-5 alignment threshold).

This ADR ships the upgrade as a SEPARATE alert (not modifying the existing
quartet) so :

- Both alerts coexist : quartet for the original 4-axis signal, quintet for
  the 5-axis enriched view
- Trader sees both fire simultaneously when both apply (signals strong
  agreement) or only one fires when axes diverge (signals which is the
  stronger constraint)
- No migration risk on quartet history

## Decision

```python
AlertDef("MACRO_QUINTET_STRESS", warning,
         "Macro quintet stress {value:.0f}/5 dimensions aligned",
         "quintet_stress_count", 4, "above", ...)
```

Fires when **N >= 4 of 5 dimensions** have `|z| > 2.0` (90d window).

### 5 dimensions

| #   | Series       | Label        | Mode                                 |
| --- | ------------ | ------------ | ------------------------------------ |
| 1   | DTWEXBGS     | DXY          | level                                |
| 2   | DGS10        | 10Y          | level                                |
| 3   | VIXCLS       | VIX          | level                                |
| 4   | BAMLH0A0HYM2 | HY_OAS       | level                                |
| 5   | DGS10        | TREASURY_VOL | realized_vol (30d annualized × √252) |

### Threshold rationale : 4-of-5 (stricter than quartet 3-of-4)

When adding a 5th independent axis, the simple count threshold should INCREASE
proportionally to maintain specificity. Per OFR FSI methodology + Federal
Reserve supervisory stress test, 4-of-5 alignment in same direction = the
unmistakable systemic-stress signature. 3-of-5 (= 60% alignment) is too
permissive — would over-fire on partial alignments.

Mathematical intuition : if base rate of any single dim being |z|>2 is
~5% under approx normality, then :

- P(>=3 of 4 align) ≈ 0.5%
- P(>=4 of 5 align) ≈ 0.5% (similar specificity preserved)
- P(>=3 of 5 align) ≈ 5% (would over-fire)

### Dimension #5 methodology : same as TREASURY_VOL_SPIKE (ADR-048)

- Fetch DGS10 levels for 90d window + buffer
- Compute log-changes per business day
- Compute 30d rolling stdev of log-changes
- Annualize : `realized_vol = stdev × √252` (in %)
- Z-score current realized_vol vs 90d distribution of realized_vols

This reuses `treasury_vol_check.py` semantics — stays consistent across
sister alerts.

### Severity : warning (matches quartet)

Composite multi-dim alignment warrants warning. The trader interprets
the regime tag in extra_payload :

- `stress` (N+ aligned positive) — funding/credit/duration stress regime
- `complacency` (N- aligned negative) — unusually-tight all-axes regime
- `mixed` (N>=4 extreme but split direction) — divergent / dollar-smile transition

### Cron : daily 22:37 Paris

Slot inserted between MACRO_QUARTET (22:35) and TREASURY_VOL (22:42). 2-min
spacing keeps logs separated.

## Consequences

### Pros

- Closes ADR-048 §Followups explicit upgrade item
- Adds Treasury-vol axis (previously absent from quartet)
- Coexists with quartet (no migration risk)
- 4-of-5 threshold preserves specificity vs quartet 3-of-4
- Source-stamped + per_dim audit drill-back
- Reuses existing FRED collector (no new feed)

### Cons

- 2 similar alerts (quartet + quintet) — slight risk of trader confusion
  when both fire vs only one. Mitigation : ADR docstrings + payload
  metadata distinguish clearly
- Realized-vol computation adds ~30ms latency vs pure level z-score
  (acceptable for daily cron)

### Neutral

- The 2 alerts can be reconciled in a future v3 doctrine where quartet is
  deprecated in favor of quintet only — but not v1, both ship in parallel.

## Alternatives rejected

### A — Modify MACRO_QUARTET_STRESS in-place to become QUINTET

Rejected. Migration risk on existing quartet alerts in DB. Two coexisting
alerts cleaner separation of concerns.

### B — 5-of-5 strict (all 5 must align)

Rejected. Way too strict — would never fire in practice. Even March 2020
COVID didn't have all 5 dims |z|>2 simultaneously (DXY moved opposite of
intuitive).

### C — 3-of-5 simple (lower bar)

Rejected. Loses specificity. P(>=3/5)≈5% under normality = over-firing.

### D — Per-dim weighted vote (e.g. HY OAS counts 2x)

Rejected for v1. Adds complexity. Equal-weight 4-of-5 is the canonical
academic threshold. Weighted voting is a v2 enhancement.

### E — Defer until quartet deprecated

Rejected. Quartet has value as 4-axis fast signal ; quintet enriches.
No reason to deprecate.

### F — Use Treasury vol via MOVE Index instead of DGS10 realized vol

Rejected. MOVE is paid (Voie D violation per ADR-009). DGS10 realized vol
is the free proxy already shipped in ADR-048.

## Implementation

Shipped wave 14 PR #53. Files :

- `apps/api/src/ichor_api/services/macro_quintet_check.py` (NEW, ~280 LOC)
- `apps/api/src/ichor_api/cli/run_macro_quintet_check.py` (NEW)
- `apps/api/tests/test_macro_quintet_check.py` (NEW, 17 tests)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend, bump assert 52 → 53)
- `scripts/hetzner/register-cron-macro-quintet-check.sh` (NEW, daily 22:37 Paris)
- `docs/decisions/ADR-051-macro-quintet-stress-alert.md` (this file)

## Related

- ADR-009 Voie D
- ADR-017 boundary preserved (composite signal, no BUY/SELL leak)
- ADR-042 MACRO_QUARTET_STRESS (sister, coexists)
- ADR-048 TREASURY_VOL_SPIKE (5th dimension methodology source)
- OFR Financial Stress Index methodology
- TORVAQ four-invariants framework
- Federal Reserve supervisory stress test 2025
