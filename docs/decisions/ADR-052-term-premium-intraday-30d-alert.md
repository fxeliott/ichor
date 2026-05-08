# ADR-052: TERM_PREMIUM_INTRADAY_30D — completes term premium trinity 30d/90d/252d

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: Phase E completeness — term premium trinity

## Context

Phase E shipped two term-premium alerts on the Kim-Wright 10y term premium
(FRED:THREEFYTP10) :
- **TERM_PREMIUM_REPRICING** (ADR-041, 90d window, severity warning)
- **TERM_PREMIUM_STRUCTURAL_252D** (ADR-045, 252d window, severity info)

The 90d window catches narrative-shift episodes (debt-ceiling drama,
auction tail repricing) but **dampens intra-month event-driven shifts**
that resolve within days :
- USTR Section 301 tariff escalation press release
- Fed-independence headline (e.g. Trump-aligned chair nominee speech)
- Single auction tail surprise (3y/10y/30y)
- FOMC press conference reaction
- Single fiscal-cliff headline

Per Phase E doctrine (cf GEOPOL_FLASH 30d / GEOPOL_REGIME_STRUCTURAL 252d
sister-pair pattern, ADR-039) : multiple windows on the same series
provide **signal stacking** for the trader.

This ADR adds the **30d intra-month acute** companion, completing the
trinity 30d/90d/252d.

## Decision

```python
AlertDef("TERM_PREMIUM_INTRADAY_30D", warning,
         "Term premium intra-month z={value:+.2f}",
         "term_premium_z_30d", 2.0, "above", ...)
```

Window : 30d. Threshold : `|z| >= 2.0` aligned with sister 90d alert.

### Severity : `warning` (matches 90d, distinct from 252d info)

The 30d signal is **as actionable** as the 90d signal — both flag
events the trader should incorporate into next session card. The
distinction is **timing** :
- 30d : event happened in last few days, just hitting baseline
- 90d : narrative is building/sustaining over multi-week horizon
- 252d : structural regime shift (severity info, context only)

When BOTH 30d and 90d fire same direction → high-conviction signal.
When only 30d fires → potential noise / single-event reaction.
When only 90d fires → narrative is sustaining without recent acceleration.

### Cron : daily 22:25 Paris

5 minutes before TERM_PREMIUM_REPRICING (22:30). Lets the trader see
the acute reading first, then the tactical 90d reading second — natural
reading order from short to long window.

### Source-stamping

`extra_payload.source = "FRED:THREEFYTP10"` with :
- `term_premium_pct`, `term_premium_bps`, `baseline_mean_pct`, `baseline_std_pct`
- `n_history`, `window_days=30`, `regime`, `observation_date`
- `methodology` string
- `sister_alerts` list — explicit cross-reference to 90d + 252d sisters
  for trader drill-back

### Implementation : code reuse from sister 90d service

`services/term_premium_intraday_check.py` is ~95% structurally identical
to `term_premium_check.py` (90d) — same FRED query, z-score helper,
regime classifier. Only differences :
- `ZSCORE_WINDOW_DAYS = 30` (vs 90)
- `_MIN_ZSCORE_HISTORY = 20` (warmup floor on 30d window)
- `metric_name = "term_premium_z_30d"`
- Module docstring + `sister_alerts` payload field

Per ADR-039 doctrine : duplication > premature abstraction.

## Consequences

### Pros
- Closes the trinity 30d/90d/252d on term premium (parity with GEOPOL pair)
- Catches intra-month events the 90d window dampens
- Severity warning matches 90d (consistent escalation tier)
- Reuses existing FRED collector (zero infra)
- 22:25 cron slot precedes 90d 22:30 (logical reading order)

### Cons
- 3 alerts on same series ↔ potential signal dilution if all fire
  simultaneously (mitigation : trader interprets the combination)
- 20d minimum history before z-score is credible
- Daily fires during sustained intra-month moves (acceptable for
  warning-level)

### Neutral
- The 3-alert stack mirrors the GEOPOL pair (which only has 2 windows).
  Future sister-pair upgrades : DOLLAR_SMILE 252d, MACRO_QUARTET 252d.

## Alternatives rejected

### A — Multi-window list (30/90/252) on single service
Rejected per ADR-039 doctrine (duplication > premature abstraction).
Each window is its own alert with own AlertDef + own cron.

### B — Window 14d instead of 30d
Rejected. Too noisy. 30d is the canonical "intra-month" window per
Phase E convention.

### C — Severity info (matches 252d)
Rejected. 30d catches actionable events. info would under-signal.

### D — Skip in v1, defer
Rejected. Trinity completion has clear pattern-aligned doctrine.

### E — Cross-window composite gate (fire when 30d AND 90d aligned)
Rejected for v1. Adds complexity for marginal value. The trader can
easily see both fire concurrently.

## Implementation

Shipped wave 15 PR #55. Files :
- `apps/api/src/ichor_api/services/term_premium_intraday_check.py` (NEW, ~170 LOC)
- `apps/api/src/ichor_api/cli/run_term_premium_intraday_check.py` (NEW)
- `apps/api/tests/test_term_premium_intraday_check.py` (NEW, 13 tests)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend, bump assert 53 → 54)
- `scripts/hetzner/register-cron-term-premium-intraday-check.sh` (NEW)
- `docs/decisions/ADR-052-term-premium-intraday-30d-alert.md` (this file)

Catalog 53 → 54.

## Related
- ADR-009 Voie D (free FRED only)
- ADR-017 boundary preserved
- ADR-039 sister-pair doctrine (duplication > premature abstraction)
- ADR-041 TERM_PREMIUM_REPRICING (90d sister)
- ADR-045 TERM_PREMIUM_STRUCTURAL_252D (252d sister)
- Kim-Wright 10y term premium methodology
