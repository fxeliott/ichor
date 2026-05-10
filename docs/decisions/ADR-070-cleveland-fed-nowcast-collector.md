# ADR-070: Cleveland Fed Inflation Nowcast collector — daily 4×3 surface

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-009 (Voie D), ADR-017 (research-only),
  ADR-069 (NY Fed MCT trend, the structural complement to this nowcast)

## Context

The Cleveland Fed publishes a daily inflation nowcast spanning four
measures (Headline CPI, Core CPI, Headline PCE, Core PCE) and three
horizons (Month-over-Month annualised, Quarter-over-Quarter SAAR,
Year-over-Year). Updated ~10:00 ET every business day.

Where this complements the NY Fed MCT trend (ADR-069) :

- **MCT** = Bayesian-trend, smooth, lags by ~1 month. Tells us where
  _persistent_ inflation is anchored.
- **Cleveland nowcast** = point-in-time forecast for the _current and
  next_ CPI/PCE prints. Tells us what the imminent BLS/BEA release is
  likely to print.
- Together: gap between MCT trend and Cleveland nowcast prefigures
  trend revisions. Gap between Cleveland nowcast and consensus
  prefigures CPI/PCE surprise.

The Cleveland Fed page returns 403 to plain HTTP scraping (anti-bot
CDN). W72 audit (2026-05-09) discovered three direct JSON endpoints
referenced in `data-data-config` HTML attributes:

- `/-/media/files/webcharts/inflationnowcasting/nowcast_quarter.json?sc_lang=en` → QoQ
- `/-/media/files/webcharts/inflationnowcasting/nowcast_month.json?sc_lang=en` → MoM
- `/-/media/files/webcharts/inflationnowcasting/nowcast_year.json?sc_lang=en` → YoY

These endpoints accept a standard browser User-Agent and return
FusionCharts JSON config arrays — one entry per snapshot (~52
quarter / ~155 month / ~155 year snapshots historical). No Playwright
or browser engine required. No CSRF token, no JS execution, no
session cookie.

## Decision

Ship a new collector `apps/api/src/ichor_api/collectors/cleveland_fed_nowcast.py`
that fetches the 3 endpoints in parallel, takes the latest snapshot
from each (most recent revision), and emits one observation per
(measure × horizon) — 4 × 3 = 12 rows per run.

Persist to a new table `cleveland_fed_nowcasts` with columns:

- `revision_date` (PK + Timescale hypertable column) — when the
  nowcast was last revised
- `measure` (CPI / CoreCPI / PCE / CorePCE)
- `horizon` (mom / qoq / yoy)
- `target_period` (first day of the target month or quarter)
- `nowcast_value` (percent)

Composite UniqueConstraint `(measure, horizon, target_period,
revision_date)` makes daily polls idempotent — re-fetching after the
nowcast already updated for the day is a no-op.

Migration `0035_cleveland_fed_nowcasts.py`. systemd timer
`ichor-collector-cleveland_fed_nowcast.timer` polling daily at 17:30
Europe/Paris (~7.5 hours after the typical 10:00 ET publication
window + buffer for revisions).

`data_pool.py` adds `_section_cleveland_fed_nowcast(session)` after
`_section_nyfed_mct`. Surfaces:

- 4 measures × 3 horizons grouped by horizon (YoY / QoQ / MoM)
- Δ vs prior revision date (limited to the YoY measure to keep the
  section short — YoY is the headline-print metric)

Schema retains all historical revisions, so over time `data_pool` can
expose nowcast-revision drift (revisions are themselves a signal — a
nowcast that keeps drifting up between the previous CPI print and
the next is a leading indicator of an upside surprise).

## Consequences

### Positive

- **Cross-validation surface**: with MCT trend (W71) + Cleveland
  nowcast (W72) + actual FRED prints, Pass 1 régime can triangulate
  three independent estimates of inflation persistence and detect
  divergences.
- **Pre-print early warning**: nowcast for May 2026 published 2-3
  weeks before the BLS CPI release of May data. Surprise-thesis
  citation in Pass 2 grounded in actual model output, not
  speculation.
