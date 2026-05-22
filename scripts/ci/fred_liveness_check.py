"""Nightly FRED-DB liveness check — ADR-097 R53 codification (r61).

Mechanically enforces R53 doctrine ("EMPIRICAL FRED DB liveness check >
web-search cache") by polling each series in `merged_series()` against
FRED API + comparing against `_FRED_SERIES_MAX_AGE_DAYS` registry.

MVP scope (per r50.5 wave-2 critique correcting initial ADR-097 over-
engineering) :
- NO LLM-suggested replacements (out of MVP scope)
- NO auto-issue creation (out of MVP scope)
- ONLY fail CI hard on RED + emit structured JSON report artifact

Rate-limit math (corrected per r50.5 wave-2 critique) :
- FRED API documented limit : 120 requests/minute = 2 req/sec sustained
- Original ADR-097 spec : 60 req in <5s burst → would trip rate-limit
- This script : 0.5s sleep between requests = ≤2 req/sec = safe

Imports use existing canonical sources. r92 : the max-age registry was
extracted to a dependency-free SSOT so this CI guard no longer pulls
data_pool's SQLAlchemy + 33-ORM graph — the latent Defect A that made
every run exit-4 since r61 (the docstring below anticipated exactly
this extraction) :
- `merged_series()` from `apps/api/src/ichor_api/collectors/fred_extended.py`
- `FRED_SERIES_MAX_AGE_DAYS` + `FRED_DEFAULT_MAX_AGE_DAYS` from
  `apps/api/src/ichor_api/services/fred_age_registry.py` (dependency-
  free SSOT ; `data_pool.py` re-exports them byte-identically)

Severity bands (per ADR-097) :
- GREEN : staleness ≤ threshold
- YELLOW : staleness > threshold but ≤ 2× threshold (warn, no fail)
- RED : staleness > 2× threshold OR FRED API 4xx/5xx (FAIL CI hard)

Exit codes :
- 0 : 0 RED series (CI green)
- 2 : ≥1 RED series (CI fail)
- 3 : missing ICHOR_CI_FRED_API_KEY env var
- 4 : import path error (canonical sources moved/renamed)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from typing import Any

import httpx

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
RATE_LIMIT_SLEEP_S = 0.5  # 2 req/sec sustained, safe vs FRED 120/min
HTTP_TIMEOUT_S = 15
REPORT_PATH = "fred_liveness_report.json"


def _import_canonical_sources() -> tuple[tuple[str, ...], dict[str, int], int]:
    """Import canonical merged_series + max-age registry from apps/api.

    Returns (series_tuple, max_age_registry_dict, default_max_age_days).
    Exits with code 4 if imports fail (canonical source moved).
    """
    try:
        # Add apps/api/src to sys.path so ichor_api module resolves.
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        apps_api_src = os.path.join(repo_root, "apps", "api", "src")
        if apps_api_src not in sys.path:
            sys.path.insert(0, apps_api_src)

        from ichor_api.collectors.fred_extended import merged_series
        from ichor_api.services.fred_age_registry import (
            FRED_DEFAULT_MAX_AGE_DAYS as _FRED_DEFAULT_MAX_AGE_DAYS,
        )
        from ichor_api.services.fred_age_registry import (
            FRED_SERIES_MAX_AGE_DAYS as _FRED_SERIES_MAX_AGE_DAYS,
        )

        series = merged_series()
        return series, _FRED_SERIES_MAX_AGE_DAYS, _FRED_DEFAULT_MAX_AGE_DAYS
    except ImportError as exc:
        print(f"FATAL : canonical import path moved : {exc}", file=sys.stderr)
        sys.exit(4)


async def check_series(
    client: httpx.AsyncClient,
    series_id: str,
    api_key: str,
) -> dict[str, Any]:
    """Single-series liveness check : returns severity + last_obs metadata."""
    try:
        r = await client.get(
            FRED_BASE_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            timeout=HTTP_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        return {
            "series_id": series_id,
            "severity": "RED",
            "api_status": None,
            "last_obs_date": None,
            "staleness_days": None,
            "error": f"http_error: {exc.__class__.__name__}",
        }

    if r.status_code != 200:
        return {
            "series_id": series_id,
            "severity": "RED",
            "api_status": r.status_code,
            "last_obs_date": None,
            "staleness_days": None,
            "error": f"http_{r.status_code}",
        }

    obs = r.json().get("observations", [])
    if not obs:
        return {
            "series_id": series_id,
            "severity": "RED",
            "api_status": 200,
            "last_obs_date": None,
            "staleness_days": None,
            "error": "empty_observations",
        }

    last_obs_str = obs[0].get("date")
    if not last_obs_str:
        return {
            "series_id": series_id,
            "severity": "RED",
            "api_status": 200,
            "last_obs_date": None,
            "staleness_days": None,
            "error": "missing_date_field",
        }

    return {
        "series_id": series_id,
        "api_status": 200,
        "last_obs_date": last_obs_str,
    }


def _classify_severity(
    last_obs_date: str | None,
    threshold_days: int,
) -> tuple[str, int | None]:
    """Compute (severity, staleness_days) from last_obs_date."""
    if last_obs_date is None:
        return "RED", None
    try:
        last = date.fromisoformat(last_obs_date)
    except ValueError:
        return "RED", None
    staleness = (date.today() - last).days
    if staleness <= threshold_days:
        return "GREEN", staleness
    if staleness <= 2 * threshold_days:
        return "YELLOW", staleness
    return "RED", staleness


async def main() -> int:
    api_key = os.environ.get("ICHOR_CI_FRED_API_KEY", "").strip()
    if not api_key:
        print("FATAL : ICHOR_CI_FRED_API_KEY env var not set", file=sys.stderr)
        return 3

    series, registry, default_days = _import_canonical_sources()
    print(f"Checking {len(series)} FRED series (rate-limit 2 req/sec)...")

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for i, sid in enumerate(series):
            r = await check_series(client, sid, api_key)
            # Severity classification (already RED if check_series errored)
            if "severity" not in r:
                threshold = registry.get(sid, default_days)
                sev, stale = _classify_severity(r.get("last_obs_date"), threshold)
                r["severity"] = sev
                r["staleness_days"] = stale
                r["threshold_days"] = threshold
            results.append(r)
            # Rate-limit : 2 req/sec sustained
            if i < len(series) - 1:
                await asyncio.sleep(RATE_LIMIT_SLEEP_S)

    counts = {
        sev: sum(1 for r in results if r["severity"] == sev) for sev in ("GREEN", "YELLOW", "RED")
    }
    report = {
        "date": str(date.today()),
        "total_series": len(series),
        "counts": counts,
        "series": results,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"\n=== FRED liveness report ({REPORT_PATH}) ===")
    print(
        f"Total : {len(series)} | GREEN : {counts['GREEN']} | YELLOW : {counts['YELLOW']} | RED : {counts['RED']}"
    )
    if counts["RED"] > 0:
        print("\nRED series (CI fail) :")
        for r in results:
            if r["severity"] == "RED":
                err = r.get("error", "stale")
                print(
                    f"  - {r['series_id']:18s} : {err} (last_obs={r.get('last_obs_date')}, staleness={r.get('staleness_days')}d)"
                )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
