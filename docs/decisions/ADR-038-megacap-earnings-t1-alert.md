# ADR-038: MEGACAP_EARNINGS_T-1 alert — Mag-7 earnings proximity flag

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.f

## Context

The Magnificent 7 mega-caps (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)
are projected to account for ~27% of S&P 500 earnings power in 2026 (Zacks
Director of Research Sheraz Mian, May 2026). Each individual earnings
release reshapes a wide cone of cross-asset positioning :

- **SPX / NDX vol skew steepens** as dealers hedge gamma into the print
- **Single-stock IV explodes** (NVDA / TSLA routinely 8–15% post-earnings
  moves vs ~3% normal day)
- **USD complex repositions** : a soft Mag-7 print can drive USD-haven
  bid via risk-off rotation, or USD-funding sell-off if growth fears
- **Dealer gamma** can flip near at-the-money with EOM expirations
  coinciding with earnings weeks

A trader looking at session cards for SPX500 on the day before any one of
these reports needs an explicit T-1 advance warning — implicitly the
trader knows roughly when earnings season is coming, but the *specific
day* matters because the binary catalyst removes any rational pre-trade
positioning.

Ichor already has calendar-driven proximity flags for QUAD_WITCHING and
OPEX_GAMMA_PEAK (ADR-035). MEGACAP_EARNINGS_T-1 is the third entry in
that family — calendar-driven, asset-specific, fires at a defined T-N.

## Decision

Wire one new catalog alert :

```python
AlertDef("MEGACAP_EARNINGS_T_1", info,
         "Mag-7 earnings T-{value:.0f} ({asset})",
         "megacap_t_minus_days", 1, "below", ...)
```

Fires per-ticker when `days_to_event <= 1` (today or tomorrow).

### Implementation : yfinance live fetch

`services/megacap_earnings_check.py` :

- `MEGACAP_TICKERS = ("TSLA", "GOOGL", "MSFT", "META", "AAPL", "AMZN",
  "NVDA")` — ordered by typical Q-end reporting date (TSLA earliest in
  every cycle, NVDA latest by ~3 weeks because of its FY end-October
  fiscal year).
- `_fetch_next_earnings_date(ticker, *, today)` — calls
  `yfinance.Ticker(ticker).calendar` and returns the earliest future
  earnings date in the next 60 days (or None on any failure / stale data).
  Defensive try/except : Yahoo rate limits + transient network failures
  must NOT crash the alert run for the other 6 tickers.
- `evaluate_megacap_earnings(session, *, persist, today)` — iterate, fire
  per-ticker `check_metric` when proximity <= floor.
- `LOOKAHEAD_DAYS = 60` — avoids noise from announce-then-shift events
  while covering the typical Q-end + 3-week NVDA lag.

### Cron schedule

Daily 14h Paris (= 08:00 ET, post US pre-market). Mag-7 announce earnings
AFTER market close (~16:00 ET / 22:00 Paris) so a 14:00 Paris daily run
gives the trader a full session of advance notice before the catalyst.

### Threshold rationale

`EARNINGS_PROXIMITY_FLOOR = 1` (T-0 or T-1). At T-2+, vol skew is already
priced in and pre-trade positioning is rational ; at T-1 the binary
becomes acute. T-0 (= today) is also flagged because some traders who
hedge intraday want the day-of warning in the morning briefing.

The semantic on the metric is "T-N proximity counter" : value goes from
1 → 0 as the day of approaches. Same shape as QUAD_WITCHING / OPEX_GAMMA_PEAK
catalog entries (proximity counters with `default_direction="below"`).

### Asset semantics : `asset = ticker`

Per-ticker alert. The trader needs to know *which* Mag-7 reports tomorrow
(MSFT skew is different from NVDA skew). Aligns with single-ticker alerts
like `USDJPY_INTERVENTION_RISK` and `XAU_BREAKOUT_ATH`. The alert fires
up to 7 times in a single Q (one per Mag-7 ticker) but spread over ~10 days
of reporting season — well below catalog dedup window.

### Source-stamping (ADR-017)

`extra_payload.source = "yfinance:earnings_calendar"`. Plus :

- `ticker`
- `earnings_date` (ISO)
- `days_to_event` (int)
- `fetched_at` (ISO timestamp of the yfinance fetch — for audit)

Source resilience : if yfinance fails, the ticker is silently skipped
and logged WARNING. The alert payload makes the source explicit so any
audit consumer can re-derive (or flag) a stale calendar.

## Consequences

### Pros

- **Trader-actionable** : T-1 advance on a binary catalyst is the most
  asymmetric warning in the catalog (binary outcomes have ~5–8× the vol
  of an average trading day).
- **Per-ticker drill-back** : `asset` field in the Alert ORM row lets
  the trader filter on `MEGACAP_EARNINGS_T_1 WHERE asset='NVDA'`.
- **Calendar-driven, deterministic** : the alert reflects company-confirmed
  schedules. No ML, no statistical inference — same low-noise principle
  as QUAD_WITCHING.
