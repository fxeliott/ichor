"""CME Fed Funds futures (ZQ) front-month implied EFFR collector.

Mini-FedWatch DIY: pulls ZQ=F front-month price from Yahoo Finance
and computes the market-implied Effective Fed Funds Rate via the
canonical formula:

    implied_effr = 100 - ZQ_price

This is the contract that CME uses for its FedWatch tool — the
official tool aggregates several month contracts to derive next-FOMC
move probabilities. For a single-month signal (Wave 47 minimum),
front-month is sufficient: spread vs current EFFR tells us whether the
market expects ANY move before front-month expiry (typically 30-60d).

Signal interpretation:
  - implied_effr ≈ current_effr → no move priced in (status quo)
  - implied_effr < current_effr → cut priced (dovish)
  - implied_effr > current_effr → hike priced (hawkish)

Free path verified Voie D-compliant (ADR-009): Yahoo Finance public
chart endpoint for `ZQ=F`. Same pattern as cboe_skew (Wave 24) /
cboe_vvix (Wave 29). No API key, spoofed User-Agent required.

Persistence: synthetic FRED-style series_id `ZQ_FRONT_PRICE` and
`ZQ_FRONT_IMPLIED_EFFR` written to `fred_observations` (same pattern
as AAII collector, no new table needed). Pass 2 reads via
`services/data_pool._latest_fred(session, "ZQ_FRONT_IMPLIED_EFFR")`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# Yahoo Finance public chart endpoint. ZQ=F front-month, URL-encoded.
ZQ_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/ZQ%3DF"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36 IchorCollector/1.0"
    ),
    "Accept": "application/json,text/plain,*/*",
}


@dataclass(frozen=True)
class ZqFuturesObservation:
    """One daily ZQ front-month reading + derived implied EFFR."""

    observation_date: date
    """Calendar day of the close (US trading day)."""

    zq_price: float
    """ZQ front-month settle price. 100-ZQ = implied EFFR for that
    contract month."""

    implied_effr: float
    """Derived: 100 - zq_price. Market-implied Fed Funds rate for the
    contract month (front-month = next ~30-60 days)."""

    fetched_at: datetime


def parse_chart_response(payload: dict) -> list[ZqFuturesObservation]:
    """Pure parser — extract daily observations from Yahoo chart JSON.

    Mirror of cboe_skew.parse_chart_response for ZQ futures.
    """
    try:
        chart = payload.get("chart") or {}
        if chart.get("error") is not None:
            log.warning("cme_zq.yahoo_error", error=chart["error"])
            return []
        result = (chart.get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        if len(timestamps) != len(closes):
            log.warning(
                "cme_zq.shape_mismatch",
                ts_len=len(timestamps),
                close_len=len(closes),
            )
        fetched = datetime.now(UTC)
        out: list[ZqFuturesObservation] = []
        for ts, close in zip(timestamps, closes, strict=False):
            if close is None:
                continue
            try:
                obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
                price = float(close)
                # Implied EFFR formula: 100 - ZQ = next-month avg EFFR
                implied = 100.0 - price
            except (TypeError, ValueError):
                continue
            out.append(
                ZqFuturesObservation(
                    observation_date=obs_date,
                    zq_price=price,
                    implied_effr=implied,
                    fetched_at=fetched,
                )
            )
        return out
    except (KeyError, TypeError, IndexError) as e:
        log.warning("cme_zq.parse_failed", error=str(e))
        return []


async def fetch_recent(
    *,
    range_window: str = "5d",
    interval: str = "1d",
    client: httpx.AsyncClient | None = None,
) -> list[ZqFuturesObservation]:
    """Fetch the last `range_window` of daily ZQ front-month closes."""
    params = {"interval": interval, "range": range_window}
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0, headers=_HEADERS)
    try:
        try:
            r = await client.get(ZQ_CHART_URL, params=params)
            r.raise_for_status()
            return parse_chart_response(r.json())
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cme_zq.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all(
    range_window: str = "5d",
) -> list[ZqFuturesObservation]:
    """Standard collector entry point — single-source ZQ front-month daily."""
    return await fetch_recent(range_window=range_window)


# ────────────────────────── Wave 48 multi-month sweep ──────────────────
#
# CME FedWatch methodology requires 30-Day Federal Funds Futures contracts
# bracketing each FOMC meeting. By fetching 9-12 forward months we can
# reconstruct the market-implied EFFR forward curve and derive per-meeting
# move probabilities (full FedWatch DIY, future iteration).
#
# Yahoo symbols use {Z}{Q}{Month-code}{2-digit-year}.{exchange-suffix}
# Month codes (CME standard) :
#   F=Jan G=Feb H=Mar J=Apr K=May M=Jun N=Jul Q=Aug U=Sep V=Oct X=Nov Z=Dec
# Exchange suffix : .CBT (Chicago Board of Trade)

# Static list of upcoming contract month tickers (rolling refresh annually
# as years pass; comments tag the FOMC meeting month each contract straddles).
ZQ_FORWARD_TICKERS: tuple[tuple[str, str, str], ...] = (
    # (yahoo_ticker, month_code, label_for_persistence)
    ("ZQK26.CBT", "K26", "May 2026"),  # straddles no-FOMC May
    ("ZQM26.CBT", "M26", "Jun 2026"),  # FOMC Jun 16-17
    ("ZQN26.CBT", "N26", "Jul 2026"),  # post-Jun, pre-Jul FOMC Jul 28-29
    ("ZQQ26.CBT", "Q26", "Aug 2026"),  # post-Jul FOMC
    ("ZQU26.CBT", "U26", "Sep 2026"),  # FOMC Sep 15-16
    ("ZQV26.CBT", "V26", "Oct 2026"),  # FOMC Oct 27-28
    ("ZQX26.CBT", "X26", "Nov 2026"),
    ("ZQZ26.CBT", "Z26", "Dec 2026"),  # FOMC Dec 8-9
    ("ZQF27.CBT", "F27", "Jan 2027"),  # post-Dec FOMC
)


@dataclass(frozen=True)
class ZqMultiContract:
    """Snapshot of one ZQ contract month at one point in time."""

    month_code: str  # K26, M26, ...
    month_label: str  # "May 2026", ...
    observation_date: date
    zq_price: float
    implied_effr: float
    fetched_at: datetime


async def fetch_multi_month(
    *, client: httpx.AsyncClient | None = None, timeout: float = 30.0
) -> list[ZqMultiContract]:
    """Fetch latest close for each ZQ_FORWARD_TICKERS contract.

    Returns one ZqMultiContract per available contract (ones that 404 are
    silently skipped). Used to reconstruct the forward EFFR curve per the
    CME FedWatch methodology.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    out: list[ZqMultiContract] = []
    fetched = datetime.now(UTC)
    try:
        for ticker, code, label in ZQ_FORWARD_TICKERS:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            try:
                r = await client.get(url, params={"interval": "1d", "range": "5d"})
                r.raise_for_status()
                payload = r.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("cme_zq.multi_fetch_failed", ticker=ticker, error=str(e)[:80])
                continue
            try:
                result = (payload.get("chart") or {}).get("result") or [None]
                if not result or not result[0]:
                    continue
                meta = result[0].get("meta") or {}
                price = meta.get("regularMarketPrice")
                ts = meta.get("regularMarketTime")
                if price is None or ts is None:
                    continue
                obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
                p = float(price)
                out.append(
                    ZqMultiContract(
                        month_code=code,
                        month_label=label,
                        observation_date=obs_date,
                        zq_price=p,
                        implied_effr=100.0 - p,
                        fetched_at=fetched,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                log.warning("cme_zq.multi_parse_failed", ticker=ticker, error=str(e)[:80])
                continue
    finally:
        if own_client:
            await client.aclose()
    return out


__all__ = [
    "ZQ_CHART_URL",
    "ZQ_FORWARD_TICKERS",
    "ZqFuturesObservation",
    "ZqMultiContract",
    "fetch_multi_month",
    "fetch_recent",
    "parse_chart_response",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} rows")
    for r in rows[-5:]:
        print(f"  {r.observation_date}  ZQ={r.zq_price:.3f}  implied EFFR={r.implied_effr:.3f}%")
