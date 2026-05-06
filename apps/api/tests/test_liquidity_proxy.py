"""Unit tests for services/liquidity_proxy.py — wires
LIQUIDITY_TIGHTENING out of dormancy by computing the RRP+TGA delta.

DB is mocked ; these are pure function tests. The CLI runner
`cli/run_liquidity_check.py` is exercised separately.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from ichor_api.services.liquidity_proxy import (
    LiquidityProxyReading,
    assess_liquidity_proxy,
)


def _build_session(rows: list[tuple[date, float] | None]) -> MagicMock:
    """Mock session whose `.execute()` returns rows in order so that
    each call to `.first()` produces one of `rows`. Use None to
    simulate a missing series."""
    session = MagicMock()
    session.execute = AsyncMock()

    def _build(row):
        result = MagicMock()
        result.first = MagicMock(return_value=row)
        return result

    session.execute.side_effect = [_build(r) for r in rows]
    return session


@pytest.mark.asyncio
async def test_returns_none_when_rrp_missing() -> None:
    """No RRP row → reading reports the missing series + null delta."""
    session = _build_session([None, (date(2026, 5, 5), 800_000.0)])

    reading = await assess_liquidity_proxy(session, lookback_days=5)
    assert reading.rrp_bn is None
    assert reading.tga_bn == pytest.approx(800.0)  # 800_000 mn / 1000
    assert reading.proxy_bn is None
    assert reading.delta_bn is None
    assert "RRPONTSYD" in reading.note


@pytest.mark.asyncio
async def test_returns_none_when_tga_missing() -> None:
    session = _build_session([(date(2026, 5, 5), 450.0), None])
    reading = await assess_liquidity_proxy(session)
    assert reading.tga_bn is None
    assert reading.proxy_bn is None
    assert "DTS_TGA_CLOSE" in reading.note


@pytest.mark.asyncio
async def test_computes_proxy_and_delta_when_both_present() -> None:
    # Order of session.execute calls inside assess_liquidity_proxy :
    #   1. RRPONTSYD at-or-before today
    #   2. DTS_TGA_CLOSE at-or-before today
    #   3. RRPONTSYD at-or-before today - 5d (lag)
    #   4. DTS_TGA_CLOSE at-or-before today - 5d (lag)
    session = _build_session(
        [
            (date(2026, 5, 5), 450.0),  # RRP today = 450 bn
            (date(2026, 5, 5), 800_000.0),  # TGA today = 800 bn (in $mn)
            (date(2026, 4, 30), 600.0),  # RRP 5d ago = 600 bn
            (date(2026, 4, 30), 900_000.0),  # TGA 5d ago = 900 bn
        ]
    )

    reading = await assess_liquidity_proxy(session, lookback_days=5)
    assert reading.rrp_bn == pytest.approx(450.0)
    assert reading.tga_bn == pytest.approx(800.0)
    assert reading.proxy_bn == pytest.approx(1250.0)  # 450 + 800
    assert reading.proxy_bn_lag == pytest.approx(1500.0)  # 600 + 900
    assert reading.delta_bn == pytest.approx(-250.0)  # 1250 - 1500
    assert "Δ -250bn" in reading.note


@pytest.mark.asyncio
async def test_returns_proxy_but_null_delta_when_history_too_short() -> None:
    """Current values present, lookback values missing → still emit
    proxy_bn so observability has something, but delta stays None."""
    session = _build_session(
        [
            (date(2026, 5, 5), 450.0),
            (date(2026, 5, 5), 800_000.0),
            None,  # no RRP at lag
            (date(2026, 4, 30), 900_000.0),
        ]
    )
    reading = await assess_liquidity_proxy(session, lookback_days=5)
    assert reading.proxy_bn == pytest.approx(1250.0)
    assert reading.delta_bn is None
    assert "insufficient history" in reading.note


@pytest.mark.asyncio
async def test_negative_delta_signals_drainage() -> None:
    """The point of the alert: a -300 bn 5d move should surface as
    `delta_bn = -300` so check_metric('liq_proxy_d', value) fires."""
    session = _build_session(
        [
            (date(2026, 5, 5), 200.0),  # RRP shrunk
            (date(2026, 5, 5), 700_000.0),  # TGA unchanged
            (date(2026, 4, 30), 400.0),
            (date(2026, 4, 30), 800_000.0),
        ]
    )
    reading = await assess_liquidity_proxy(session, lookback_days=5)
    assert reading.delta_bn == pytest.approx(-300.0)


@pytest.mark.asyncio
async def test_dataclass_is_frozen_and_complete() -> None:
    """Light contract-style sanity check: the dataclass exposes the
    six fields the CLI uses for the extra_payload."""
    r = LiquidityProxyReading(
        rrp_bn=10.0, tga_bn=20.0, proxy_bn=30.0,
        proxy_bn_lag=40.0, delta_bn=-10.0, note="hi",
    )
    with pytest.raises(Exception):  # frozen=True
        r.delta_bn = 99.0  # type: ignore[misc]
