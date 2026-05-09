# ADR-069: NY Fed Multivariate Core Trend collector replaces discontinued UIG

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-009 (Voie D, free path only), ADR-017 (research-only
  boundary), ADR-022 (probability bias models reinstated under Critic)

## Context

The NY Fed published the Underlying Inflation Gauge (UIGFULL) on FRED
through 2017 then discontinued it in favour of the Multivariate Core
Trend (MCT) Inflation. UIG was a useful primary input to Ichor's
inflation-régime classifier — without a replacement, the régime layer
was running on `core_pce_yoy` alone, which is too noisy on a single
month and doesn't decompose into sectoral drivers.

The NY Fed MCT (Almuzara-Sbordone, FRBNY Staff Reports 2024-2025) is a
Bayesian dynamic-factor model on 17 PCE sectors. It outputs:

- A persistent-trend headline value (smoother than core PCE)
- A 3-sector decomposition (Goods / Services ex housing / Housing)
- Updated monthly, ~10:00 ET on the first business day of the month
  following the BEA PCE release

There is no FRED mirror — the only canonical source is the NY Fed
Liberty Street interactive on `/research/policy/mct`. Direct scraping
of that page returns 403 to plain HTTP requests (anti-bot). The page
data is loaded via XHR from a JS bundle.

W71 audit (2026-05-09) located the data URL by inspecting the bundle
JS payload (`/medialibrary/Research/Interactives/mct/js/mct-chart.0.0.1.bundle.js`):

> /medialibrary/Research/Interactives/Data/mct/mct-chart-data.csv

This URL is reachable with a standard browser User-Agent, returns a
~70 KB CSV with 795 monthly observations (1960-01 → 2026-03), and is
updated alongside the chart (verified live 2026-05-09 with 2026-03
data already published).

The official GitHub repo `MCT-Inflation-NYFed/MCT-PCE` was evaluated as
a fallback — it contains MATLAB `.mat` files, but the only commit is
2024-02-20 (single snapshot). Confirmed unreliable as a live source.

## Decision

Ship a new collector `apps/api/src/ichor_api/collectors/nyfed_mct.py`
consuming the live NY Fed CSV. Persist to a new table
`nyfed_mct_observations` with columns:

- `observation_month` (PK + Timescale hypertable column)
- `mct_trend_pct` (NOT NULL — central trend, the primary signal)
- `headline_pce_yoy`, `core_pce_yoy`, `goods_pct`,
  `services_ex_housing_pct`, `housing_pct` (nullable for
  forward-compat if NY Fed drops a column)

Migration `0034_nyfed_mct_observations.py`. TimescaleDB hypertable on
`observation_month`, 365-day chunks (low cardinality).

CLI registered under `_run_nyfed_mct` + dispatched at
`run_collectors.py: SCHEDULES["nyfed_mct"]`.

systemd timer `ichor-collector-nyfed_mct.timer` polling daily at 17:00
Europe/Paris (~6 hours after the typical NY Fed publication window
+ buffer). Idempotent dedup on `observation_month` makes daily polls
cost-free for non-release days.

`data_pool.py` adds `_section_nyfed_mct(session)` between OECD CLI and
labor_uncertainty. The section surfaces:

