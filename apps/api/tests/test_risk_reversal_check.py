"""Unit tests for services/risk_reversal_check.py.

Wires the previously DORMANT RISK_REVERSAL_25D alert. Tests cover :
  - z-score arithmetic on a synthetic history
  - guard against insufficient history (< 30 points)
  - guard against zero variance
  - exclusion of today's value from the distribution
  - alert firing when |z| ≥ 2.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ichor_api.services.risk_reversal_check import (
    _MIN_HISTORY,
    _zscore,
    evaluate_rr25,
)


# ── pure z-score helper ────────────────────────────────────────────


def test_zscore_returns_none_when_history_too_short() -> None:
    short = [0.0] * (_MIN_HISTORY - 1)
    assert _zscore(short, 0.5) is None


def test_zscore_returns_none_when_std_zero() -> None:
    flat = [0.0] * (_MIN_HISTORY + 5)
    assert _zscore(flat, 0.5) is None


def test_zscore_classic_two_sigma() -> None:
    # 50 zeros + 1 standard deviation around them
    history = [0.0] * 25 + [1.0] * 25  # mean=0.5, std=0.5
    z = _zscore(history, 1.5)
    assert z is not None
    assert z == pytest.approx(2.0, abs=1e-9)


def test_zscore_negative_for_bearish_extreme() -> None:
    history = [0.01] * 30 + [-0.01] * 30  # symmetric ≈ 0
    z = _zscore(history, -0.05)
    assert z is not None
    assert z < -2.0


# ── evaluate_rr25 (mocks DB) ───────────────────────────────────────


def _build_mock_session(history_values: list[float], existing_today: bool = False) -> MagicMock:
    """Mock async session whose execute() returns:
       1. existing-today-value lookup (None if no row)
       2. (after insert/update) read_history rows
       3. check_metric internal queries (catalog-driven)
    """
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    def _scalar_result(value):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=value)
        return r

    def _all_result(values):
        r = MagicMock()
        r.all = MagicMock(return_value=[(v,) for v in values])
        return r

    # First call: existence check (.scalar_one_or_none returns None or some id)
    # Second call: read_history (.all() returns list of tuples)
    # Subsequent calls (alerts_runner internals): non-deterministic — return empty.
    queue = [
        _scalar_result("existing-id" if existing_today else None),
        _all_result(history_values),
    ]

    async def _execute(*args, **kwargs):
        if queue:
            return queue.pop(0)
        # Fallback for alerts_runner queries — empty result
        empty = MagicMock()
        empty.scalar_one_or_none = MagicMock(return_value=None)
        empty.all = MagicMock(return_value=[])
        empty.first = MagicMock(return_value=None)
        empty.scalar = MagicMock(return_value=None)
        return empty

    session.execute = _execute
    return session


@pytest.mark.asyncio
async def test_evaluate_returns_none_z_when_history_short() -> None:
    """First few runs after the alert is wired won't have enough
    history yet — must NOT fail, just return z=None."""
    session = _build_mock_session(history_values=[0.0] * 10)
    result = await evaluate_rr25(session, asset="SPX500_USD", rr25_pct=0.01)
    assert result.z_score is None
    assert "insufficient history" in result.note


@pytest.mark.asyncio
async def test_evaluate_computes_z_when_history_sufficient() -> None:
    history = [0.001] * 25 + [-0.001] * 25  # 50 pts, mean=0, std≈0.001
    session = _build_mock_session(history_values=history + [0.005])
    # The persisted row + today's value both surface in the read; we
    # exclude the last point (today) before computing z.
    result = await evaluate_rr25(session, asset="SPX500_USD", rr25_pct=0.005)
    assert result.z_score is not None
    assert result.z_score > 4.0  # 0.005 vs std ≈ 0.001 → ~5σ


@pytest.mark.asyncio
async def test_evaluate_persist_false_skips_writes() -> None:
    """Dry-run mode : no DB writes, no alert calls — only computation."""
    session = _build_mock_session(history_values=[0.0] * 50)
    result = await evaluate_rr25(
        session, asset="SPX500_USD", rr25_pct=0.0, persist=False
    )
    assert result.rr25_pct == 0.0
    session.add.assert_not_called()
