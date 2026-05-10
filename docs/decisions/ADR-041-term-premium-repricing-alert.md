# ADR-041: TERM_PREMIUM_REPRICING alert — KW 10y term premium z-score

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP E.2 (Phase E innovations)

## Context

The 10-year Treasury yield decomposes into two parts :

```
DGS10 = expected_path_short_rates + term_premium_10y
```

Where `term_premium_10y` is the additional yield investors demand for
holding duration risk over rolling shorter-term Treasuries. This is a
**latent variable** — not directly observable — estimated via affine
no-arbitrage term-structure models from yield-curve dynamics + survey
data.

Two main models compete in academia / practice :

- **Kim-Wright (KW)** — 3-factor, incorporates Blue Chip survey of short-
  rate expectations. Hosted on FRED as `THREEFYTP10`.
- **Adrian-Crump-Moench (ACM)** — 5-factor, no surveys. Hosted on NY
  Fed website as `ACMTP10`.

Per Federal Reserve note 2017-04-03 ("Robustness of long-maturity term
premium estimates"), KW and ACM agree to within bps once survey-rate-
expectations are matched. We adopt **KW** because it's free, daily, and
already accessible via the FRED API our collector uses.

### 2026 macro context — why now

Per multiple 2026 outlooks (Hartford, SSGA, NY Life, Forex.com), term
premium is **expanding** in 2026 driven by :

- Trump-administration fiscal expansion (deficit + debt ceiling drama)
- Fed independence questions (replacement chair nominee Trump-aligned)
- Foreign reserve diversification (USD-debasement narrative)
- Treasury auction tail surprises (record supply + tepid demand)

The result is a **disconnect** between front-end policy (Fed cutting
rates) and long-end yields (term premium widening). This drives :

- **Mortgage rates stay elevated** despite Fed cuts (housing inflation)
- **Gold rallies** on debasement narrative (J.P. Morgan target $5,055/oz Q4 2026)
- **DXY weakens** despite higher US yields (foreign holders demand higher term premium → bonds sell off)
- **EUR/USD** range-bound as ECB faces same fiscal pressure

A z-score-based alert flags the **moment of repricing**, not the
absolute level. A +2σ expansion against a 90d baseline catches narrative
shifts (fiscal-cliff fears, auction tail surprises, debt-ceiling
drama) ; a -2σ contraction catches the reverse (flight-to-quality
bond bid).

## Decision

Wire one new catalog alert :

```python
AlertDef("TERM_PREMIUM_REPRICING", warning,
         "Term premium repricing z={value:+.2f}",
         "term_premium_z", 2.0, "above", ...)
```

Fires when `|z| >= 2.0` against trailing 90d distribution.

### Implementation : pure FRED + Python z-score

`services/term_premium_check.py` :

- `_fetch_recent_observations(session, *, days=104)` — pulls 90 + 14d
  buffer from `fred_observations` WHERE series_id='THREEFYTP10'.
- `_zscore(history, current)` — defensive : returns `None` below
  `_MIN_ZSCORE_HISTORY = 60` ; returns `(None, mean, std)` if std==0.
- `evaluate_term_premium_repricing(session, *, persist)` — orchestrate,
  fire `check_metric` only when threshold crosses.
- `_classify_regime(z)` → 'expansion' | 'contraction' | '' for tagging.
- `_assets_for_regime(regime)` → list of trader-actionable assets per
  regime (XAU_USD/DXY/MORTGAGE/EUR_USD/USD_JPY for expansion ;
  DGS10/DXY/USD_JPY/HY_OAS for contraction).

### Collector extension

`collectors/fred_extended.py` `EXTENDED_SERIES_TO_POLL` extended with
`THREEFYTP10`. The collector `ichor-collector-fred_extended.timer`
polls FRED daily at 18:30 Paris (already wired Phase 0+).

### Cron schedule

Daily 22:30 Paris. FRED THREEFYTP10 is published with ~1-day latency
(Kim-Wright model is technically weekly-updated but the FRED feed
reflects the latest within hours of release). The 22:30 slot gives
a 4h buffer post the 18:30 Paris collector run.

### Threshold rationale

`|z| >= 2.0` matches the catalog convention shared with DATA_SURPRISE_Z,
REAL_YIELD_GOLD_DIVERGENCE, GEOPOL_FLASH, GEOPOL_REGIME_STRUCTURAL,
TARIFF_SHOCK. 2σ on a 90d window = ~1-in-20 day under approximate
normality — rare enough to avoid fatigue, common enough to be
informative for a slow-moving signal.

The 90d window (vs 252d for GEOPOL_REGIME) is a deliberate trade-off :

- 30d would chase noise (term premium has positive autocorrelation
  intra-month)
- 90d catches narrative-shift episodes (fiscal-cliff, auction tail,
  debt-ceiling) without absorbing structural drift
- 252d would dampen the kind of repricing this alert is meant to catch
  (the structural variant could be added in v2 as a sister alert
  similar to GEOPOL_FLASH + GEOPOL_REGIME_STRUCTURAL pair)

### Source-stamping (ADR-017)

`extra_payload.source = "FRED:THREEFYTP10"`. Plus :

- `term_premium_pct` (raw FRED value, e.g. 0.45 = 45 bps)
- `term_premium_bps` (derived \* 100 for trader display)
- `term_premium_date` (ISO)
- `baseline_mean` / `baseline_std` / `n_history`
- `regime` ('expansion' | 'contraction')
- `assets_likely_to_move` (trader drill-back list)

## Consequences

### Pros

- **Trader-actionable** : term premium expansion is the signal of fiscal-
  stress macro regime — directly drives gold + DXY + mortgage rates.
- **Reuses existing FRED collector** — only adds 1 series to
  EXTENDED_SERIES_TO_POLL ; zero new infrastructure.
- **Self-calibrating** : 90d rolling z-score absorbs steady-state level
  shifts. Catches _acceleration_ not absolute value.
- **Bidirectional** : `default_direction="above"` on `|z|` — catches
  both expansion (z > 0, fiscal stress) and contraction (z < 0, flight-
  to-quality). regime tag distinguishes them in payload.
- **Cheap** : 1 SQL query + 90 numbers averaged. Sub-second per execution.

### Cons

- **KW vs ACM methodology disagreement** : the two models can diverge by
  hundreds of bps in stress periods. Mitigation : document the choice
  (KW = FRED-hosted, free, accepted by Federal Reserve note as ~equivalent
  to ACM modulo survey calibration). v2 could add ACM cross-check by
  scraping NY Fed website.
- **THREEFYTP10 update cadence** : Kim-Wright updates weekly nominally
  but FRED feed within hours. Z-score on daily readings may show small
  jumps on update days. Acceptable noise — the 60d minimum history
  smooths it.
- **No event categorization** : "term premium repricing" is one signal,
  not "auction tail vs debt-ceiling vs Fed-independence." A future
  enhancement could cross-reference with GDELT 'fiscal' / 'debt' / 'auction'
  keyword bursts for narrative attribution.
- **Fresh data warmup** : on first deploy, the 60d history minimum
  means the alert no-ops for ~2 months until FRED THREEFYTP10
  accumulates enough rows. Structured note ("insufficient history") is
  the dry-run output until then.

### Neutral

- The cron fires daily even when no spike. The CLI prints
  "term_premium=X% baseline=Y±Z z=W (regime=...)" status either way for
  operator visibility.

## Alternatives considered

### A — Use ACM directly via NY Fed scraping

Tabled (not rejected) for v2 : technically defensible (ACM is the
preferred academic series), operationally costly (new HTTP scraper +
parser + freshness checks). v1 ships with KW (free, FRED-hosted, ~bps-
equivalent to ACM per Fed note 2017).

### B — Multi-window stack (30d + 90d + 252d) like GEOPOL_FLASH +

GEOPOL_REGIME

Tabled for v2 : richer signal but multiplies analytic surface. v1 starts
with 90d. v2 could add 252d structural companion if Eliot finds gap.

### C — Threshold on absolute level (e.g. >100 bps)

Rejected : term premium has secular drift (~+0.45% in 2024-2025, ~+0.85%
mid-2026 per forecasts). Fixed level threshold would over-fire in
expansion regime then under-fire as baseline catches up. Z-score
self-calibrates.

### D — Weekly cron (matching KW model update cadence)

Rejected : market reactions to term premium repricing happen intraday
(auction days, FOMC press conferences). Daily check ensures the alert
reflects fresh KW data within ~24h of release. Acceptable to
occasionally alert on a no-update day (the z-score doesn't move much
between updates).

### E — Cross-reference with DGS10 raw (level + delta)

Considered : DGS10 already has daily collection. The decomposition into
expected_path + term_premium is the value-add ; otherwise we'd just
alert on raw DGS10 jumps which is noisy. Term premium isolates the
duration-risk component.

### F — Skip THREEFYTP10 collector extension, use external API call

Rejected : violates Voie D principle of free + self-hosted. FRED is
free and we already have a collector — adding 1 series to the polling
list is negligible.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/collectors/fred_extended.py` (+1 series:
  THREEFYTP10)
- `apps/api/src/ichor_api/services/term_premium_check.py` (NEW, ~250 LOC)
- `apps/api/src/ichor_api/cli/run_term_premium_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 43 → 44)
- `apps/api/tests/test_term_premium_check.py` (NEW, 12 tests)
- `scripts/hetzner/register-cron-term-premium-check.sh` (NEW, daily
  22:30 Paris)
