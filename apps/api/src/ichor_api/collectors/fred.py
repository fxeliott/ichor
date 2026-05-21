"""FRED collector — pulls St. Louis Fed economic data series.

Strategy: poll the latest observation for each series we care about, then
write to a `fred_observations` time-series table (TimescaleDB).

Free tier: ~120 req/min (per AUDIT_V3 §7). With 30 series × 24 polls/day
= 720 calls/day = trivial.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

# Series Ichor cares about (per ARCHITECTURE_FINALE + AUDIT_V3)
SERIES_TO_POLL: tuple[str, ...] = (
    # Credit
    "BAMLH0A0HYM2",  # HY OAS spread
    # NB BAMLC0A0CMTRIV (IG OAS) was here — FRED 400s, renamed/removed.
    # BAMLC0A0CM (canonical IG OAS) is in fred_extended.py.
    # Vol
    "VIXCLS",  # VIX
    # Rates
    "SOFR",  # secured overnight financing
    "DFF",  # Federal funds effective
    "DGS2",
    "DGS10",  # Treasury 2y and 10y
    # Macro
    "CPIAUCSL",  # CPI all urban
    "PCEPI",  # PCE price index
    "PAYEMS",  # NFP total
    "UNRATE",  # Unemployment rate
    "GDPC1",  # Real GDP
    "INDPRO",  # Industrial production
    # Money
    "M2SL",  # M2
    "WALCL",  # Fed balance sheet
    "RRPONTSYD",  # Reverse repo overnight
    "WTREGEN",  # Treasury General Account
    # FX
    "DTWEXBGS",  # Trade-weighted dollar (broad)
    # Commodities
    "DCOILWTICO",  # WTI crude
    # NB GOLDAMGBD228NLBM (Gold London PM fix) was here — FRED 400s,
    # renamed/removed — dropped wave 37b. No FRED-hosted gold price as of
    # 2026-05; gold via XAU spot from polygon C:XAUUSD already covered.
)


@dataclass
class FredObservation:
    series_id: str
    observation_date: str  # ISO date "2026-05-02"
    value: float | None
    fetched_at: datetime


async def fetch_latest(
    series_id: str, api_key: str, *, client: httpx.AsyncClient
) -> FredObservation | None:
    """One series, latest observation. Returns None if unavailable."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }
    try:
        r = await client.get(f"{FRED_BASE}/series/observations", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        obs = data.get("observations", [])
        if not obs:
            return None
        o = obs[0]
        val_str = o.get("value", ".")
        # FRED uses "." for missing
        value = None if val_str == "." else float(val_str)
        return FredObservation(
            series_id=series_id,
            observation_date=o["date"],
            value=value,
            fetched_at=datetime.now(UTC),
        )
    except Exception as e:
        log.warning("fred.fetch_failed", series=series_id, error=str(e))
        return None


async def poll_all(api_key: str, series: tuple[str, ...] = SERIES_TO_POLL) -> list[FredObservation]:
    """Poll every series in parallel (gated by httpx connection pool)."""
    async with httpx.AsyncClient() as client:
        tasks = [fetch_latest(s, api_key, client=client) for s in series]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ── r135 : deep-history backfill ──────────────────────────────────────
# The routine `fetch_latest` poll stores only the SINGLE most recent
# observation (limit=1). That is why the Economic Surprise Index was dark
# (composite=None) : its z-score needs ≥6 prints per series to form ≥5
# period-changes, but the table only ever held 1-2 rows. `fetch_history`
# pulls the last `limit` observations so a one-shot backfill gives the
# index real depth. `persist_fred_observations` dedups read-then-insert
# (not a SQL ON CONFLICT — idempotent for sequential re-runs, but do NOT
# run two backfills concurrently), so re-running this is safe + cheap.

# The headline macro series the Economic Surprise Index z-scores. Monthly
# (PAYEMS/UNRATE/CPIAUCSL/PCEPI/INDPRO) + quarterly (GDPC1) → limit=120
# gives ~10y monthly (≈119 changes) / ~30y quarterly. More than enough.
SURPRISE_BACKFILL_SERIES: tuple[str, ...] = (
    "CPIAUCSL",
    "PCEPI",
    "PAYEMS",
    "UNRATE",
    "GDPC1",
    "INDPRO",
)


async def fetch_history(
    series_id: str, api_key: str, *, client: httpx.AsyncClient, limit: int = 120
) -> list[FredObservation]:
    """Last `limit` observations for `series_id` (any order from FRED;
    persisted by natural key so order is irrelevant). Returns [] on error.

    Used by the r135 backfill path ONLY — routine polling stays on
    `fetch_latest` (limit=1) to keep per-cron cost minimal."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        r = await client.get(f"{FRED_BASE}/series/observations", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        now = datetime.now(UTC)
        out: list[FredObservation] = []
        for o in data.get("observations", []):
            val_str = o.get("value", ".")
            value = None if val_str == "." else float(val_str)
            out.append(
                FredObservation(
                    series_id=series_id,
                    observation_date=o["date"],
                    value=value,
                    fetched_at=now,
                )
            )
        return out
    except Exception as e:
        log.warning("fred.fetch_history_failed", series=series_id, error=str(e))
        return []


async def backfill_history(
    api_key: str,
    series: tuple[str, ...] = SURPRISE_BACKFILL_SERIES,
    *,
    limit: int = 120,
) -> list[FredObservation]:
    """Deep-history backfill for `series`. Sequential with a 0.2s gap to
    stay well under FRED's ~120 req/min free tier (r135)."""
    out: list[FredObservation] = []
    async with httpx.AsyncClient() as client:
        for s in series:
            rows = await fetch_history(s, api_key, client=client, limit=limit)
            log.info("fred.backfill_series", series=s, rows=len(rows))
            out.extend(rows)
            await asyncio.sleep(0.2)
    return out
