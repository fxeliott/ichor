"""DeFiLlama TVL + stablecoin supply collector.

Why this exists for Ichor :
  - Aggregate stablecoin supply (USDT + USDC + DAI + others) is the
    most direct proxy for crypto-side USD liquidity. Net supply
    expansions/contractions correlate with risk-asset moves on a
    multi-week horizon.
  - DeFi TVL by chain reflects on-chain leverage and capital flows
    that pre-date equity moves (e.g., when ETH TVL contracts hard,
    NAS100 often follows within days).

DeFiLlama public API (verified 2026-05-05) :
  - https://api.llama.fi/v2/historicalChainTvl  → all chains, daily
  - https://api.llama.fi/v2/historicalChainTvl/{chain}  → per chain
  - https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=N → time series

  No auth, no rate limit on the public path (per docs.llama.fi/faqs).
  Updates hourly.

Sources:
  - https://api-docs.defillama.com/
  - https://docs.llama.fi/faqs/frequently-asked-questions
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

DEFILLAMA_BASE = "https://api.llama.fi"
STABLECOINS_BASE = "https://stablecoins.llama.fi"

# Chains we care about for the macro overlay (USD-denominated activity).
WATCHED_CHAINS: tuple[str, ...] = ("Ethereum", "Solana", "Tron", "Arbitrum", "Base")


@dataclass(frozen=True)
class TvlObservation:
    """One historical TVL data-point for a chain."""

    chain: str
    observation_date: date
    tvl_usd: float
    fetched_at: datetime


@dataclass(frozen=True)
class StablecoinSupply:
    """Aggregate stablecoin supply (peggedUSD)."""

    observation_date: date
    total_circulating_usd: float
    fetched_at: datetime


def _ts_to_date(ts: int | float | str | None) -> date | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC).date()
    except (ValueError, TypeError, OSError):
        return None


def parse_chain_tvl_response(chain: str, body: list[Any]) -> list[TvlObservation]:
    """DeFiLlama returns a list of {date: int, tvl: float} dicts."""
    out: list[TvlObservation] = []
    if not isinstance(body, list):
        return out
    now = datetime.now(UTC)
    for row in body:
        if not isinstance(row, dict):
            continue
        d = _ts_to_date(row.get("date"))
        tvl = row.get("tvl")
        if d is None or tvl is None:
            continue
        try:
            tvl_f = float(tvl)
        except (TypeError, ValueError):
            continue
        out.append(TvlObservation(chain=chain, observation_date=d, tvl_usd=tvl_f, fetched_at=now))
    return out


def parse_stablecoins_response(body: dict[str, Any]) -> list[StablecoinSupply]:
    """Stablecoincharts/all returns a list of dated points with totalCirculatingUSD.

    The 2026 schema shape is `[{date, totalCirculatingUSD: {peggedUSD,...}}, ...]`.
    Returns peggedUSD aggregate (the dominant USD-pegged supply).
    """
    out: list[StablecoinSupply] = []
    rows = body if isinstance(body, list) else body.get("aggregated", [])
    if not isinstance(rows, list):
        return out
    now = datetime.now(UTC)
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = _ts_to_date(row.get("date"))
        if d is None:
            continue
        circ = row.get("totalCirculatingUSD")
        if isinstance(circ, dict):
            circ = circ.get("peggedUSD") or sum(
                v for v in circ.values() if isinstance(v, (int, float))
            )
        if circ is None:
            continue
        try:
            circ_f = float(circ)
        except (TypeError, ValueError):
            continue
        out.append(
            StablecoinSupply(
                observation_date=d,
                total_circulating_usd=circ_f,
                fetched_at=now,
            )
        )
    return out


async def fetch_chain_tvl(
    chain: str,
    *,
    timeout_s: float = 30.0,
    last_n_days: int = 60,
) -> list[TvlObservation]:
    """One chain's historical TVL — all points, we slice last_n_days."""
    url = f"{DEFILLAMA_BASE}/v2/historicalChainTvl/{chain}"
    headers = {"User-Agent": "IchorDefiLlamaCollector/0.1", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            obs = parse_chain_tvl_response(chain, r.json())
    except httpx.HTTPError:
        return []
    # Slice to last_n_days
    if not obs:
        return obs
    obs.sort(key=lambda o: o.observation_date)
    return obs[-last_n_days:]


async def fetch_stablecoin_supply(
    *, timeout_s: float = 30.0, last_n_days: int = 60
) -> list[StablecoinSupply]:
    """Aggregate stablecoin supply across all chains (peggedUSD)."""
    url = f"{STABLECOINS_BASE}/stablecoincharts/all"
    headers = {"User-Agent": "IchorDefiLlamaCollector/0.1", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            obs = parse_stablecoins_response(r.json())
    except httpx.HTTPError:
        return []
    if not obs:
        return obs
    obs.sort(key=lambda o: o.observation_date)
    return obs[-last_n_days:]


async def poll_all(
    *, chains: tuple[str, ...] = WATCHED_CHAINS, last_n_days: int = 60
) -> tuple[list[TvlObservation], list[StablecoinSupply]]:
    """Pull TVL for each watched chain + the stablecoin supply aggregate."""
    import asyncio

    tvl_results = await asyncio.gather(
        *(fetch_chain_tvl(c, last_n_days=last_n_days) for c in chains)
    )
    flat_tvl: list[TvlObservation] = []
    for batch in tvl_results:
        flat_tvl.extend(batch)
    stables = await fetch_stablecoin_supply(last_n_days=last_n_days)
    return flat_tvl, stables
