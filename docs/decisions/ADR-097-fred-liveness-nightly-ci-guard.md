# ADR-097: Nightly FRED-DB liveness CI guard (R53 codified preventive guard)

**Status**: PROPOSED (round-50, 2026-05-15) — awaiting Eliot ratification. Code prototype not yet shipped. Estimated effort 1 dev-day (CI workflow + pytest assertions + alerts wiring).

**Date**: 2026-05-15

**Decider**: Claude r50 audit (proposal) ; Eliot to ratify

**Supersedes**: none

**Extends**: [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D — uses existing FRED API key, no new feed) ; [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md) (CI-guard-as-policy pattern : every doctrinal claim should be mechanically pinned)

**Related rounds** : R46 (China M2 dead-series cache hallucination), R49 (China M1 dead-series same hallucination on different series), R50 (this codification)

---

## Context

Across rounds 46 → 49, two consecutive sessions shipped code that referenced FRED series the researcher subagent claimed were LIVE based on web-search cache snippets, which were stale by 6+ years :

1. **R46-r10** : researcher cited "MYAGM2CNM189N (China M2) LIVE Dec 2025" — empirical FRED API DB query post-deploy showed `MAX(observation_date) = 2019-08-01`. Series DISCONTINUED 6 years prior.
2. **R46-round-2** : audit swap to MYAGM1CNM189N (China M1) on the same researcher's recommendation — r49 disclosure revealed M1 ALSO DISCONTINUED 2019-08-01 (same IMF IFS family death event).
3. **R47-r6** : Empirical 3rd-party liveness verification became R45 doctrinal pattern, but R46-r10 violation still slipped through because the verification was textual ("subagent says LIVE") not mechanical (psql query).
4. **R49** : R53 pattern codified in CLAUDE.md prose : _"EMPIRICAL FRED DB liveness check > web-search cache (researcher reports can hallucinate via cached snippets ; ALWAYS verify via `psql -d ichor -c \"SELECT MAX(observation_date) FROM fred_observations WHERE series_id='X'\"` post-deploy)"_. But the rule is prose, not enforced.

**Root cause** : the dead-series detection happens AFTER deploy (post-mortem in production), not BEFORE merge. The cost of one round of "shipped code referencing dead series + multi-round audit-gap rollback + ADR-093 graceful-degradation patch" is high (~3-5 hours of subagent + Eliot trust budget).

**Impact** : Currently 1 dead series confirmed (MYAGM1CNM189N) is shipped to production with graceful-degradation hiding the silent skip. r50 also discovered **PIORECRUSDM + PCOPPUSDM are 0 rows in `fred_observations` despite being in EXTENDED_SERIES_TO_POLL r46 + FRED API confirms data exists** — this could be a different bug class (silent skip in `fetch_latest`) but a liveness CI guard would surface the symptom.

## Decision

Add a **nightly CI workflow** that :

