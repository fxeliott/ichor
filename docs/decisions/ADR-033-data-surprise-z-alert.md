# ADR-033: DATA_SURPRISE_Z alert wiring (Citi-style proxy on FRED)

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.a — first of the 8 dormant alerts
  earmarked for Phase D.5

## Context

ROADMAP §Phase D.5 lists 8 alertes manquantes for Phase 2's
"perfection absolue" cible. The first one — `DATA_SURPRISE_Z` — was
defined as :

> z-score deviation actual vs ForexFactory consensus pour NFP /
> CPI / Core PCE / ISM / JOLTS / Retail Sales / GDP advance

The textbook implementation is **Citi Eco Surprise** :

```
surprise_t = (actual_t - consensus_t) / std_consensus_t
```

with consensus pulled from Bloomberg / Refinitiv / Bloomberg-grade
calendar feeds. Two blockers in our setup :

1. **No free Bloomberg consensus feed** in 2026. Free options
   (ForexFactory weekly XML, JBlanked News API, Myfxbook) cover
   forecasts but not historical actuals + revisions in a clean
   structured form. Scraping the FF calendar HTML works but is
   fragile (CSS-class drift, captcha, rate limits).
2. **Wiring effort vs payoff** : a full Bloomberg-grade pipeline is
   ~6-8h of collector + service + tests. Payoff for a single-trader
   workflow is the _direction_ of the macro surprise, not its
   absolute calibration vs Bloomberg.

We already ship a **defensible proxy** :

```
proxy_t = (last_print - rolling_mean_24) / rolling_std_24
```

implemented in `services/surprise_index.py` (delta E of the 2026
vision brief), polarity-corrected so positive z-score always means
positive economic surprise (UNRATE inverted). It runs on 6 US
headliners (PAYEMS, UNRATE, CPIAUCSL, PCEPI, INDPRO, GDPC1) sourced
from FRED and is already fed to Pass 1 via `data_pool.py`.

## Decision

**Wire `DATA_SURPRISE_Z` to the existing surprise_index proxy** —
defer the Bloomberg-grade pipeline to a later ADR (D.5.a v2) when
the consensus-feed sourcing question is settled.

### Implementation

1. **Bridge service** `services/data_surprise_check.py` :
   - Calls `assess_surprise_index(session)` (the proxy).
   - For each constituent series with `|z| ≥ 2.0`, fires
     `check_metric("data_surprise_z", current_value=z, asset=series_id, ...)`
   - Source-stamps `extra_payload.source = f"FRED:{series_id}"` so
     Eliot can drill from the alert badge directly to the macro
     print that triggered it.
   - **Per-series, not composite** : firing on the average z would
     mask which constituent is screaming. The trader needs to see
     _PAYEMS surprise +2.31_ not _composite +1.4_.
2. **CLI runner** `cli/run_data_surprise_check.py` — daily Mon-Fri
   14h35 Paris cron (5 min buffer after the 14h30 / 08:30 ET US
   data release window). `--persist` opt-in pattern (consistent with
   RR25, FOMC tone, liquidity).
3. **Catalog entry** `AlertDef("DATA_SURPRISE_Z", ...)` in
   `alerts/catalog.py` — severity `warning`, metric_name
   `data_surprise_z`, default_threshold `2.0`, direction `above`.
   `assert_catalog_complete()` len bumped from 33 to 34.
4. **Tests** `tests/test_data_surprise_check.py` :
   - No alerts when all `|z| < 2.0`.
   - Alerts fire above threshold (positive AND negative side via
     `abs()`).
   - Source-stamping correctness (FRED:`<series_id>`).
   - `persist=False` suppresses `check_metric` (CLI dry-run contract).
   - Defensive single-source-of-truth test: bridge constant
     `ALERT_Z_ABS_FLOOR` matches catalog `default_threshold`.
5. **Cron** `scripts/hetzner/register-cron-data-surprise-check.sh` —
   Mon-Fri 14:35 Europe/Paris, `RandomizedDelaySec=180`.

### Boundary (ADR-017)

`DATA_SURPRISE_Z` is **macro context, not a trading signal**. The
alert says "the data printed far from the rolling distribution" ;
it does NOT recommend a direction. Eliot still chooses what to do
with the surprise — typically "DXY tends to rally on positive
surprise, fade on negative" but this is _trader interpretation_,
not Ichor output.

