"""FlashAlpha free-tier GEX (Gamma Exposure) collector.

FlashAlpha exposes options-derived dealer positioning data on the
free tier (5 requests / day). For a 8-asset universe Ichor wants
NDX + SPX gamma flip + call-wall + put-wall + total GEX → 2 calls/day,
8% of the daily quota.

VISION_2026 delta C — options flow / dealer gamma.

API endpoint shape (per public docs, verify on first --persist run) :
    GET https://flashalphalive.com/api/v1/options/gex/{ticker}
        Headers: X-API-Key: <key>
    Response (best-guess shape — adapt on first call) :
        {
          "ticker": "SPX",
          "as_of": "2026-05-04T20:00:00Z",
          "spot": 5187.0,
          "total_gex_usd": 1.35e9,
          "gamma_flip": 5160.0,
          "call_wall": 5250.0,
          "put_wall": 5100.0,
          "zero_gamma": 5180.0
        }

Fail-soft : if `flashalpha_api_key` is empty, the collector skips
silently with a stderr line. If the API responds 4xx/5xx we log
the body and return [] — never crash the brain pipeline.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

FLASHALPHA_BASE = "https://flashalphalive.com/api/v1"

# Tickers we poll on the free tier — sized for 5 req/day budget.
WATCHED_TICKERS: tuple[str, ...] = ("SPX", "NDX")


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
    return GexSnapshot(
        ticker=ticker,
        as_of=_parse_iso(body.get("as_of") or body.get("timestamp")),
        spot=_safe_float(body.get("spot") or body.get("underlying")),
        total_gex_usd=_safe_float(
            body.get("total_gex_usd") or body.get("net_gex") or body.get("totalGEX")
        ),
        gamma_flip=_safe_float(body.get("gamma_flip") or body.get("gammaFlip") or body.get("flip")),
        call_wall=_safe_float(body.get("call_wall") or body.get("callWall")),
        put_wall=_safe_float(body.get("put_wall") or body.get("putWall")),
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
            f"{FLASHALPHA_BASE}/options/gex/{ticker}",
            headers={
                "X-API-Key": api_key,
                "User-Agent": "IchorFlashalphaCollector/0.1",
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
