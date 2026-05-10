# ADR-044: VIX_TERM_INVERSION alert — VIXCLS / VXVCLS backwardation detector

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP E (innovations) — vol-of-vol detector

## Context

The VIX (VIXCLS) measures 30-day implied volatility on SPX options.
The VXV / VIX3M (VXVCLS) measures 90-day implied volatility on the
same option chain. Their ratio :

```
ratio = VIXCLS / VXVCLS
```

defines the **VIX term structure** :

- **ratio < 1.0** : _contango_ (longer-dated vol prices higher than
  near-term — normal calm regime, bull-market default)
- **ratio ≈ 1.0** : _neutral_ (transition zone, typically 0.95-1.00)
- **ratio > 1.0** : _backwardation_ (near-term vol exceeds longer-dated
  — fear is _imminent_, not 3 months out)
- **ratio > 1.05** : _vol-shock_ (steep inversion, panic/capitulation)

VIX backwardation is **rare** and historically tracks major stress
episodes :

- 2008 GFC
- 2011 US debt downgrade
- August 2015 China yuan devaluation
- February 2018 Volmageddon
- Late-2018 sell-off
- March 2020 COVID crash

Empirical research (Macrosynergy 2010-2017 ; QuantSeeker analyses)
shows that inverted VIX curves have a **SIGNIFICANT positive relation
with subsequent S&P 500 returns**. The inversion marks panic /
capitulation moments which often coincide with near-bottoms. The
April 2020 ratio drop back below 1.0 marked the durable COVID-bottom
all-clear in 2020.

For Ichor's pre-trade context engine, this alert flags when the
trader should :

- Reduce dip-buying aggression (bear-market overnight gap risk
  elevated)
- Increase intraday range expectations (higher vol velocity, larger
  gaps)
- Watch for all-clear when ratio drops back below 1.0 (durable
  bottom marker)

The classic VIX*SPIKE alert (already in catalog) fires on absolute
VIX level > 25. But VIX 25 with VIX-3M 30 is \_not* the same regime
as VIX 25 with VIX-3M 22 — the term structure tells you which
direction the _expected_ path goes. Adding VIX_TERM_INVERSION
captures the term-structure dimension that VIX_SPIKE alone misses.

## Decision

Wire one new catalog alert :

```python
AlertDef("VIX_TERM_INVERSION", warning,
         "VIX term backwardation ratio={value:.4f}",
         "vix_term_ratio", 1.0, "above", ...)
```

Fires when `ratio = VIXCLS / VXVCLS > 1.0`.

### Implementation : pure ratio computation

`services/vix_term_check.py` :

- `_fetch_latest(session, *, series_id)` — pull last VIXCLS + VXVCLS
  observation each (within 14d cutoff for freshness).
- `_classify_regime(ratio)` → 4-tier tag :
  - `backwardation_shock` (ratio >= 1.05)
  - `backwardation` (ratio >= 1.00)
  - `neutral` (0.95 - 1.00)
  - `contango` (ratio < 0.95)
- `evaluate_vix_term_inversion(session, *, persist)` — orchestrate,
  fire `check_metric` when ratio crosses inversion floor.

### Threshold rationale

`>= 1.0` is the canonical inversion threshold per industry convention
(Cboe, vixcentral, Macrosynergy). The level-based threshold is
intrinsic (not relative to a rolling baseline) because the term
structure has a **well-defined economic interpretation** at 1.0 :
near-term IV exceeds longer-dated IV. Z-score normalization would
add complexity without value — the level is the signal.

Secondary `>= 1.05` `vol_shock` tag is informational (exposed in
payload + regime field). Steep inversions are rarer + more
trader-actionable.

### Regime tag direction

| Ratio     | Regime              | Trader implication                                |
| --------- | ------------------- | ------------------------------------------------- |
| < 0.95    | contango            | Normal calm regime, dip-buying ok, lower gap risk |
| 0.95-1.00 | neutral             | Transition, no signal                             |
| 1.00-1.05 | backwardation       | Near-term stress, reduce dip-buying, expect gaps  |
| ≥ 1.05    | backwardation_shock | Panic/capitulation, watch for all-clear bottom    |

Only `backwardation` and `backwardation_shock` fire the alert. Trader
implementation : the `regime` payload field lets the trader
distinguish levels.

### Source-stamping (ADR-017)

`extra_payload.source = "FRED:VIXCLS+VXVCLS"`. Plus :

- `vix_1m` / `vix_3m` (raw IV values)
- `ratio` (computed)
- `vix_1m_date` / `vix_3m_date` (ISO observation dates for audit)
- `regime` (4-tier tag)
- `is_vol_shock` (bool, ratio >= 1.05)

### Cron schedule

Daily 22:45 Paris. Part of the nightly macro alert chain :

- 22:30 — TERM_PREMIUM_REPRICING
- 22:35 — MACRO_QUARTET_STRESS
- 22:40 — DOLLAR_SMILE_BREAK
- **22:45 — VIX_TERM_INVERSION** (this alert)

All 4 alerts feed off the FRED extended collector at 18:30 Paris (4h
buffer for KW + IV publication latency).

## Consequences

### Pros

- **Closes the term-structure dimension** missed by VIX_SPIKE alone.
  Catches the SHAPE of vol expectations, not just the absolute level.
- **Contrarian signal grounded in research** : Macrosynergy 2010-2017
  empirical analysis shows inverted curves predict positive subsequent
  SPX returns (panic = near-bottom).
- **Reuses existing FRED collector** : both VIXCLS + VXVCLS already
  in EXTENDED_SERIES_TO_POLL.
