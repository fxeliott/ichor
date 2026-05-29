# ADR-107 — EIA crude-stocks `supply_demand` theme driver (theme classifier 8/8)

- **Status**: Accepted (r191)
- **Date**: 2026-05-29
- **Supersedes / amends**: none (extends ADR-099 §theme_classifier ; mirrors the
  r189 `price_action_flow` enrichment pattern)
- **CI-guarded by**: `test_theme_classifier.py` (supply_demand driver tests) +
  `test_eia_crude_stocks_collector.py` + the W90 `test_invariants_theme_drivers_lockstep.py`
  (THEME_DRIVERS backend↔frontend lockstep — unchanged, `supply_demand` was already a member).

## Context

The theme classifier (Eliot Fathom transcript étape 1 — « identifier le thème
sous-jacent du marché ») scores 8 canonical drivers. Seven are data-driven
after r189 wired `price_action_flow` via VVIX/SKEW percentile. The 8th and
last — `supply_demand` (« offre/demande directe — impact majeur sur
commodities : pétrole production OPEC, or physique, agricultural ») — was still
hardcoded at `_BASELINE_STRENGTH = 0.2`, i.e. it could never become the
dominant theme. This ADR closes the classifier to **8/8 data-driven drivers**.

The repo already had a **fetch-only** EIA collector
(`collectors/eia_petroleum.py:fetch_weekly_petroleum_stocks`) hitting EIA
OpenData v2 `petroleum/stoc/wstk` — but no persistence, no model, no schedule,
and the theme classifier did not read it. The `eia_api_key` Settings field
exists (`config.py:133`) but EIA has **no anonymous tier**.

## Decision

1. **Persist** EIA weekly petroleum stocks: new ORM
   `EiaCrudeStockObservation` (table `eia_crude_stocks`, TimescaleDB hypertable)
   - migration **0054** (composite PK `(series_id, observation_date)` — the
     partition column must be in the PK for the hypertable ; CHECK `value >= 0`).
     Series: `WCESTUS1` (crude ending stocks), `WCRSTUS1` (commercial crude),
     `WTTSTUS1` (total products) — all stored, the driver reads `WCESTUS1`.
2. **Ingest** via `cli/run_eia_crude_stocks.py` (mirror `run_ecb_estr`):
   feature-flag `eia_crude_stocks_collector_enabled` (fail-closed), ON CONFLICT
   `(series_id, observation_date)` DO NOTHING, scheduled weekly Thursday 06:00
   Paris (post-WPSR Wed 10:30 ET) via `register-cron-eia-crude-stocks.sh`.
3. **Score** `supply_demand` via `_is_supply_demand_elevated`: the most-recent
   **absolute weekly change** in `WCESTUS1` (a build or a draw) at/above the
   **80th percentile** of |Δ| over a rolling **365-day** window → strength
   `0.7`, else baseline `0.2`. A large weekly inventory swing marks a
   supply/demand-driven regime (the commodity complex — oil, and via the
   dollar / real-yield channel, gold — is driven by physical balance rather
   than macro/policy). Reuses the shared `_value_above_percentile` (Doctrine #4
   SSOT) — self-calibrating, no fragile hardcoded barrel level (mirror r189).

   **Window rationale**: weekly data over 180d ≈ 25 Δ — below the shared
   `_MIN_PERCENTILE_HISTORY = 30` Cohen-1988 floor → would never trigger. 365d
   ≈ 52 weekly obs → ~51 Δ clears the floor with margin.

### ADR-017 boundary

Descriptive physical-balance **context**, never a trade signal. A crude build
above expectations is bearish for oil — a context input for Pass-2 narrative
framing, never an order, never BUY/SELL. The driver surfaces which moteur
dominates, not what to do.

### Voie D

Pure HTTPS GET against EIA OpenData v2. Zero LLM surface, zero `import
anthropic`. (ADR-009.)

## Consequences

- Theme classifier is **8/8 drivers data-driven**. No change to `THEME_DRIVERS`
  (the key already existed) → no frontend change, W90 lockstep stays green.
- **Live activation is Eliot-gated** (two one-time manual steps, no code):
  (1) `EIA_API_KEY` into Hetzner `/etc/ichor/api.env` (free registration,
  https://www.eia.gov/opendata/register.php — never commit the key) ;
  (2) flip `eia_crude_stocks_collector_enabled` true + register the cron +
  one-shot backfill `--last-n-obs 120`.
- **Graceful until data**: with no rows, `_is_supply_demand_elevated` returns
  False → baseline 0.2 → zero behaviour regression (same dormant-until-data
  pattern as Bund/€STR pre-activation). Doctrine #11 calibrated honesty.

## Citations / provenance

- **Primary**: Eliot Fathom transcript étape 1 (practitioner_stamp — the
  8-driver taxonomy is practitioner discipline, not a peer-reviewed enum).
- **Data source**: EIA OpenData v2, Weekly Petroleum Status Report (crude
  inventories, released Wed 10:30 ET). API docs: https://www.eia.gov/opendata/.
- Build > expected (inventory accumulation) = bearish oil is standard
  petroleum-market practitioner interpretation (descriptive, ADR-017).
