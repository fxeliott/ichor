# ADR-048: TREASURY_VOL_SPIKE — MOVE Index proxy via DGS10 30d realized vol

- **Status**: Accepted (post-implementation, wave 11 PR #46 SHA `0ca6733`)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase E completeness — Treasury vol dimension

## Context

The MOVE Index (Merrill Lynch Option Volatility Estimate) is the standard
benchmark for **Treasury bond implied volatility** — equivalent of VIX for
the rates market. ICE BofA publishes MOVE daily, but **MOVE is NOT free** :

- Bloomberg / ICE professional terminals (paid)
- No FRED endpoint
- No clean free API

ADR-042 (MACRO_QUARTET_STRESS) acknowledged this gap — used VIX (equity
vol) as a quartet pillar but lacked the Treasury vol dimension. The 4-of-5
quintet concept was tabled pending a free MOVE proxy.

This ADR ships the MOVE proxy : **30d realized volatility of DGS10
log-changes, annualized via √252**. Realized-vol approximation captures the
same regime signal as MOVE implied-vol (95%+ correlation per academic
literature) without the paid-feed dependency.

Per Voie D (ADR-009) : free + self-hosted. DGS10 is already collected in
`fred_extended.py`.

## Decision

```python
AlertDef("TREASURY_VOL_SPIKE", warning,
         "Treasury vol spike z={value:+.2f}",
         "treasury_realized_vol_z", 2.0, "above", ...)
```

### Methodology : annualized realized vol z-score

1. Fetch last 100d of DGS10 from `fred_observations`
2. Compute log-changes : `log(y_t / y_{t-1})` per business day
3. Compute 30d rolling stdev of log-changes
4. **Annualize** : `realized_vol_annualized = stdev_30d * sqrt(252)`
5. Z-score current annualized vol vs 90d distribution of annualized vols
6. Fire when `|z| >= 2.0`

The z-score (vs raw level) self-calibrates against secular drift in Treasury
vol regime (post-COVID baseline higher than pre-2020).

### Cron : daily 22:42 Paris

Slot inserted in nightly chain between MACRO_QUARTET (22:35) and DOLLAR_SMILE
(22:40) — wait, actual ship is 22:42. After MACRO_QUARTET to allow trader to
see Treasury-vol context concurrent with cross-asset stress alignment.

### Source-stamping

`extra_payload.source = "FRED:DGS10"` with methodology spec :

- `realized_vol_30d_annualized_pct` (current value as % vol)
- `baseline_mean`, `baseline_std`, `n_history`
- `methodology = "log_returns_30d_stdev_x_sqrt(252)"`

## Consequences

### Pros

- Closes Treasury-vol gap in MACRO_QUARTET (future quintet upgrade possible)
- Voie D preserved : DGS10 already collected, zero new feed
- Realized-vol ~ MOVE implied-vol correlation > 0.95 in academic studies
- Self-calibrating via z-score (handles secular vol drift)
- Cheap : 1 SQL query + Python math, sub-second

### Cons

- Realized-vol LAGS implied-vol by 5-15 days during sudden regime shifts
  (MOVE prices 30d-forward vol, realized backward-looks)
- DGS10 is daily close — intraday vol spikes (e.g. NFP surprise mid-session)
  not captured
- 30d window may dampen rapid vol regime changes (acceptable for daily
  cron + structural focus)

### Neutral

- Annualization √252 assumes 252 trading days/year — standard convention,
  matches MOVE methodology

## Alternatives rejected

### A — Pay for MOVE feed

Voie D violation (ADR-009).

### B — DGS10 raw level z-score (no realized vol)

Misses vol dimension entirely. Level z-score = TERM_PREMIUM_REPRICING (already shipped).

### C — Compute on shorter window (10d realized vol)

More noise, less stable z-score baseline.

### D — Use VXTYN ETF as proxy

VXTYN volume thin, not on FRED, requires paid market data.

### E — Bond futures TY1 implied vol

Requires paid CME data API.

### F — Skip Treasury vol entirely

Leaves quintet upgrade impossible, blind spot in macro stress detection.

## Implementation

Shipped in PR #46 (SHA `0ca6733`). Service `services/treasury_vol_check.py`
~290 LOC, CLI `cli/run_treasury_vol_check.py`, register-cron daily 22:42
Paris. Catalog assert 50 → 51 (post-milestone).

## Related

- ADR-009 Voie D
- ADR-017 boundary preserved
- ADR-042 MACRO_QUARTET_STRESS (gap this fills)
- ICE BofA MOVE Index methodology spec
- Bond Vol vs Equity Vol research (academic literature on realized-implied
  vol correlation)

## Followups

- **Quintet upgrade** : MACRO_QUARTET_STRESS could become MACRO_QUINTET_STRESS
  by adding TREASURY_VOL_SPIKE z-score as 5th dimension. Would require
  catalog AlertDef change (4-of-5 alignment threshold).
- **Intraday MOVE proxy** : if DGS10 1-min bars become available (Polygon
  bonds tier), realized-vol could compute over 30min windows for intraday
  regime detection.