- **Simple + interpretable** : 1 ratio, 1 threshold, 4 regimes. No
  z-score complexity.
- **Cheap** : 2 SQL queries (latest each) + 1 division. Sub-second
  per execution.
- **Bidirectional via regime tag** : even when contango (no fire), the
  CLI prints the regime + ratio for operator visibility into the
  vol-curve state.

### Cons

- **Single-day reading** : the alert fires on TODAY's ratio without
  smoothing. A 1-day spike could fire then immediately reset. Mitigation
  acceptable : the alert is meant to flag the moment of inversion, not
  the duration. Sustained backwardation = repeated daily fires through
  dedup.
- **Level-only** : doesn't normalize against historical distribution.
  In structurally-elevated-vol regimes (e.g. mid-2025 if it had
  happened), the 1.0 threshold may be reached more often than in
  ultra-tight 2017 regimes. Mitigation : the threshold is intrinsic
  (not relative) so this is BY DESIGN — economic interpretation at
  1.0 is regime-invariant.
- **No futures-curve depth** : real VIX futures curves have 1M, 2M, 3M,
  ... 9M points. This alert uses only spot 1M (VIX) + spot 3M (VXV) —
  loses the granularity of mid-curve dynamics. Mitigation : v2 could
  pull VIX futures from a paid feed (Bloomberg/Cboe) and compute
  multi-point curve features.

### Neutral

- The cron fires daily even when contango (no alert). CLI prints the
  regime status either way for operator visibility into vol-curve
  state evolution over time.

## Alternatives considered

### A — Use absolute VIX level (VIX_SPIKE) only

Rejected : VIX_SPIKE catches LEVEL but not term-structure shape. VIX 25
with VXV 30 (contango) is fundamentally different from VIX 25 with VXV
22 (backwardation). The term-structure signal is independent of and
complementary to the level signal.

### B — Z-score the ratio against rolling baseline

Considered : would handle structural regime shifts in vol baseline.
Rejected for v1 because the level-based 1.0 threshold has a well-
defined economic interpretation (mathematical inversion of term
structure). Z-score would obscure this. v2 could add a _companion_
z-score alert if needed.

### C — Use VIX futures spread (M1 - M2) instead of spot ratio

Rejected : VIX futures aren't on FRED ; would require Bloomberg or
Cboe paid feed (Voie D violation). Spot VIX (VIXCLS) + spot VXV
(VXVCLS) are FRED-hosted free. Acceptable proxy for the term-structure
shape because they price the same option chain at different
maturities.

### D — Multi-tier alerts (CONTANGO_DEEP, BACKWARDATION_SHOCK distinct)

Tabled (not rejected) for v2 : separate alerts for steep contango (e.g.
ratio < 0.85, ultra-complacency) and vol-shock (ratio > 1.05) would
add granularity. v1 keeps a single alert with tagged regimes ; the
trader inspects payload to distinguish.

### E — Smooth the ratio (5d EMA before threshold check)

Rejected for v1 : adds parameter (smoothing window) without clear
benefit. The 2h dedup window in `alerts_runner.check_metric` already
prevents intraday re-fire spam ; smoothing would delay genuine
inversions.

### F — Combine with VIX absolute level (e.g. ratio > 1.0 AND VIX > 25)

Rejected for v1 : would silence the alert when VIX is moderate (e.g.
VIX 22, VXV 20 = ratio 1.10) which is actually a meaningful inversion
even at low absolute vol. Independent term-structure signal preserved.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/vix_term_check.py` (NEW, ~180 LOC)
- `apps/api/src/ichor_api/cli/run_vix_term_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 46 → 47)
- `apps/api/tests/test_vix_term_check.py` (NEW, 14 tests)
- `scripts/hetzner/register-cron-vix-term-check.sh` (NEW, daily
  22:45 Paris)
- `docs/decisions/ADR-044-vix-term-inversion-alert.md` (this file)

No new collector — both VIXCLS + VXVCLS already polled by
`fred_extended.py`.

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-009 — Voie D (free + self-hosted, no paid feeds).
- ADR-041 — TERM_PREMIUM_REPRICING (sister term-structure alert in
  Treasury space).
- ADR-042 — MACRO_QUARTET_STRESS (sister composite, includes VIX as
  one dim ; this alert adds the term-structure dimension that the
  quartet level-based stress check doesn't capture).
- ADR-043 — DOLLAR*SMILE_BREAK (sister composite, uses VIX-low as one
  condition ; this alert adds the \_direction-of-VIX-curve* check).
- Macrosynergy. "VIX term structure as a trading signal." Empirical
  2010-2017 analysis : inverted curve = positive SPX 1M-forward.
- QuantSeeker. "Timing volatility with the VIX term structure."
- Cristian Velasquez (Medium). "Detecting VIX term structure regimes."
- Cboe Tradable Products. VIX Term Structure documentation.
- vixcentral.com — live VIX term structure data source.

## Followups

- v2 : add a CONTANGO_DEEP alert (ratio < 0.85 ultra-complacency
  warning).
- v2 : pull VIX futures M1-M9 from Cboe DataShop (paid) for full curve
  features (slope, curvature, butterfly).
- v2 : combine with realized vol (10d EWMA on SPX returns) for
  IV-vs-RV gap detector (volatility risk premium).
- Phase E.5 : feed `vix_term_ratio` as Brier V2 driver feature
  (regime-aware probability calibration).
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  current VIX curve narrative at alert time (recent fund positioning,
  upcoming macro catalysts) and produce a 1-paragraph regime
  attribution.
