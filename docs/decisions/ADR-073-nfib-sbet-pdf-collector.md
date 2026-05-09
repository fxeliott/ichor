# ADR-073: NFIB Small Business Economic Trends PDF collector

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-009 (Voie D), ADR-017 (research-only),
  ADR-069 (NY Fed MCT), ADR-070 (Cleveland Fed nowcast)

## Context

The NFIB Small Business Economic Trends (SBET) report is a leading
indicator of US small-business sentiment, published monthly on the
2nd Tuesday of each month for the prior month's survey. Headline
metric: Small Business Optimism Index (SBOI), 1986=100. Sub-component:
Uncertainty Index. Both have predictive value for hiring/capex
intentions and, when both deteriorate together, recession-precursor
signature seen in 2007 and 2019.

W74 audit (2026-05-09) located the canonical source. NFIB hosts the
report as a PDF on `nfib.com/wp-content/uploads/`. The filename
convention is inconsistent across months (`Feb.-2026`, `March-2026`,
etc.) so a stable URL pattern is impossible. Solution: scrape the
hub page `nfib.com/news/monthly_report/sbet/` and regex out the
first PDF link. Verified live: hub returns exactly one
`*NFIB-SBET-Report*.pdf` href, pointing at the most recent
publication.

PDF structure: 27 pages. Cover (page 1) + components table. Page 3
contains the headline narrative:

> "The Small Business Optimism Index for March was 95.8, down 3.0
> points from February and falling below its 52-year average of 98.0.
> The Uncertainty Index rose 4 points from February to 92, well above
> its [...]"

Two regex anchors extract SBOI ("Optimism Index for <Month> was X.X")
and Uncertainty ("Uncertainty Index ... to N").

NFIB's `nfib-sbet.org/Indicators.html` exposes "EXPORT EXCEL" buttons
but the URLs are dynamically generated (no static endpoint). FRED has
no canonical mirror series for SBOI confirmable from this audit. PDF
+ pdfplumber is the only stable path.

## Decision

Ship a new collector `apps/api/src/ichor_api/collectors/nfib_sbet.py`
that:

1. Fetches the SBET hub page (HTML).
2. Regex-extracts the current PDF URL.
3. Parses the survey month from the filename (e.g.
   `NFIB-SBET-Report-March-2026.pdf` → `2026-03-01`).
4. Downloads the PDF via httpx.
5. Uses pdfplumber to extract page-3 text (defensive scan of pages
   1-5 in case of layout shifts).
6. Regexes SBOI + Uncertainty Index from the headline narrative.
7. Persists `(report_month, sboi, uncertainty_index, source_pdf_url)`.

Migration `0036_nfib_sbet_observations.py`. TimescaleDB hypertable on
`report_month`. UniqueConstraint on `report_month` makes daily polls
idempotent.

systemd timer `ichor-collector-nfib_sbet.timer` polling daily at 12:30
Europe/Paris. NFIB publishes 2nd Tuesday ~06:00 ET = 12:00 Paris;
12:30 daily catches the publication day and is no-op-fast on the
~28 other days.

`data_pool.py` adds `_section_nfib_sbet(session)` after the Cleveland
Fed nowcast. Surfaces:

- SBOI with reference to 52-year average (≈ 98.0)
- Uncertainty Index
- Régime classifier with bands {recession-precursor < 95 + Unc > 95,
  below-avg < 95, soft < 100, expansionary ≥ 100}
- Δ SBOI 1m and 12m

`pdfplumber` added as a runtime dependency (heavy ~30 MB with the
pdfminer.six + Pillow + cryptography sub-tree). Installed locally
into `/opt/ichor/api/.venv` via the deploy script. Imported lazily
inside the collector to avoid loading at API startup.

## Consequences

### Positive

- **Sentiment leading indicator now wired**. Pass 1 régime layer
  cross-validates with the inflation pillar (W71 MCT, W72 Cleveland
  nowcast) — divergence between sentiment regime and inflation regime
  is the cleanest "stagflation-pivot" detection.
- **Verified live 2026-05-09 14:08 CEST**: 1 row persisted, March 2026
  SBOI = 95.8, Uncertainty Index = 92, régime = "below-average
  sentiment" (only 1 of 2 conditions for recession-precursor met).
  Timer next trigger 12:30 CEST.
- **Voie D-compliant** (ADR-009): public PDF, no API key.
- **Hub-scrape strategy is resilient** to NFIB's filename
  inconsistency. The first SBET PDF href on the hub is always the
  most recent — verified live with 1 unique match.
- **License-respectful**: only derived metrics (SBOI value +
  Uncertainty value) persisted. The PDF itself is not rehosted; the
  `source_pdf_url` field is an audit pointer back to the original.

### Negative

- **PDF parsing is fragile** to layout shifts. Mitigation: regex
  scans the first 5 pages (not just page 3) and defensive `_RE`
  patterns are tolerant of small wording variations. Headline
  narrative wording has been stable for >5 years per W74 audit.
- **`pdfplumber` is a heavy dep**. Imported lazily, only loaded by
  this collector. Installed system-wide on Hetzner once for future
  PDF collectors (e.g. Cleveland Fed FAQ + WGC reports).
- **Single data point per month**. SBOI components, "Inflation as #1
  problem", and the 52-year history table on page 8 are not
  extracted in v1. Extension is straightforward when needed (regex
  per-component table).

## Alternatives considered

- **Scrape `nfib-sbet.org/Indicators.html` Excel export** — rejected:
  URL is JS-generated and not statically reachable.
- **Use Trading Economics or another aggregator** — rejected: those
  re-publish NFIB data with their own ToS layered on top, less
  Voie-D-clean than the source.
- **Wait for NFIB to ship a JSON API** — rejected: no signal in 5
  years that they will. PDF is the canonical interface.
- **Skip the Uncertainty Index** — rejected: the {SBOI, Uncertainty}
  pair is what makes the recession-precursor classifier work. Both
  must persist or the régime layer is downgraded.

## Verification (live 2026-05-09)

```
NFIB SBET · 1 rows fetched
  2026-03-01  SBOI=95.8  Uncertainty=92.0
  src=https://www.nfib.com/wp-content/uploads/2026/04/NFIB-SBET-Report-March-2026.pdf
nfib_sbet.persisted inserted=1 skipped=0 total=1
```

PostgreSQL:

```
report_month | sboi | uncertainty_index | source_pdf_url
2026-03-01   | 95.8 | 92                | https://www.nfib.com/.../NFIB-SBET-Report-March-2026.pdf
```

Régime classifier output: "below-average sentiment". 52-year average
98.0 → SBOI 95.8 is 2.2 pts below average, consistent with the
NFIB-cited March commentary "fell below its 52-year average of 98.0".

## References

- `apps/api/src/ichor_api/collectors/nfib_sbet.py` — collector
- `apps/api/src/ichor_api/models/nfib_sbet_observation.py` — model
- `apps/api/migrations/versions/0036_nfib_sbet_observations.py` — migration
- `apps/api/src/ichor_api/services/data_pool.py:_section_nfib_sbet`
- `scripts/hetzner/register-cron-collectors-extended.sh:nfib_sbet`
- NFIB SBET hub: https://www.nfib.com/news/monthly_report/sbet/
- pdfplumber 0.11.9: https://github.com/jsvine/pdfplumber
- ADR-009 (Voie D), ADR-017 (research-only), ADR-022 (probability bias)