1. Reads the canonical series tuple from `apps/api/src/ichor_api/collectors/fred_extended.py:merged_series()` + base `fred.SERIES_TO_POLL`.
2. For each `series_id`, hits FRED API `series/observations?series_id={id}&limit=1&sort_order=desc` with the CI-only FRED API key (separate from prod key).
3. Computes `staleness_days = today − observation_date`.
4. Categorizes :
   - **GREEN** : staleness ≤ `_FRED_SERIES_MAX_AGE_DAYS[series_id]` (existing registry per W90 r37)
   - **YELLOW** : staleness > registry threshold but < 2× threshold (warn, don't fail CI)
   - **RED** : staleness > 2× threshold OR FRED API 404/410/Bad-Request (FAIL CI hard)
5. Emit a JSON report `fred_liveness_report.json` artifact for trend-graphing.
6. On RED : open a GitHub issue tagged `fred-dead-series` + `audit-gap` with the series_id + last_obs date + suggested replacement (LLM-generated from `series/categories` API).

CI cadence : daily 04:00 UTC (after FRED's overnight publication window completes).

## Implementation sketch

```python
# .github/workflows/fred-liveness.yml
name: FRED-DB liveness nightly
on:
  schedule:
    - cron: '0 4 * * *'  # 04:00 UTC daily
  workflow_dispatch:
jobs:
  liveness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --extra phase-d
      - run: uv run python scripts/ci/fred_liveness_check.py
        env:
          ICHOR_CI_FRED_API_KEY: ${{ secrets.ICHOR_CI_FRED_API_KEY }}
      - if: failure()
        uses: actions/github-script@v8
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('fred_liveness_report.json'));
            const reds = report.series.filter(s => s.severity === 'RED');
            for (const s of reds) {
              await github.rest.issues.create({
                owner: context.repo.owner, repo: context.repo.repo,
                title: `[fred-dead-series] ${s.series_id} stale ${s.staleness_days}d`,
                body: `Last obs: ${s.last_obs_date}\nThreshold: ${s.threshold_days}d\nFRED status: ${s.api_status}\n\nSuggested replacement search: \`/fred/category?category_id=${s.category_id}\``,
                labels: ['fred-dead-series', 'audit-gap'],
              });
            }
      - uses: actions/upload-artifact@v5
        with:
          name: fred-liveness-report
          path: fred_liveness_report.json
```

```python
# scripts/ci/fred_liveness_check.py
import asyncio, json, os, sys
from datetime import date, timedelta
import httpx

from ichor_api.collectors.fred_extended import merged_series
from ichor_api.services.fred_age_registry import FRED_SERIES_MAX_AGE_DAYS  # W90 r37

async def check_series(client: httpx.AsyncClient, series_id: str, key: str) -> dict:
    r = await client.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": key, "file_type": "json",
                "sort_order": "desc", "limit": 1},
        timeout=15,
    )
    if r.status_code != 200:
        return {"series_id": series_id, "severity": "RED",
                "api_status": r.status_code, "last_obs_date": None,
                "staleness_days": None}
    obs = r.json().get("observations", [])
    if not obs:
        return {"series_id": series_id, "severity": "RED",
                "api_status": 200, "last_obs_date": None,
                "staleness_days": None, "reason": "empty observations"}
    last = date.fromisoformat(obs[0]["date"])
    threshold = FRED_SERIES_MAX_AGE_DAYS.get(series_id, 30)  # default 30d
    staleness = (date.today() - last).days
    if staleness <= threshold:
        sev = "GREEN"
    elif staleness <= 2 * threshold:
        sev = "YELLOW"
    else:
        sev = "RED"
    return {"series_id": series_id, "severity": sev, "api_status": 200,
            "last_obs_date": str(last), "staleness_days": staleness,
            "threshold_days": threshold}