- `docs/decisions/ADR-041-term-premium-repricing-alert.md` (this file)

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-009 — Voie D (free + self-hosted, no paid feeds).
- ADR-034 — REAL_YIELD_GOLD_DIVERGENCE (sister 2-series rolling-corr
  alert on FRED-hosted DFII10 + GOLDAMGBD228NLBM).
- ADR-039 — GEOPOL_REGIME_STRUCTURAL (sister z-score alert on a
  longer 252d window).
- Adrian, Tobias, Richard K. Crump, and Emanuel Moench (2013).
  "Pricing the term structure with linear regressions." _Journal of
  Financial Economics_ 110(1): 110–138.
- Kim, Don H. and Jonathan H. Wright (2005). "An Arbitrage-Free
  Three-Factor Term Structure Model and the Recent Behavior of
  Long-Term Yields and Distant-Horizon Forward Rates." Federal Reserve
  Board.
- Federal Reserve note (April 2017). "Robustness of long-maturity term
  premium estimates." (KW vs ACM comparison).
- NY Fed Research (2014). "Treasury Term Premia: 1961-Present"
  (Liberty Street Economics).
- Hartford Funds 2026 Outlook (term premium expansion driver).
- SSGA Gold 2026 Outlook (real yields + dollar smile + term premium).
- Forex.com 2026 USD outlook (DXY weakness + term premium expansion).

## Followups

- v2 : add ACM cross-check by scraping NY Fed Treasury Term Premia data
  (separate collector + table or alternate series_id).
- v2 : 252d structural companion alert (sister to TERM_PREMIUM_REPRICING
  the way GEOPOL_REGIME_STRUCTURAL is sister to GEOPOL_FLASH).
- v2 : narrative attribution — cross-reference TARIFF_SHOCK / GEOPOL_FLASH
  - auction-tail bursts to tag _why_ the repricing happened.
- Phase E.4 : term-premium feature in Brier V2 driver matrix (existing
  per-factor SGD optimizer can ingest this as a covariate).
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  latest auction tail / debt-ceiling status at alert time and produce
  a 1-paragraph narrative summary grounded in the regime tag.