- **Reuses existing yfinance install** on Hetzner (1.3.0 already in
  /opt/ichor/api/.venv from Phase 1 collectors). Zero new dependency.
- **Cheap** : 7 yfinance calls/day × ~150ms each = ~1s total. Daily slot
  keeps the alert state fresh.

### Cons

- **yfinance reliability** : Yahoo rate limits, occasional 5xx, schema
  drift across yfinance versions. Mitigation : per-ticker try/except,
  None-tolerant evaluation, structured logging via WARNING for ops
  monitoring. Multi-failure detection deferred to `/metrics`
  `prometheus-fastapi-instrumentator` + journald (already wired Phase A.4).
- **Mag-7 only** : doesn't cover sub-Mag-7 mega-caps (META Platforms +
  TSM + Berkshire + Eli Lilly, etc.) that also drive material market
  moves. v2 could expand the ticker list. v1 sticks with Mag-7 because
  of the clean S&P 500 earnings concentration argument (27%).
- **No event categorization** : alert says "earnings tomorrow" not
  "expected vol +18% based on options skew". A future enhancement could
  pull the SPX/NDX gamma surface (cf existing GEX_FLIP alert) and tag
  the earnings event with expected dealer-gamma magnitude.

### Neutral

- Alert fires up to 7 times per Q (one per Mag-7 ticker on its own T-1).
  The 2h dedup window in `alerts_runner.check_metric` prevents intra-day
  re-fire spam (the cron fires daily, so each ticker has a fresh dedup
  window every 24h regardless).

## Alternatives considered

### A — Hardcode 2026 earnings calendar in a Python const

Considered : maintenance burden of refreshing 7 tickers × 4 quarters = 28
date entries quarterly. Rejected because companies sometimes shift
confirmed dates within a 1-week window (timing of post-market call slot
availability), and a hardcoded list would silently drift. Live yfinance
is the source of truth.

### B — Use a dedicated earnings-calendar collector with persistent table

Tabled (not rejected) for v2 : a new `earnings_calendar` table populated
by a weekly collector would decouple the alert from Yahoo's availability.
Adds complexity (new table + migration + collector + tests) for a marginal
robustness gain. v1 keeps the simpler live-fetch path.

### C — Single combined alert "EARNINGS_SEASON_NOW"

Rejected : conflates "Mag-7 reports tomorrow" with "30 random S&P 500
companies report this week". Trader needs single-ticker resolution
because individual binary catalysts are what move SPX skew, not the
volume of small-cap reports.

### D — Fire at T-3 instead of T-1 for more advance notice

Rejected : at T-3, vol skew is already steepening and dealer gamma is
adjusted ; an alert there would amplify positioning rather than enable
positioning. T-1 is the binary moment where pre-trade positioning still
has actionable optionality (close out / hedge).

### E — Asset list extended beyond Mag-7 (NFLX, BRK.B, JPM, LLY, AVGO,
ADBE, V, MA, JNJ, PG, KO, XOM)

Tabled for v2 : reasonable case for "Mag-12" or "Top S&P EW20". v1 is
deliberately scoped to the 7-ticker concentration argument. Easy to
extend the `MEGACAP_TICKERS` tuple in v2 once we observe trader demand
for non-Mag-7 earnings alerts.

### F — Pull from Polygon/Massive `/v1/reference/earnings` endpoint

Polygon Massive Currencies plan ($49/mo) does not include earnings data.
Would require Stocks plan ($29/mo) or higher. yfinance is free and
already installed — net cost-zero for v1.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/megacap_earnings_check.py` (NEW, ~210 LOC)
- `apps/api/src/ichor_api/cli/run_megacap_earnings_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 39 → 40)
- `apps/api/tests/test_megacap_earnings_check.py` (NEW, ~10 tests)
- `scripts/hetzner/register-cron-megacap-earnings-check.sh` (NEW)
- `docs/decisions/ADR-038-megacap-earnings-t1-alert.md` (this file)

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-035 — QUAD_WITCHING + OPEX_GAMMA_PEAK (sister calendar-driven
  proximity alerts, same `default_direction="below"` semantic).
- ADR-033 — DATA_SURPRISE_Z (sister Phase D.5 macro alert).
- Zacks Director of Research Sheraz Mian, "Mag-7 Earnings Spotlight"
  (Yahoo Finance, May 2026).
- Wall Street Horizon, "Magnificent 7 Earnings Tariff Concerns" (2026).

## Followups

- v2 : weekly earnings-calendar collector populating
  `earnings_calendar` table (decouple alert from Yahoo availability).
- v2 : magnitude-aware MEGACAP (pull SPX/NDX gamma surface, tag with
  expected vol % and dealer gamma flip risk).
- v2 : extend ticker list beyond Mag-7 (NFLX, BRK.B, JPM, LLY, etc.).
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  consensus EPS / revenue at alert time and produce a 1-paragraph
  binary risk narrative (expected miss vs beat asymmetry).
