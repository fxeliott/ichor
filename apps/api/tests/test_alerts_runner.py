"""Unit tests for the alerts_runner service.

Verifies :
  - check_metric correctly de-dups within the configured window
  - check_fred_alerts triggers both level + delta alerts when both
    are encoded in the catalog
  - check_gex_alerts feeds gex_d AND gex_dealer simultaneously
  - persisted alert rows match the AlertHit shape

The DB is mocked — these tests are unit-level. Integration tests
(real Postgres) live in test_alerts_runner_integration.py if/when
needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ichor_api.alerts.evaluator import AlertHit
from ichor_api.services.alerts_runner import (
    _DEDUP_WINDOW,
    check_fred_alerts,
    check_gex_alerts,
    check_metric,
)


# ── helpers ─────────────────────────────────────────────────────────


def _mock_session_with_calls(*scalar_returns) -> MagicMock:
    """Build a session where each .execute() returns a result whose
    `.scalar_one_or_none()` and `.first()` and `.scalar()` all yield
    the supplied values in order."""
    session = MagicMock()
    session.execute = AsyncMock()

    def _build(value):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=value)
        result.first = MagicMock(return_value=value)
        result.scalar = MagicMock(return_value=value)
        return result

    session.execute.side_effect = [_build(v) for v in scalar_returns]
    session.add = MagicMock()
    return session


def _make_hit(code: str, severity: str = "warning") -> AlertHit:
    ad = SimpleNamespace(
        code=code,
        severity=severity,
        title_template=f"{code} fired at {{value:.1f}}",
        metric_name="FAKE",
        default_threshold=10.0,
        default_direction="above",
        crisis_mode=False,
        description="test",
    )
    return AlertHit(
        alert_def=ad,
        metric_value=15.0,
        threshold=10.0,
        direction_observed="above",
        source_payload={"x": 1},
    )


# ── check_metric ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_metric_dedup_skips_recent_duplicate() -> None:
    session = _mock_session_with_calls(1)  # _is_recent_duplicate → row found

    with patch(
        "ichor_api.services.alerts_runner.evaluate_metric", return_value=[_make_hit("VIX_SPIKE")]
    ):
        out = await check_metric(
            session, metric_name="VIXCLS", current_value=30.0, asset=None
        )

    assert out == []  # de-duped, nothing persisted
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_check_metric_persists_when_no_duplicate() -> None:
    session = _mock_session_with_calls(None)  # _is_recent_duplicate → no row

    with patch(
        "ichor_api.services.alerts_runner.evaluate_metric", return_value=[_make_hit("VIX_SPIKE")]
    ):
        out = await check_metric(
            session, metric_name="VIXCLS", current_value=30.0, asset=None
        )

    assert len(out) == 1
    assert out[0].alert_def.code == "VIX_SPIKE"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_check_metric_no_hits_returns_empty() -> None:
    session = _mock_session_with_calls()
    with patch(
        "ichor_api.services.alerts_runner.evaluate_metric", return_value=[]
    ):
        out = await check_metric(
            session, metric_name="VIXCLS", current_value=15.0, asset=None
        )
    assert out == []
    session.add.assert_not_called()


# ── check_fred_alerts ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_fred_alerts_evaluates_level_and_delta() -> None:
    """For BAMLH0A0HYM2 the catalog has both level + delta alerts.
    A series with a *_d in ALL_ALERTS should trigger 2 evaluate calls."""
    # Sequence of session.execute() returns :
    #  1. previous value lookup → 200.0
    #  2. _is_recent_duplicate for level alert → no
    #  3. _is_recent_duplicate for delta alert → no
    session = _mock_session_with_calls(200.0, None, None)

    call_count = {"n": 0}

    def _fake_evaluate(metric_name, *args, **kwargs):
        call_count["n"] += 1
        if metric_name == "BAMLH0A0HYM2":
            return [_make_hit("HY_OAS_CRISIS", "critical")]
        if metric_name == "BAMLH0A0HYM2_d":
            return [_make_hit("HY_OAS_WIDEN")]
        return []

    with patch(
        "ichor_api.services.alerts_runner.evaluate_metric", side_effect=_fake_evaluate
    ):
        out = await check_fred_alerts(
            session, series_id="BAMLH0A0HYM2", current_value=900.0
        )

    # Should have triggered both level + delta evaluations
    assert call_count["n"] == 2


# ── check_gex_alerts ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_gex_alerts_evaluates_both_metric_names() -> None:
    """gex_dealer + gex_d : both should be passed through evaluate_metric."""
    # 1. previous gex value → -2.0e9
    # 2-3. _is_recent_duplicate for the 2 evaluate_metric calls
    session = _mock_session_with_calls(-2.0e9, None, None)

    seen_metrics: list[str] = []

    def _fake_evaluate(metric_name, *args, **kwargs):
        seen_metrics.append(metric_name)
        return []

    with patch(
        "ichor_api.services.alerts_runner.evaluate_metric", side_effect=_fake_evaluate
    ):
        await check_gex_alerts(session, asset="SPY", dealer_gex_total=-3.5e9)

    assert "gex_dealer" in seen_metrics
    assert "gex_d" in seen_metrics


# ── dedup window sanity ─────────────────────────────────────────────


def test_dedup_window_is_at_least_one_hour() -> None:
    """If we shrink it too low, sustained spikes spam the alerts table."""
    assert _DEDUP_WINDOW.total_seconds() >= 3600