- Headline MCT + headline PCE YoY + core PCE YoY
- Δ MCT 6m and Δ MCT 12m
- Régime classifier: anchored / near-target / above-target /
  unanchored, with thresholds 2.25 / 2.75 / 3.25 (anchored to the
  Fed's 2 % target + Powell 2024-Q3 "tolerable upper band" 2.5 %)
- 3-sector contribution decomposition (Goods / Services ex housing /
  Housing)

## Consequences

### Positive

- **Inflation régime layer now has a credible primary input** that
  isn't noisy month-to-month. The Fed's reaction function is more
  sensitive to trend than to single-print headline; matching that in
  the data_pool removes a structural distortion.
- **Sector decomposition unlocks a new mechanism citation in Pass 2**.
  E.g. "MCT trend stable at 2.74 % in Mar 2026, but Goods +0.59 vs
  Services ex housing +0.65 — late-cycle services-sticky pattern". This
  is exactly the sort of mechanism narrative the 4-pass orchestrator
  needs to score conviction.
- **Verified live 2026-05-09**: 795 rows persisted (1960-01 → 2026-03),
  Mar 2026 MCT = 2.74 %, headline PCE 3.5 %, core PCE 3.2 %, Goods
  +0.59, Services ex h. +0.65, Housing +0.09. Timer next trigger
  2026-05-09 17:00 CEST.
- **Voie D-compliant** (ADR-009): no API key, free path, public
  domain US Federal Reserve publication.

### Negative

- **JS bundle URL is undocumented and could change** without notice.
  Mitigation: the URL pattern follows a clear NY Fed convention
  (`/medialibrary/.../Data/<topic>/<topic>-chart-data.csv`); if the
  collector starts returning empty rows, refresh the bundle URL with
  the same JS-inspection technique encoded in the docstring of
  `nyfed_mct.py`.
- **CSV header has 4 nested levels** (section / route / radio / column)
  which makes column-index parsing brittle. The collector keys on the
  date format `M/D/YYYY` to find data rows and uses positional column
  indices — refactor to header-name parsing if NY Fed re-orders.
- **Régime classifier thresholds are heuristic** (2.25 / 2.75 / 3.25).
  These are documented inline and can be tuned post-hoc once Brier
  optimizer V2 has enough output history to back-test.

## Alternatives considered

- **Use only the GitHub repo .mat file** — rejected: frozen at
  2024-02-20 (single commit, single snapshot).
- **Scrape the NY Fed page HTML** — rejected: returns 403 to plain
  HTTP without a real-browser UA; even with UA, the page is JS-rendered
  with no static data table.
- **Use an alternative trend measure (Cleveland Fed trimmed-mean / median CPI)**
  — rejected: those are point-in-time statistics, not Bayesian trend
  estimates. They serve a different function (cross-sectional outlier
  removal vs persistent-trend filtering). Wave 72 will add the
  Cleveland Fed nowcast as a complement, not a replacement.
- **Wait for NY Fed to mirror MCT on FRED** — rejected: 8 years and
  counting since UIG discontinuation, no FRED mirror appeared.

## Verification (live 2026-05-09)

```
NY Fed MCT · 795 monthly observations fetched
  latest = 2026-03-01 : MCT=2.74%  headlinePCE=3.5%  corePCE=3.2%
nyfed_mct.persisted inserted=795 skipped=0 total=795

postgres# SELECT COUNT(*), MIN, MAX, ROUND(AVG(mct_trend_pct)::numeric, 2)
          FROM nyfed_mct_observations;
total | first      | last       | avg_mct
795   | 1960-01-01 | 2026-03-01 | 2.98
```

Régime classifier output for the latest observation: "above target
(cuts-on-hold band)" — coherent with the Fed's pause-and-wait posture
documented in the Liberty Street Economics Feb 2026 commentary.

## References

- `apps/api/src/ichor_api/collectors/nyfed_mct.py` — collector
- `apps/api/src/ichor_api/models/nyfed_mct_observation.py` — model
- `apps/api/migrations/versions/0034_nyfed_mct_observations.py` — migration
- `apps/api/src/ichor_api/services/data_pool.py:_section_nyfed_mct` — surfacing
- `scripts/hetzner/register-cron-collectors-extended.sh:nyfed_mct` — timer
- Almuzara, M., & Sbordone, A. M. (2024). *Inertia, Uncertainty, and the
  Persistence of Inflation*. FRBNY Staff Reports.
- ADR-009 (Voie D — Max 20x flat, no paid API)
- ADR-017 (research-only boundary)
- ADR-022 (Probability bias models under Critic gate)
