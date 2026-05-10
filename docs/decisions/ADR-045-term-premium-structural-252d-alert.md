# ADR-045: TERM_PREMIUM_STRUCTURAL_252D — long-window companion to TERM_PREMIUM_REPRICING

- **Status**: Accepted (post-implementation, wave 9 PR #42 SHA `eec121c`)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP E.2 sister (structural)

## Context

ADR-041 ratified TERM_PREMIUM_REPRICING (KW 10y term premium z-score, 90d
window, severity warning). The 90d window catches narrative-shift episodes
(auction tail, debt-ceiling, FOMC surprise) but **dampens slow-build regimes**
where term premium climbs steadily over months — the 90d baseline catches
up and the relative z-score shrinks even as absolute level rises.

2026 macro context : Trump fiscal expansion + Fed independence questions +
foreign reserve diversification = **multi-year term premium expansion arc**
(2025-2027 forecast per Hartford / SSGA / NY Life / Forex.com 2026 outlooks).
A 90d-only alert would silently miss the structural shift.

This is the same problem GEOPOL_FLASH (30d) faced vs GEOPOL_REGIME_STRUCTURAL
(252d) — solved in ADR-039 with a sister long-window alert.

## Decision

Wire one new catalog alert :

```python
AlertDef("TERM_PREMIUM_STRUCTURAL_252D", info,
         "Term premium structural shift z={value:+.2f}",
         "term_premium_z_252d", 2.0, "above", ...)
```

Window : 252d (1 trading year). Threshold : `|z| >= 2.0` aligned with sister
acute alert.

### Severity rationale : `info` (not `warning`)

Per the GEOPOL_FLASH (warning) / GEOPOL_REGIME_STRUCTURAL (info) pattern :
acute 90d signal is actionable, structural 252d signal is **context flag**
for the trader's regime call. Chaining info-level alerts into the session
card gives the trader the macro regime stamp without spamming warning-level
escalations.

### Implementation : code reuse from TERM_PREMIUM_REPRICING

`services/term_premium_structural_check.py` duplicates ~80 LOC from
`term_premium_check.py` (per ADR-039 doctrine "duplication > premature
abstraction") with three diffs :

- `ZSCORE_WINDOW_DAYS = 252` (vs 90)
- `_MIN_ZSCORE_HISTORY = 180` (warmup floor on 252d window)
- `metric_name = "term_premium_z_252d"` (distinguishes from sister)

### Cron schedule : weekly Sunday 22:15 Paris

Slow signal — daily eval is overkill. Sunday slot avoids weekend FRED
publication gaps. 22:15 = post FRED extended collector at 18:30 + 4h buffer.

### Source-stamping

`extra_payload.source = "FRED:THREEFYTP10"` with `window_days=252` for audit
re-derivation distinct from FLASH alert (which uses same series but
window=90).

## Consequences

### Pros

- Closes structural-blind-spot gap of TERM_PREMIUM_REPRICING (acute only)
- Reuses existing FRED collector (zero new infrastructure)
- Pattern-aligned with GEOPOL pair (proven)
- info severity = no alert spam during multi-year expansion

### Cons

- Duplication ~80 LOC vs sister service (deliberate per ADR-039)
- Warmup 180d before z-scores are credible

## Alternatives rejected

- **A: Multi-window list (30/90/252) on single service** — premature
  abstraction, unclear when to deduplicate fires.
- **B: Skip structural** — leaves blind spot.
- **C: Severity warning** — over-fires during multi-year regimes.

## Implementation

Shipped in PR #42 (SHA `eec121c`). 10 tests, register-cron weekly Sun 22:15
Paris. Catalog assert bumped 47 → 48.

## Related

- ADR-017 boundary preserved
- ADR-039 (sister GEOPOL pair pattern)
- ADR-041 (acute companion TERM_PREMIUM_REPRICING)
