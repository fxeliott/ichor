"""FlashAlpha GEX (Gamma Exposure) collector.

FlashAlpha exposes options-derived dealer positioning data via its
Lab API. Free tier = 5 req/day, individual stocks only (ETFs/indexes
like SPY/QQQ/SPX/NDX require Basic+ paid plan). VISION_2026 delta C —
options flow / dealer gamma.

API endpoint (verified 2026-05-05 — old `flashalphalive.com` domain
was retired ; the product moved to `lab.flashalpha.com` with a new
path scheme and lowercase `X-Api-Key` header) :

    GET https://lab.flashalpha.com/v1/exposure/gex/{symbol}
        Headers: X-Api-Key: <key>
    Response (per https://flashalpha.com/docs/lab-api-reference) :
        {
          "symbol": "AAPL",
          "underlying_price": 187.45,
          "gamma_flip": 185.0,
          "net_gex": 1.35e9,
          "call_wall": {"strike": 195.0, "gex": ...},
          "put_wall": {"strike": 180.0, "gex": ...},
          ...
        }

Fail-soft : if `flashalpha_api_key` is empty, the collector skips
silently. 4xx/5xx → log + return [] (never crash the brain pipeline).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

FLASHALPHA_BASE = "https://lab.flashalpha.com/v1"

# Tickers we poll. Free tier covers individual stocks (5 req/day).
# ETFs/indexes (SPY, QQQ, SPX, NDX) require Basic+ paid plan.
# When upgraded, swap WATCHED_TICKERS to ("SPY", "QQQ") for the
# market-wide dealer GEX signal that drives Ichor's regime detection.
WATCHED_TICKERS: tuple[str, ...] = ("AAPL", "MSFT")


@dataclass(frozen=True)
class GexSnapshot:
    """One Gamma Exposure snapshot from FlashAlpha."""

    ticker: str
    as_of: datetime
    spot: float | None
    total_gex_usd: float | None
    """Net dealer gamma in USD. Positive = dealers long gamma (mean-revert
    market), negative = dealers short gamma (trend-amplifying market)."""

    gamma_flip: float | None
    """Spot level where dealer gamma flips sign — the 'pivot'."""

    call_wall: float | None
    """Highest strike with significant call gamma — typical resistance."""

    put_wall: float | None
    """Highest strike with significant put gamma — typical support."""

    zero_gamma: float | None
    """Strike where dealer gamma sums to zero (similar to gamma_flip)."""

    fetched_at: datetime
    raw: dict


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_iso(s: str | None) -> datetime:
    if not s:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(UTC)


def parse_gex_response(ticker: str, body: dict) -> GexSnapshot | None:
    """Convert a FlashAlpha JSON body into a GexSnapshot.

    Tolerant of upstream key drift : tries multiple key variants
    (gamma_flip / zerogamma / zero-gamma / etc.).
    """
    if not isinstance(body, dict):
        return None
    fetched = datetime.now(UTC)

    # call_wall / put_wall may be either a scalar strike OR a nested
    # object {strike, gex} per the 2026 lab.flashalpha.com schema.
    def _wall_strike(v: object) -> float | None:
        if isinstance(v, dict):
            return _safe_float(v.get("strike"))
        return _safe_float(v)

    return GexSnapshot(
        ticker=ticker,
        as_of=_parse_iso(body.get("as_of") or body.get("timestamp")),
        spot=_safe_float(
            body.get("underlying_price") or body.get("spot") or body.get("underlying")
        ),
        total_gex_usd=_safe_float(
            body.get("net_gex") or body.get("total_gex_usd") or body.get("totalGEX")
        ),
        gamma_flip=_safe_float(body.get("gamma_flip") or body.get("gammaFlip") or body.get("flip")),
        call_wall=_wall_strike(body.get("call_wall") or body.get("callWall")),
        put_wall=_wall_strike(body.get("put_wall") or body.get("putWall")),
        zero_gamma=_safe_float(
            body.get("zero_gamma") or body.get("zeroGamma") or body.get("zero-gamma")
        ),
        fetched_at=fetched,
        raw=body,
    )


async def fetch_gex(
    ticker: str,
    *,
    api_key: str,
    client: httpx.AsyncClient,
    timeout_s: float = 20.0,
) -> GexSnapshot | None:
    """Single-ticker fetch. Returns None on any error or missing key."""
    if not api_key:
        return None
    try:
        r = await client.get(
            f"{FLASHALPHA_BASE}/exposure/gex/{ticker}",
            headers={
                # Canonical case per https://flashalpha.com/docs/quick-start
                "X-Api-Key": api_key,
                "User-Agent": "IchorFlashalphaCollector/0.2",
            },
            timeout=timeout_s,
        )
        if r.status_code in (401, 403):
            log.warning("flashalpha.auth_failed", ticker=ticker, status=r.status_code)
            return None
        if r.status_code == 429:
            log.warning("flashalpha.rate_limited", ticker=ticker)
            return None
        r.raise_for_status()
        return parse_gex_response(ticker, r.json())
    except httpx.HTTPError as e:
        log.warning("flashalpha.fetch_failed", ticker=ticker, error=str(e))
        return None


async def poll_all(
    *,
    api_key: str,
    tickers: tuple[str, ...] = WATCHED_TICKERS,
    concurrency: int = 2,
) -> list[GexSnapshot]:
    """Sequential-friendly polling with low concurrency to stay under
    the 5-req/day free-tier ceiling."""
    if not api_key:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def _one(t: str, client: httpx.AsyncClient) -> GexSnapshot | None:
        async with sem:
            return await fetch_gex(t, api_key=api_key, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(t, client) for t in tickers))
    return [r for r in results if r is not None]


def supported_tickers() -> tuple[str, ...]:
    return WATCHED_TICKERS
