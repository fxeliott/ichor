# ADR-012 — Market data via Stooq (primary) + yfinance (fallback)

- **Date** : 2026-05-03
- **Status** : Accepted
- **Decider** : autonomous Phase 1 burst (Eliot validated v2 plan)

## Context

Phase 1 work needs daily OHLCV bars for the 8 Phase-0 assets to :

1. Train and walk-forward-evaluate ML bias models
   (`packages/ml/model_registry.yaml` step #12).
2. Populate the `predictions_audit` hypertable so the Brier-degradation
   monitoring loop ([RUNBOOK-007](../runbooks/RUNBOOK-007-brier-degradation.md))
   has data to monitor.
3. Enrich briefing context with last-close + daily-change.

Eliot does not currently have an OANDA / Polygon / Alpaca paid key, and
the next budget review is post-Phase-1. We need a free-tier path that
unblocks all the above today.

## Decision

Two-adapter chain :

1. **Stooq** as primary
   ([`apps/api/src/ichor_api/collectors/market_data.py:20`](../../apps/api/src/ichor_api/collectors/market_data.py)) :
   - Direct CSV via HTTPS, no API key, no rate limit on documented usage.
   - Full historical coverage for FX majors / metals / cash indices since
     the 1980s.
   - Used by quants for decades, schema is stable.
   - Returns `Date,Open,High,Low,Close,Volume` per row.

2. **yfinance** as fallback
   ([`apps/api/src/ichor_api/collectors/market_data.py:140`](../../apps/api/src/ichor_api/collectors/market_data.py)) :
   - Used when Stooq is unreachable / serves truncated data.
   - Lazy-imported so the dep is optional in the Hetzner image.
   - Yahoo Finance terms allow daily personal use.

Storage : `market_data` TimescaleDB hypertable, partitioned on `bar_date`
with 90-day chunks. Composite PK `(id, bar_date)` for hypertable
compatibility, plus a `UNIQUE (asset, bar_date, source)` constraint so
re-runs are idempotent and we can keep multi-source-of-truth rows
side-by-side (planned for Phase 1 OANDA migration).

Cron : daily `ichor-market-data.timer` at 23:00 Paris (after every market
session has closed).

## Alternatives considered

- **Alpha Vantage free tier** : 25 calls/day. Insufficient for 8 assets
  during backfill (~150 calls). Could be useful for sub-daily intraday
  later — re-evaluate Phase 2.
- **Polygon free tier** : 5 calls/min, 2-year history limit, FX delayed
  by 15 min. Caps our backfill window painfully.
- **Quandl / Nasdaq Data Link** : free tier killed, paid only.
- **OANDA API** : requires an account with funds. Phase 0 budget excludes
  paid services (ADR-009 / Voie D logic), Phase 1 will revisit.
- **Self-scrape Yahoo Finance via raw HTTP** : same data as yfinance but
  more brittle, no benefit.
- **Build a single adapter** that picks the best source per asset class :
  premature optimization for Phase 1; stick to chain-of-fallback.

## Consequences

Positive :

- Zero Eliot intervention to start ingesting historical data.
- Walk-forward backtests can run today.
- `predictions_audit` activation path no longer blocked.
- Multi-source schema means an OANDA migration in Phase 1 is just a new
  source label — no backfill loss.

Negative :

- Daily resolution only. Microstructure features (VPIN, intraday vol)
  still wait on real intraday data — keep the
  `packages/ml/src/ichor_ml/microstructure/vpin.py` scaffold dormant
  until OANDA M1 lands.
- Stooq ToS technically asks for "personal use" — we're a single
  operator (Eliot), so this is fine for Phase 0/1 ; revisit if we ever
  expose the dashboard publicly with backtest workflows visible.
- yfinance fallback brings a pip dep heavier than ideal (~30 MB with
  pandas already installed). Marked optional in `pyproject.toml`.

## Verification

- 11 unit tests on `parse_stooq_csv` cover : CSV happy path, missing
  volume column, "No data" response, malformed header, blank body, mixed
  valid/invalid rows, source/fetched_at metadata, asset-mapping
  completeness for the 8 Phase-0 assets.
- Live smoke test : `python -m ichor_api.cli.run_collectors market_data`
  on Hetzner.

## References

- Stooq daily download URL pattern :
  `https://stooq.com/q/d/l/?s={ticker}&i=d`
- yfinance documentation :
  [pypi.org/project/yfinance](https://pypi.org/project/yfinance/)
- Migration : [`apps/api/migrations/versions/0003_market_data.py`](../../apps/api/migrations/versions/0003_market_data.py)
- ORM model : [`apps/api/src/ichor_api/models/market_data.py`](../../apps/api/src/ichor_api/models/market_data.py)
- Persistence helper : [`apps/api/src/ichor_api/collectors/persistence.py`](../../apps/api/src/ichor_api/collectors/persistence.py)
- CLI : [`apps/api/src/ichor_api/cli/run_collectors.py`](../../apps/api/src/ichor_api/cli/run_collectors.py)
