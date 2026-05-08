"""CBOE VVIX Index daily collector — vol-of-vol meta-volatility tracker.

VVIX measures the expected 30-day volatility of the VIX itself —
i.e., how violently the implied-vol surface is being repriced. Reading
~85 is neutral; >100 = elevated turbulence in the vol surface;
extreme spikes (>140) historically coincide with vol-of-vol blowups
(e.g. Feb 2018 VIX inversion event).

Why VVIX matters for Ichor :
  - When VVIX is bid hard but VIX itself stays modest, the option
    market is *pricing-in* future vol-spike risk before the underlying
    cash equity reflects it. Useful for macro-broad regime
    classification ahead of FOMC / NFP / catalysts.
  - Confirms or invalidates the SKEW tail-risk read — both can spike
    together (genuine vol-surface stress) or diverge (pure tail vs
    pure ATM-of-vol bid).

Free path : Yahoo Finance public chart endpoint for ticker `^VVIX`.
Verified live 2026-05-08 — endpoint returns daily data with ~30-min
lag on close. Same pattern as `cboe_skew.py` (wave 24).

VVIX is **NOT on FRED** as of 2026-05 (verified by researcher subagent
2026-05-08). FRED hosts VIX/GVZ/OVX/RVX but not VVIX, so a Yahoo-side
collector is the only Voie-D-compliant path.

License : Yahoo Finance terms allow personal/research use; no API
key required.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# Yahoo Finance public chart endpoint. ^VVIX is URL-encoded as %5EVVIX.
VVIX_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVVIX"

# Yahoo bans the default Python User-Agent — must spoof a real browser.
# Mirror cboe_skew.py exactly for consistency.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36 IchorCollector/1.0"
    ),
    "Accept": "application/json,text/plain,*/*",
}


@dataclass(frozen=True)
class CboeVvixObservation:
    """One daily CBOE VVIX reading."""

    observation_date: date
    """Calendar day of the close (US trading day)."""

    vvix_value: float
    """VVIX index level. ~85 = neutral; >100 = elevated vol-of-vol;
    >140 = historic vol-surface blowup territory."""

    fetched_at: datetime


def parse_chart_response(payload: dict) -> list[CboeVvixObservation]:
    """Pure parser — extract daily observations from Yahoo chart JSON.

    Returns [] on any structural mismatch. Never raises; caller treats
    empty as "fetch produced nothing". Mirror of cboe_skew.parse_chart_response.
    """
    try:
        chart = payload.get("chart") or {}
        if chart.get("error") is not None:
            log.warning("cboe_vvix.yahoo_error", error=chart["error"])
            return []
        result = (chart.get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        if len(timestamps) != len(closes):
            log.warning(
                "cboe_vvix.shape_mismatch",
                ts_len=len(timestamps),
                close_len=len(closes),
            )
        fetched = datetime.now(UTC)
        out: list[CboeVvixObservation] = []
        for ts, close in zip(timestamps, closes, strict=False):
            if close is None:
                continue
            try:
                obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
                value = float(close)
            except (TypeError, ValueError):
                continue
            out.append(
                CboeVvixObservation(
                    observation_date=obs_date,
                    vvix_value=value,
                    fetched_at=fetched,
                )
            )
        return out
    except (KeyError, TypeError, IndexError) as e:
        log.warning("cboe_vvix.parse_failed", error=str(e))
        return []


async def fetch_recent(
    *,
    range_window: str = "1mo",
    interval: str = "1d",
    client: httpx.AsyncClient | None = None,
) -> list[CboeVvixObservation]:
    """Fetch the last `range_window` of daily VVIX closes from Yahoo."""
    params = {"interval": interval, "range": range_window}
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0, headers=_HEADERS)
    try:
        try:
            r = await client.get(VVIX_CHART_URL, params=params)
            r.raise_for_status()
            return parse_chart_response(r.json())
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cboe_vvix.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all(
    range_window: str = "1mo",
) -> list[CboeVvixObservation]:
    """Standard collector entry point — single-source VVIX daily."""
    return await fetch_recent(range_window=range_window)


__all__ = [
    "VVIX_CHART_URL",
    "CboeVvixObservation",
    "fetch_recent",
    "parse_chart_response",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} rows")
    for r in rows[-5:]:
        print(f"  {r.observation_date}  vvix={r.vvix_value:.2f}")