- **Verified live 2026-05-09**: 12 rows persisted, May 2026 nowcast
  YoY: CPI 3.89%, Core CPI 2.61%, PCE 3.93%, Core PCE 3.32%.
  May 2026 MoM annualised: CPI 0.42%, Core CPI 0.21%, PCE 0.38%,
  Core PCE 0.27%. Timer next trigger 17:30 CEST.
- **Voie D-compliant** (ADR-009): public domain Federal Reserve
  publication, no API key, no paid tier.
- **No new dependencies**: existing `httpx` + stdlib `json`/`re`
  sufficient. Playwright was on the W72 candidate stack but turned
  out unnecessary.

### Negative

- **Endpoint URL is undocumented** and could change. Mitigation: the
  pattern follows a clear Cleveland Fed CMS convention
  (`/-/media/files/webcharts/<topic>/...`); fallback re-discovery
  technique is encoded in the docstring of `cleveland_fed_nowcast.py`
  (re-inspect HTML `data-data-config` attributes).
- **Snapshot history not preserved**: the collector keeps only the
  _latest_ snapshot from each JSON. If the Cleveland Fed retroactively
  edits earlier snapshots, we won't notice. Acceptable: nowcast
  revisions are append-only by design.

## Alternatives considered

- **Scrape rendered HTML via Playwright** — rejected: heavier (browser
  binary), slower (~5-10 s vs ~1 s), and unnecessary because JSON
  endpoints exist. Adopted only if the JSON URL convention breaks.
- **Persist the full snapshot history (155 × 4 × 3 = 1860 rows per
  full backfill)** — rejected for v1: linear-time backfill is
  available later via a one-shot `--backfill-history` flag if needed.
  Daily incremental is sufficient for live operation.
- **FRED mirror** — none exists for this nowcast. FRED's
  `EXPINF5YR` is a different series (5-year inflation expectations).

## Verification (live 2026-05-09)

```
Cleveland Fed nowcast · 12 rows fetched
  mom  CoreCPI   target=2026-05-01  rev=2026-05-08  value=0.212%
  mom  CorePCE   target=2026-05-01  rev=2026-05-08  value=0.269%
  mom  CPI       target=2026-05-01  rev=2026-05-08  value=0.418%
  mom  PCE       target=2026-05-01  rev=2026-05-08  value=0.379%
  qoq  CoreCPI   target=2026-04-01  rev=2026-05-08  value=2.556%
  qoq  CorePCE   target=2026-04-01  rev=2026-05-08  value=3.459%
  qoq  CPI       target=2026-04-01  rev=2026-05-08  value=5.777%
  qoq  PCE       target=2026-04-01  rev=2026-05-08  value=5.180%
  yoy  CoreCPI   target=2026-05-01  rev=2026-05-08  value=2.614%
  yoy  CorePCE   target=2026-05-01  rev=2026-05-08  value=3.322%
  yoy  CPI       target=2026-05-01  rev=2026-05-08  value=3.890%
  yoy  PCE       target=2026-05-01  rev=2026-05-08  value=3.932%
cleveland_fed_nowcast.persisted inserted=12 skipped=0 total=12
```

Cross-validation against MCT (W71) — Mar 2026 MCT trend = 2.74 %.
Cleveland Fed Core PCE YoY nowcast for May 2026 = 3.32 %. Gap = +0.58
points → trend likely to drift up over coming months. Mechanism
narrative for Pass 2 is sharply formed.

## References

- `apps/api/src/ichor_api/collectors/cleveland_fed_nowcast.py` — collector
- `apps/api/src/ichor_api/models/cleveland_fed_nowcast.py` — model
- `apps/api/migrations/versions/0035_cleveland_fed_nowcasts.py` — migration
- `apps/api/src/ichor_api/services/data_pool.py:_section_cleveland_fed_nowcast`
- `scripts/hetzner/register-cron-collectors-extended.sh:cleveland_fed_nowcast`
- Cleveland Fed Inflation Nowcasting page:
  https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
- DOI: 10.26509/frbc-infexp
- ADR-009 (Voie D), ADR-017 (research-only), ADR-069 (NY Fed MCT)
