"""CBOE SKEW Index daily collector — tail-risk regime tracker.

The SKEW index measures perceived tail risk in S&P 500 returns over
the next 30 days, derived from out-of-the-money S&P 500 options that
are *not* captured by the at-the-money VIX. A reading of 100 is
neutral; values 130-150 are common in stress regimes; >150 indicates
fat-tail panic priced in (rare).

For Ichor it feeds two trader-actionable signals:
  - Tail risk regime classification (vs VIX-only level reading).
  - DOLLAR_SMILE_BREAK detector — a *broken* dollar smile per Stephen
    Jen (Wellington Apr 2025, Bloomberg Nov 2025) is conditional on
    SKEW being elevated alongside USD weakening + term-premium
    expansion. SKEW supplies the "tail" component the VIX misses.

Free path : Yahoo Finance public chart endpoint for ticker `^SKEW`.
Subagent verified live 2026-05-08 — endpoint returns daily data with
~30-min lag on close.

License : Yahoo Finance terms allow personal/research use; no API
key required. Treasury equivalent on FRED was searched and not
present in the CBOE-tagged release (FRED hosts VIXCLS / GVZCLS /
OVXCLS / VXVCLS but not SKEW as of 2026-05).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# Yahoo Finance public chart endpoint. ^SKEW is URL-encoded as %5ESKEW.
SKEW_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ESKEW"

# Yahoo bans the default Python User-Agent — must spoof a real browser.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36 IchorCollector/1.0"
    ),
    "Accept": "application/json,text/plain,*/*",
}


@dataclass(frozen=True)
class CboeSkewObservation:
    """One daily CBOE SKEW reading."""

    observation_date: date
    """Calendar day of the close (US trading day)."""

    skew_value: float
    """SKEW index level. 100 = neutral; >130 = elevated tail risk."""

    fetched_at: datetime


def parse_chart_response(payload: dict) -> list[CboeSkewObservation]:
    """Pure parser — extract daily observations from Yahoo chart JSON.

    Returns [] on any structural mismatch (Yahoo schema drift). Never
    raises; the caller treats empty as "fetch produced nothing".

    Yahoo schema (verified 2026-05-08):
      { "chart": {
          "result": [{
            "timestamp": [int, ...],   # epoch seconds, one per trading day
            "indicators": {"quote": [{"close": [float | null, ...]}]}
          }],
          "error": null
      }}
    """
    try:
        chart = payload.get("chart") or {}
        if chart.get("error") is not None:
            log.warning("cboe_skew.yahoo_error", error=chart["error"])
            return []
        result = (chart.get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        if len(timestamps) != len(closes):
            log.warning(
                "cboe_skew.shape_mismatch",
                ts_len=len(timestamps),
                close_len=len(closes),
            )
            # Defensive: zip stops at the shorter, drop the remainder.
        fetched = datetime.now(UTC)
        out: list[CboeSkewObservation] = []
        for ts, close in zip(timestamps, closes, strict=False):
            if close is None:
                # Yahoo returns null for non-trading days inside the range
                continue
            try:
                obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
                value = float(close)
            except (TypeError, ValueError):
                continue
            out.append(
                CboeSkewObservation(
                    observation_date=obs_date,
                    skew_value=value,
                    fetched_at=fetched,
                )
            )
        return out
    except (KeyError, TypeError, IndexError) as e:
        log.warning("cboe_skew.parse_failed", error=str(e))
        return []


async def fetch_recent(
    *,
    range_window: str = "1mo",
    interval: str = "1d",
    client: httpx.AsyncClient | None = None,
) -> list[CboeSkewObservation]:
    """Fetch the last `range_window` of daily SKEW closes from Yahoo.

    Returns [] on any HTTP error. Never raises — collector pattern is
    "best-effort, log + skip" so one source flake doesn't take the
    nightly batch down.

    `range_window` follows Yahoo's standard codes: `5d`, `1mo`, `3mo`,
    `6mo`, `1y`, `5y`, `max`. 1mo is enough for daily updates and
    handles weekend gaps without re-collecting all history.
    """
    params = {"interval": interval, "range": range_window}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0, headers=_HEADERS)
    try:
        try:
            r = await client.get(SKEW_CHART_URL, params=params)
            r.raise_for_status()
            return parse_chart_response(r.json())
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cboe_skew.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all(
    range_window: str = "1mo",
) -> list[CboeSkewObservation]:
    """Standard collector entry point — single-source SKEW daily.

    Compatible with the dispatch in `cli.run_collectors`: returns a
    list of dataclass rows ready for `persist_cboe_skew_observations`.
    """
    return await fetch_recent(range_window=range_window)


__all__ = [
    "SKEW_CHART_URL",
    "CboeSkewObservation",
    "fetch_recent",
    "parse_chart_response",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} rows")
    for r in rows[-5:]:
        print(f"  {r.observation_date}  skew={r.skew_value:.2f}")