## Consequences

### Pros

- **Reuses existing infrastructure** : `surprise_index.py` is
  already in `data_pool.py`. The bridge is ~80 LoC.
- **Source-stamped** (ADR-017 invariant) : every alert payload
  carries `FRED:<series_id>` so the trader can immediately know
  which print drove it.
- **Polarity-corrected upstream** : UNRATE (and any future inverted
  series) flips sign in `surprise_index.py`, the bridge stays
  agnostic.
- **Per-series, not composite** : the trader sees the precise
  print that surprised, not the average.
- **CLI dry-run mode** : `--persist` opt-in matches the rest of the
  alert family and lets the runner be tested in CI without
  hitting the alert table.

### Cons

- **Proxy ≠ true Citi Surprise** : the rolling-distribution z-score
  captures _deviation from trend_ but doesn't separate "actual
  surprised vs consensus" from "trend itself moved". A series that
  has been steadily declining for 24 months will register no
  surprise on the next decline ; a Bloomberg-style (actual −
  consensus) framing would.
- **6 series only** (US-only) : doesn't cover EZ HICP, UK CPI,
  JP CPI, China CPI. ROADMAP D.5/D.7 plans a multi-region
  expansion when the BLS / ECB / BoE collectors land.
- **No retroactive calibration** : we never know whether a fired
  surprise actually moved the market. Could feed Brier later.

### Neutral

- The cron fires once per day. If multiple US headliners print on
  the same day (e.g. NFP + ISM Mfg), the runner picks them up at
  14h35 and may fire 2-3 alerts in one tick. This is by design —
  each alert carries the per-series source-stamp.

## Alternatives considered

### A — Full Bloomberg-grade pipeline (FF XML + FRED actual + std_consensus)

Rejected for now : 6-8h additional work, fragile to FF HTML drift,
and the per-trader payoff over the proxy is marginal (the _direction_
of surprise is what matters, the absolute calibration vs Bloomberg
is bookkeeping). To revisit if a clean Bloomberg-equivalent free feed
appears.

### B — Composite-only alert (single z per region)

Rejected : an average z hides which series surprised. Eliot needs
to see _PAYEMS +2.31_ directly, not _US composite +1.4_. The
catalog formatter `"Surprise macro {asset} z={value:+.2f}"` puts
the series_id front-and-centre.

### C — Per-asset alert (mapped to FX pairs)

Considered : map PAYEMS surprise to USD pairs etc. Tabled — adds
mapping complexity for marginal trader value. The series_id
already tells Eliot which currency is impacted (PAYEMS = USD,
INDPRO = USD, GDPC1 = USD ; future EZ/UK series would carry their
own region).

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/data_surprise_check.py` (NEW)
- `apps/api/src/ichor_api/cli/run_data_surprise_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with
  AlertDef + bump assert 33 → 34)
- `apps/api/tests/test_data_surprise_check.py` (NEW, 5 tests)
- `scripts/hetzner/register-cron-data-surprise-check.sh` (NEW)
- `docs/decisions/ADR-033-data-surprise-z-alert.md` (this file)

## Related

- ADR-017 — boundary contractual (no signal, just macro context).
- ADR-022 — Brier optimizer V2 (surprise direction could feed
  per-factor Brier as a Pass-1 driver, future).
- ADR-024 — five-bug fix (cron family — same Hetzner systemd path).
- ROADMAP D.5/D.7 — 7 alertes restantes (TARIFF_SHOCK,
  BOE_TONE_SHIFT, MEGACAP_EARNINGS_T-1, QUAD_WITCHING,
  REAL_YIELD_GOLD_DIVERGENCE, XCCY_BASIS_STRESS,
  SOVEREIGN_CDS_WIDEN).

## Followups

- Catalog ramp 34 → 41 as the other Phase D.5 alerts land.
- D.5.a v2 ADR when Bloomberg-grade consensus feed sourcing is
  resolved.
- Multi-region expansion (BLS/ECB/BoE collectors → EZ HICP,
  UK CPI, JP CPI surprise).
- `tests/test_alerts_runner_data_surprise.py` integration test
  once the audit table is migrated to a fixture (Phase A.7+).
