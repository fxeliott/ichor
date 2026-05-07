# ADR-035: QUAD_WITCHING + OPEX_GAMMA_PEAK proximity alerts

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.e

## Context

Two date-driven alert types that flag option-expiration calendar
events :

1. **Quad witching** — the four Fridays per year (3rd Friday of
   March / June / September / December) when stock-index futures,
   single-stock futures, stock-index options, and single-stock
   options ALL expire simultaneously. Volume routinely 2-3 ×
   normal ; dealer gamma re-pricing pops ; intraday volatility
   compresses then explodes ; SPX/NDX particularly sensitive.

2. **Monthly OPEX** — the 3rd Friday of every month (12 events per
   year). Smaller-scale than quad-witching but the same dealer-
   gamma-unwind dynamics. Friday-morning trading is meaningfully
   different from a "normal" Friday.

Both events are **purely calendar-driven** : they don't require
any data feed, market state, or external API call. Just the date.
Yet they're not currently surfaced in Ichor's alert catalog, which
means a trader looking at session cards on T-1 of a quad-witching
Friday sees no warning.

## Decision

Wire two new catalog alerts :

```
AlertDef("QUAD_WITCHING", info, "Quad-witching T-{value:.0f} ({asset})",
         "quad_witching_t_minus", 5, "below", ...)
AlertDef("OPEX_GAMMA_PEAK", info, "Monthly OPEX T-{value:.0f} ({asset})",
         "opex_t_minus", 2, "below", ...)
```

Both fire when `days_to_event <= threshold` (proximity flag).

### Implementation : pure Python date math

`services/quad_witching_check.py` :

- `_third_friday(year, month)` — walks day 1 forward to the first
  Friday, adds 14 days. Verified against CME/CBOE calendar for 2026
  (Mar 20, Jun 19, Sep 18, Dec 18) and 2027 (Jan 15).
- `next_quad_witching(today)` — scans current + next year (8 dates),
  returns earliest >= today. Handles year-overflow.
- `next_opex(today)` — current month's 3rd Friday if not yet past,
  else next month's. Handles December rollover.
- `evaluate_quad_witching_proximity(session, persist=True, today=None)` —
  computes both windows, fires `check_metric` per applicable alert,
  returns a structured result.

### Cron schedule

Daily 22h Paris (post NY close). Pure date check runs in < 1 second.
Daily slot keeps the alert state fresh as the calendar advances
toward each Friday.

### Threshold semantics

- `QUAD_WITCHING` threshold = 5 (days), direction "below" — fires
  when `days_to_event <= 5`.
- `OPEX_GAMMA_PEAK` threshold = 2 (days), direction "below" — fires
  when `days_to_event <= 2`.

The semantic is "T-N proximity counter" — value goes from 5 to 0 as
the event approaches.

### Source-stamping (ADR-017)

`extra_payload.source = "calendar:third_friday"`. Plus
`event_date` (ISO) and `days_to_event` so any audit consumer can
re-derive the alert from the date alone.

## Consequences

### Pros

- **Zero data dependency** : no FRED, no FF XML, no Polygon.
  Pure stdlib `datetime`. The alert can never fail due to a
  collector outage.
- **Trader-actionable T-1**: Eliot opens his pre-Londres briefing
  on a Thursday and sees "OPEX tomorrow" — adjusts his SL placement
  for Friday-morning gamma-driven moves.
- **Source-stamped + reproducible** : the alert payload contains
  the exact calendar date the alert was computed against. If a
  trader disputes the alert in 6 months, the audit log re-derives.
- **Cheap** : 12 OPEX alerts/year + 4 quad-witching alerts/year ×
  proximity windows ≈ ~50 alert-firings/year. Each is a single
  `check_metric` call.

### Cons

- **Calendar drift** : if CME ever changes the expiration calendar
  (e.g. shifts Friday → Thursday), our 3rd-Friday math becomes
  wrong. Probability ~ 0% in practice (the convention is locked
  globally), but the test suite pinning specific 2026/2027 dates
  guards against bugs.
- **Doesn't model magnitude** : the alert says "OPEX tomorrow", not
  "OPEX with peak gamma at $5800". A future enhancement could pull
  the SPX gamma surface (cf existing GEX_FLIP alert) and tag the
  OPEX event with expected dealer-gamma magnitude.
- **No regional OPEX** : European OPEX (Eurex) lives on the 3rd
  Friday too but settles different products (Euro Stoxx 50, DAX).
  Out of scope for v1 — Eliot trades mostly US indices.

### Neutral

- The cron fires daily even when no event is in window. This is by
  design (cheaper to run a 1-second no-op than to schedule
  conditionally on the calendar). The CLI prints a one-line
  "next_quad=... T-N next_opex=... T-N" status either way.

## Alternatives considered

### A — Single combined alert "OPTION_EXPIRY_WEEK"

Rejected : conflates quad-witching with monthly OPEX even though
they're different magnitudes. Trader needs to distinguish "huge
volume tomorrow" (quad) from "elevated gamma but not exceptional"
(monthly). Two alerts × two thresholds is the right granularity.

### B — Server-rendered SessionCard flag instead of catalog alert

Considered : add `is_opex_week: bool` to SessionCardOut. Tabled as
*addition not replacement* — the catalog alert path is the
universal trader-facing surface (audited, persisted, dashboardable).
A future enhancement could ALSO surface the flag on SessionCard
for a glance-without-alert UX.

### C — Hardcode the 2026 dates instead of computing third-Friday

Rejected : bumping the hardcoded list every January is exactly the
class of "human-forgets-to-update" bug we want to avoid. The
third-Friday rule is the source of truth, locked by CME/CBOE
convention.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/quad_witching_check.py` (NEW,
  ~140 LOC)
- `apps/api/src/ichor_api/cli/run_quad_witching_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with two
  AlertDefs + bump assert 35 → 37)
- `apps/api/tests/test_quad_witching_check.py` (NEW, 13 tests)
- `scripts/hetzner/register-cron-quad-witching-check.sh` (NEW)
- `docs/decisions/ADR-035-quad-witching-opex-alerts.md` (this file)

## Related

- ADR-017 — boundary contractual.
- ADR-033 — DATA_SURPRISE_Z (sister Phase D.5 alert).
- ADR-034 — REAL_YIELD_GOLD_DIVERGENCE (sister Phase D.5 alert).
- ROADMAP D.5/D.7 — 5 alertes restantes after this one
  (TARIFF_SHOCK, BOE_TONE_SHIFT, MEGACAP_EARNINGS_T-1,
  XCCY_BASIS_STRESS, SOVEREIGN_CDS_WIDEN).

## Followups

- Magnitude-aware OPEX (pull SPX gamma surface, tag with peak
  strike + dealer-gamma estimate).
- European Eurex OPEX flag (DAX, Euro Stoxx 50).
- SessionCard `is_opex_week` flag for in-card glance UX.