async def main() -> int:
    key = os.environ["ICHOR_CI_FRED_API_KEY"]
    series = merged_series()
    async with httpx.AsyncClient() as c:
        # Throttle to respect FRED 120 req/min: chunk of 60 every 35s
        results = []
        for i in range(0, len(series), 60):
            chunk = series[i:i+60]
            results.extend(await asyncio.gather(*[check_series(c, s, key) for s in chunk]))
            if i + 60 < len(series):
                await asyncio.sleep(35)
    report = {"date": str(date.today()), "series": results,
              "counts": {sev: sum(1 for r in results if r["severity"] == sev)
                         for sev in ("GREEN", "YELLOW", "RED")}}
    with open("fred_liveness_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report["counts"]))
    return 0 if report["counts"]["RED"] == 0 else 2

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

## Invariants (CI-guarded)

1. **Single source of truth** : the polled series tuple comes from `merged_series()` — no hardcoded lists in the CI workflow.
2. **Threshold registry pinned** : `FRED_SERIES_MAX_AGE_DAYS` (W90 r37) is the single source for cadence-aware staleness thresholds. Adding a series without registering it = default 30d (catches monthly regressions).
3. **Voie D respect** : uses existing FRED API key, no paid feed.
4. **Rate-limit respect** : explicit 60-series-per-35s chunking stays well under FRED 120 req/min.
5. **Separate CI key** : `ICHOR_CI_FRED_API_KEY` GitHub secret is distinct from prod `ICHOR_API_FRED_API_KEY` — daily 1-shot CI runs cannot exhaust prod budget if FRED rate-limits.

## Consequences

**Positive**

- Future r46-class hallucinations caught BEFORE merge (researcher claims a series LIVE → CI rejects on next nightly run before any code ships).
- `_FRED_SERIES_MAX_AGE_DAYS` registry forced to stay in sync (any new series in EXTENDED_SERIES_TO_POLL without a registry entry produces YELLOW, prompting registration).
- Trend artifact `fred_liveness_report.json` accumulates as a longitudinal series-health graph (~365 reports/year, ~50 KB each = 18 MB/year, trivial).

**Negative**

- 1 GitHub Action run/day × 365 days ≈ ~30 min CI minutes/year (free tier 2000 min/mo, no impact).
- Adds 1 GitHub secret (`ICHOR_CI_FRED_API_KEY`) — Eliot manual setup ~2 min.
- If FRED itself is down at 04:00 UTC, the workflow fails (false RED). Mitigation : exponential backoff 3 attempts.
- Some series have legitimate gaps (e.g., quarterly GDP series can be 90 days stale by design). Registry handles this via per-series threshold.

**Neutral**

- Does NOT replace the post-deploy psql verification (R49 R53 prose pattern stays — useful in interactive sessions). CI guard is the BEFORE-merge prevention layer, R53 prose is the AFTER-deploy detection layer.
- Does NOT detect silent-skip bugs in `fetch_latest()` (e.g., r50 PIORECRUSDM/PCOPPUSDM 0-rows mystery) — those need a different CI guard (compare DB MAX(observation_date) per series_id against FRED API equivalent). Could be ADR-097-extension a future round.

## Alternatives considered

- **Detect dead-series at runtime in collector** (REJECTED) : silent-skip in `fetch_latest()` already exists ; the alert never surfaces because the value lands in `auto_improvement_log` at low priority, not in human-visible alert pipeline.
- **Annual manual audit by Claude in a future round** (REJECTED) : the cost of one missed dead-series in production is one round of audit-gap rollback (~3-5h). Daily CI catches it for free.
- **Use FRED's own `series/release/dates` to detect last-publication date** (REJECTED) : adds API surface complexity ; `observation_date` is sufficient signal — if FRED hasn't received new data in 2× threshold, that's the same condemnation.

## Status next steps

1. Eliot ratify or amend (NOT auto-ship — ADR-091 W117b lesson : every new LLM-touching code needs Eliot manual gate).
2. If ratified : create `scripts/ci/fred_liveness_check.py` + `.github/workflows/fred-liveness.yml` + register CI secret + smoke-test workflow_dispatch.
3. Wire alerts to Eliot's preferred channel (ntfy webhook per A.4.b pattern).
4. Add ADR-097-extension (silent-skip detection : compare DB MAX vs FRED MAX per series, alert on divergence > registry threshold).

## Cross-references

- **R45 doctrinal pattern** : "empirical 3rd-party liveness verification before deploy" (RBA F2 WebFetch, etc.)
- **R49 R53 prose** : "EMPIRICAL FRED DB liveness check > web-search cache"
- **W90 r37** : `_FRED_SERIES_MAX_AGE_DAYS` registry per-series thresholds
- **ADR-093** : graceful-degradation pattern for runtime dead-series (this ADR-097 is preventive, ADR-093 is reactive — both needed)
- **R50 r50_smoketest empirical evidence** : PIORECRUSDM + PCOPPUSDM are FRED-LIVE (latest 2026-03-01) but DB has 0 rows — this is the silent-skip bug class CI guard would have caught.
