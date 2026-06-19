"""Service-layer tests for cross-venue prediction-market consensus.

Exercises `scan_consensus` + `render_consensus_block` end-to-end (loaders →
matcher → reliability-weighted fusion → dict/markdown) WITHOUT a live DB,
via a 3-query stub session (Polymarket → Kalshi → Manifold, the order
`scan_consensus` issues them). Mirrors the stub pattern in
`test_polymarket_velocity.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


def _poly(slug: str, yes: float, question: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        fetched_at=datetime.now(UTC),
        slug=slug,
        market_id=f"m-{slug}",
        question=question,
        last_prices=[yes],
        outcomes=["Yes", "No"],
        closed=False,
        volume_usd=1_000_000.0,
    )


def _kalshi(ticker: str, yes: float, title: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        fetched_at=datetime.now(UTC),
        ticker=ticker,
        title=title,
        yes_price=yes,
        no_price=(1 - yes) if yes is not None else None,
        volume_24h=5000,
    )


def _manifold(slug: str, prob: float, question: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        fetched_at=datetime.now(UTC),
        slug=slug,
        market_id=f"m-{slug}",
        question=question,
        probability=prob,
        volume=1234.0,
        closed=False,
    )


class _StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _ThreeQuerySession:
    """Returns poly rows on the 1st .execute(), kalshi on the 2nd,
    manifold on the 3rd — the exact order `scan_consensus` loads them."""

    def __init__(
        self,
        poly: list[SimpleNamespace],
        kalshi: list[SimpleNamespace],
        manifold: list[SimpleNamespace],
    ) -> None:
        self._queues = [poly, kalshi, manifold]
        self._i = 0

    async def execute(self, stmt: Any) -> _StubResult:  # noqa: ARG002
        rows = self._queues[self._i] if self._i < len(self._queues) else []
        self._i += 1
        return _StubResult(rows)


@pytest.mark.asyncio
async def test_scan_consensus_fuses_three_venues() -> None:
    from ichor_api.services.divergence import scan_consensus

    session = _ThreeQuerySession(
        [_poly("fed-june", 0.62, "Will the Fed cut rates in June 2026?")],
        [_kalshi("FEDJUNE", 0.58, "Fed cut rates June 2026?")],
        [_manifold("fed-june-m", 0.55, "Fed cut rates in June 2026")],
    )
    out = await scan_consensus(session, min_venues=2)  # type: ignore[arg-type]
    assert len(out) == 1
    e = out[0]
    assert e["n_venues"] == 3
    assert e["confidence"] == "high"  # poly 0.62 / kalshi 0.58 → spread 0.04
    # (0.62 + 0.58 + 0.15*0.55) / 2.15
    assert e["consensus_prob"] == pytest.approx(1.2825 / 2.15, abs=1e-4)
    assert set(e["by_venue"].keys()) == {"polymarket", "kalshi", "manifold"}
    assert e["market_ids"]["kalshi"] == "FEDJUNE"


@pytest.mark.asyncio
async def test_scan_consensus_empty_when_no_cross_venue_match() -> None:
    """A lone Polymarket market with no counterpart yields no consensus."""
    from ichor_api.services.divergence import scan_consensus

    session = _ThreeQuerySession(
        [_poly("btc-200k", 0.30, "Will Bitcoin hit 200k in 2026?")],
        [_kalshi("FED", 0.55, "Fed cut rates June 2026?")],
        [],
    )
    out = await scan_consensus(session)  # type: ignore[arg-type]
    assert out == []


@pytest.mark.asyncio
async def test_render_consensus_block_honest_absence() -> None:
    from ichor_api.services.divergence import render_consensus_block

    session = _ThreeQuerySession([], [], [])
    md, sources = await render_consensus_block(session)  # type: ignore[arg-type]
    assert "Cross-venue consensus" in md
    assert "no event matched" in md
    assert sources == []


@pytest.mark.asyncio
async def test_section_prediction_markets_kalshi_dedup_group_drop_none() -> None:
    """S03 surfacing fix: the Kalshi block dedups per-ticker, drops
    None-priced rows, and groups a strike ladder in ticker order."""
    from ichor_api.services.data_pool import _section_prediction_markets

    k_dup = _kalshi("KXFED-27APR-T4.25", 0.34, "Fed upper bound <= 4.25%")
    k_lo = _kalshi("KXFED-27APR-T4.00", 0.59, "Fed upper bound <= 4.00%")
    k_dup2 = _kalshi("KXFED-27APR-T4.25", 0.36, "Fed upper bound <= 4.25% (newer dup)")
    k_none = _kalshi("KXCPIYOY-26NOV-T5.0", None, "CPI YoY <= 5.0%")  # unpriced → dropped
    session = _ThreeQuerySession([], [k_dup, k_lo, k_dup2, k_none], [])
    md, sources = await _section_prediction_markets(session)  # type: ignore[arg-type]

    assert "[KXFED]" in md  # grouped by series
    assert "CPI YoY" not in md  # None-priced dropped
    # duplicate ticker collapsed to one entry
    assert sources.count("kalshi:KXFED-27APR-T4.25") == 1
    # ladder rendered in ticker (strike) order: T4.00 before T4.25
    assert md.index("KXFED-27APR-T4.00") < md.index("KXFED-27APR-T4.25")
    assert "kalshi:KXFED-27APR-T4.00" in sources


@pytest.mark.asyncio
async def test_section_prediction_markets_manifold_dedup() -> None:
    from ichor_api.services.data_pool import _section_prediction_markets

    m1 = _manifold("recession-2026", 0.30, "US recession in 2026?")
    m1_dup = _manifold("recession-2026", 0.32, "US recession in 2026? (newer)")
    session = _ThreeQuerySession([], [], [m1, m1_dup])
    _, sources = await _section_prediction_markets(session)  # type: ignore[arg-type]
    assert sources.count("manifold:recession-2026") == 1


@pytest.mark.asyncio
async def test_render_consensus_block_renders_estimate_and_sources() -> None:
    from ichor_api.services.divergence import render_consensus_block

    session = _ThreeQuerySession(
        [_poly("fed-june", 0.62, "Will the Fed cut rates in June 2026?")],
        [_kalshi("FEDJUNE", 0.58, "Fed cut rates June 2026?")],
        [],
    )
    md, sources = await render_consensus_block(session)  # type: ignore[arg-type]
    assert "consensus" in md.lower()
    assert "%" in md
    assert "[high," in md  # confidence tag rendered
    # provenance sources carry venue:market_id (Polymarket market_id == slug,
    # mirroring `_latest_polymarket`)
    assert "polymarket:fed-june" in sources
    assert "kalshi:FEDJUNE" in sources
