"""r131 — Polymarket Δ-YES manipulation watch (axis-8 completion) tests.

Pure pytest-async tests on `_fetch_yes_24h_ago_per_slug` + integrated
`assess_polymarket_impact` populating `MarketHit.yes_24h_ago` +
`yes_velocity_pp`. Snapshot fixtures shaped after the
`polymarket_snapshots` ORM (composite (id, fetched_at) PK, last_prices
JSONB list).

No live DB — uses a session stub that returns canned rows for both the
"latest snapshot per slug" query (existing) and the new "oldest in
24h-48h-ago window per slug" query (r131).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


def _mk_snapshot(
    slug: str,
    yes: float,
    fetched_at: datetime,
    question: str = "Will the Fed cut rates in June 2026?",
) -> SimpleNamespace:
    """Minimal stub mirroring the PolymarketSnapshot ORM shape used by
    `assess_polymarket_impact`. Only the fields the service reads."""
    return SimpleNamespace(
        id=uuid4(),
        fetched_at=fetched_at,
        slug=slug,
        question=question,
        last_prices=[yes],
        outcomes=["Yes", "No"],
        market_id=f"market-{slug}",
        closed=False,
        volume_usd=None,
    )


class _StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _StubSession:
    """Two-query stub : the first .execute() returns the 24h-window
    "latest snapshots" rows ; the second returns the 24h-48h-window
    "oldest snapshots" rows for the Δ-YES history query."""

    def __init__(
        self,
        latest_rows: list[SimpleNamespace],
        history_rows: list[SimpleNamespace],
    ) -> None:
        self._latest = latest_rows
        self._history = history_rows
        self._call_count = 0

    async def execute(self, stmt: Any) -> _StubResult:  # noqa: ARG002
        self._call_count += 1
        if self._call_count == 1:
            return _StubResult(self._latest)
        return _StubResult(self._history)


@pytest.mark.asyncio
async def test_fetch_yes_24h_ago_empty_slugs_returns_empty() -> None:
    """Defensive : empty input slug list short-circuits, no DB query."""
    from ichor_api.services.polymarket_impact import _fetch_yes_24h_ago_per_slug

    session = _StubSession([], [])
    result = await _fetch_yes_24h_ago_per_slug(session, [])  # type: ignore[arg-type]
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_yes_24h_ago_filters_malformed_prices() -> None:
    """Snapshots with empty/None/out-of-range YES are filtered (defense)."""
    from ichor_api.services.polymarket_impact import _fetch_yes_24h_ago_per_slug

    now = datetime.now(UTC)
    window_mid = now - timedelta(hours=36)

    good = _mk_snapshot("good", 0.42, window_mid)
    bad_empty = _mk_snapshot("bad-empty", 0.5, window_mid)
    bad_empty.last_prices = []
    bad_oor = _mk_snapshot("bad-oor", 0.5, window_mid)
    bad_oor.last_prices = [1.5]  # > 1 = malformed
    bad_none = _mk_snapshot("bad-none", 0.5, window_mid)
    bad_none.last_prices = [None]

    # Direct helper call = FIRST .execute() of the stub. Put rows in
    # `latest_rows` slot since the helper does the first DB query.
    session = _StubSession([good, bad_empty, bad_oor, bad_none], [])
    result = await _fetch_yes_24h_ago_per_slug(
        session,  # type: ignore[arg-type]
        ["good", "bad-empty", "bad-oor", "bad-none"],
    )
    # r131 trader MUST-FIX-2 — helper now returns (yes, fetched_at) tuple.
    assert set(result.keys()) == {"good"}
    yes_value, fetched_at = result["good"]
    assert yes_value == 0.42
    assert fetched_at == window_mid


@pytest.mark.asyncio
async def test_assess_polymarket_impact_populates_velocity_when_history_exists() -> None:
    """End-to-end : latest snapshot YES=0.62 + history YES=0.55 →
    velocity = +7.00 pp (significant shift, > 5pp threshold)."""
    from ichor_api.services.polymarket_impact import assess_polymarket_impact

    now = datetime.now(UTC)
    latest_at = now - timedelta(hours=1)
    history_at = now - timedelta(hours=30)

    latest = _mk_snapshot(
        "fed-june-cut",
        0.62,
        latest_at,
        question="Will the Fed cut rates in June 2026?",
    )
    history = _mk_snapshot(
        "fed-june-cut",
        0.55,
        history_at,
        question="Will the Fed cut rates in June 2026?",
    )
    session = _StubSession([latest], [history])

    report = await assess_polymarket_impact(session, hours=24, limit=100)  # type: ignore[arg-type]

    # Find the fed_cut theme + the matching market hit
    fed_theme = next((t for t in report.themes if t.theme_key == "fed_cut"), None)
    assert fed_theme is not None, "fed_cut theme must match the Fed-cut question"
    market = next((m for m in fed_theme.markets if m.slug == "fed-june-cut"), None)
    assert market is not None
    assert market.yes == 0.62
    assert market.yes_24h_ago == 0.55
    assert market.yes_velocity_pp == 7.0  # (0.62 - 0.55) * 100 = 7.0 pp
    # r131 trader MUST-FIX-2 — honest dual-stamp carried through.
    assert market.yes_24h_ago_at == history_at


@pytest.mark.asyncio
async def test_assess_polymarket_impact_velocity_none_when_no_history() -> None:
    """Honest silent absence : market has latest YES but no 24h-48h-ago
    snapshot → velocity = None (frontend renders no badge per doctrine #11)."""
    from ichor_api.services.polymarket_impact import assess_polymarket_impact

    now = datetime.now(UTC)
    latest_at = now - timedelta(hours=1)
    latest = _mk_snapshot(
        "fed-new",
        0.40,
        latest_at,
        question="Will the Fed cut rates in June 2026?",
    )
    # No history rows — slug younger than 24h or cron gap
    session = _StubSession([latest], [])

    report = await assess_polymarket_impact(session, hours=24, limit=100)  # type: ignore[arg-type]

    fed_theme = next((t for t in report.themes if t.theme_key == "fed_cut"), None)
    assert fed_theme is not None
    market = next((m for m in fed_theme.markets if m.slug == "fed-new"), None)
    assert market is not None
    assert market.yes == 0.40
    assert market.yes_24h_ago is None
    assert market.yes_velocity_pp is None
    assert market.yes_24h_ago_at is None


@pytest.mark.asyncio
async def test_assess_polymarket_impact_velocity_negative_shift() -> None:
    """Bear shift : latest YES=0.30 + history YES=0.45 → velocity = -15 pp
    (> 10pp = "manipulation possible" tier in frontend tone escalation)."""
    from ichor_api.services.polymarket_impact import assess_polymarket_impact

    now = datetime.now(UTC)
    latest = _mk_snapshot(
        "iran-deal",
        0.30,
        now - timedelta(hours=1),
        question="Israel Iran deal?",
    )
    history = _mk_snapshot(
        "iran-deal",
        0.45,
        now - timedelta(hours=30),
        question="Israel Iran deal?",
    )
    session = _StubSession([latest], [history])

    report = await assess_polymarket_impact(session, hours=24, limit=100)  # type: ignore[arg-type]

    iran_theme = next((t for t in report.themes if t.theme_key == "israel_iran"), None)
    assert iran_theme is not None
    market = next((m for m in iran_theme.markets if m.slug == "iran-deal"), None)
    assert market is not None
    assert market.yes_velocity_pp == -15.0


@pytest.mark.asyncio
async def test_assess_polymarket_impact_velocity_subtle_shift_under_5pp() -> None:
    """Small shift : latest YES=0.51 + history YES=0.50 → velocity = +1.0 pp
    (below 5pp "shift rapide" threshold, frontend renders neutral badge)."""
    from ichor_api.services.polymarket_impact import assess_polymarket_impact

    now = datetime.now(UTC)
    latest = _mk_snapshot(
        "cpi-above",
        0.51,
        now - timedelta(hours=1),
        question="CPI above 3% in May?",
    )
    history = _mk_snapshot(
        "cpi-above",
        0.50,
        now - timedelta(hours=30),
        question="CPI above 3% in May?",
    )
    session = _StubSession([latest], [history])

    report = await assess_polymarket_impact(session, hours=24, limit=100)  # type: ignore[arg-type]

    cpi_theme = next((t for t in report.themes if t.theme_key == "inflation"), None)
    assert cpi_theme is not None
    market = next((m for m in cpi_theme.markets if m.slug == "cpi-above"), None)
    assert market is not None
    assert market.yes_velocity_pp == 1.0
