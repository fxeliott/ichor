"""Crypto Fear & Greed Index collector — alternative.me API.

Why this exists for Ichor :
  - The crypto F&G index aggregates volatility, volume, social
    sentiment, dominance and Google trends into one 0-100 reading.
    Extremes (<20 = capitulation, >80 = euphoria) tend to mark
    multi-week turning points and bleed into NAS100/SPX risk-on/off
    via the "tech-crypto correlation chain".

Endpoint (verified 2026-05-05) :
  GET https://api.alternative.me/fng/?limit=N&format=json
  Returns : {data: [{value, value_classification, timestamp,
                      time_until_update}, ...]}

  No auth, 60 req/min over 10-min window, updated every 5 min.

Source:
  - https://alternative.me/crypto/api/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

ALTERNATIVE_BASE = "https://api.alternative.me"


@dataclass(frozen=True)
class FearGreedReading:
    """One reading of the Crypto Fear & Greed Index."""

    observation_date: date
    value: int  # 0-100
    classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    fetched_at: datetime


def parse_fng_response(body: dict[str, Any]) -> list[FearGreedReading]:
    """Walk {data: [...]} into a list of readings, dated."""
    out: list[FearGreedReading] = []
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return out
    now = datetime.now(UTC)
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp")
        try:
            obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
        except (TypeError, ValueError, OSError):
            continue
        try:
            value = int(r.get("value", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= value <= 100:
            continue
        cls = str(r.get("value_classification") or "").strip() or "Unknown"
        out.append(
            FearGreedReading(
                observation_date=obs_date, value=value, classification=cls, fetched_at=now
            )
        )
    return out


async def fetch_fng_history(
    *, limit: int = 30, timeout_s: float = 15.0
) -> list[FearGreedReading]:
    """Pull the last `limit` daily readings (limit=0 = all history)."""
    url = f"{ALTERNATIVE_BASE}/fng/"
    params = {"limit": str(limit), "format": "json"}
    headers = {"User-Agent": "IchorCryptoFNGCollector/0.1", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            return parse_fng_response(r.json())
    except httpx.HTTPError:
        return []


def is_extreme(reading: FearGreedReading) -> bool:
    """True at the conventional contrarian thresholds (≤20 or ≥80)."""
    return reading.value <= 20 or reading.value >= 80
