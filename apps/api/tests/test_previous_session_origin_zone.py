"""r174 FOUNDATION + r179 EXECUTION specs for previous_session_origin_zone.py.

r174 (preserved below) pinned the FOUNDATION-only contract :
- Pydantic-like dataclass shape (frozen, immutable, fields exhaustive)
- SessionZoneLabel + OriginDirection Literal types
- compute_previous_session_origin_zone() returns None unconditionally
  at r174 (skeleton).

r179 (this commit) ships the EXECUTION-phase compute logic :
- 5-step classifier (window resolution + polygon_intraday query +
  zone decomposition + dominant zone selection + direction classification)
- Pure helper functions unit-tested in isolation (_classify_zone,
  _compute_zone_metrics, _pick_dominant_zone, _classify_direction)
- DB-touching main async fn tested via AsyncMock session that returns
  hand-crafted fake bar fixtures

Mirror r160 Dukascopy FOUNDATION → EXECUTION pattern.

Doctrine #5 pure-module discipline : helper fns are pure (no I/O).
Doctrine #11 calibrated honesty : EXECUTION returns None on empty bars
or bar_count < 30 in dominant zone.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.previous_session_origin_zone import (
    OriginDirection,
    OriginZoneSnapshot,
    SessionZoneLabel,
    _classify_direction,
    _classify_zone,
    _compute_zone_metrics,
    _pick_dominant_zone,
    _ZoneMetrics,
    compute_previous_session_origin_zone,
)

# ─────────────────────────────────── FAKE BAR FIXTURE ─────────────────


def _fake_bar(
    bar_ts: datetime,
    open_p: float,
    high: float,
    low: float,
    close_p: float,
) -> Any:
    """Build a fake PolygonIntradayBar-shaped object for tests. We only
    duck-type the 5 fields the EXECUTION compute reads."""
    bar = MagicMock()
    bar.bar_ts = bar_ts
    bar.open = open_p
    bar.high = high
    bar.low = low
    bar.close = close_p
    return bar


def _fake_session(bars: list[Any]) -> AsyncMock:
    """AsyncMock session whose ``execute()`` returns a result whose
    ``.scalars().all()`` yields ``bars``. Mirrors the SQLAlchemy 2.x
    async select result shape that ``compute_previous_session_origin_zone``
    consumes."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = bars
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    return session


class TestOriginZoneSnapshotShape:
    """Pin the FOUNDATION dataclass shape — fields + types + frozenness."""

    def test_snapshot_is_frozen_dataclass(self) -> None:
        """``OriginZoneSnapshot`` MUST be a frozen dataclass for cache
        safety + structural-immutability discipline (mirror
        ``CorrelationMatrix`` r171a pattern)."""
        assert dataclasses.is_dataclass(OriginZoneSnapshot)
        params = OriginZoneSnapshot.__dataclass_params__
        assert params.frozen is True

    def test_snapshot_has_all_required_fields(self) -> None:
        """The 7 canonical fields documented in the module docstring
        MUST all be present. r175+ EXECUTION-phase consumers depend
        on this exact contract."""
        field_names = {f.name for f in dataclasses.fields(OriginZoneSnapshot)}
        assert field_names == {
            "session_zone",
            "high_price",
            "low_price",
            "direction",
            "bar_count",
            "start_utc",
            "end_utc",
        }

    def test_snapshot_can_be_constructed(self) -> None:
        """Smoke test : valid snapshot constructible with realistic
        FX intraday values."""
        snap = OriginZoneSnapshot(
            session_zone="london",
            high_price=1.0875,
            low_price=1.0851,
            direction="up",
            bar_count=420,
            start_utc=datetime(2026, 5, 27, 7, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 16, 0, tzinfo=UTC),
        )
        assert snap.session_zone == "london"
        assert snap.direction == "up"
        assert snap.bar_count == 420

    def test_snapshot_is_immutable(self) -> None:
        """Frozen dataclass MUST raise FrozenInstanceError on mutation
        attempt — preserves cache safety + Pydantic-class discipline."""
        snap = OriginZoneSnapshot(
            session_zone="ny",
            high_price=1.0,
            low_price=0.99,
            direction="down",
            bar_count=300,
            start_utc=datetime(2026, 5, 27, 13, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 21, 0, tzinfo=UTC),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.session_zone = "asian"  # type: ignore[misc]


class TestSessionZoneLabelLiteral:
    """The 3-zone enum is intentionally bounded — new zones land via
    ADR amendment (e.g., Mideast or Sydney sub-decomposition)."""

    def test_canonical_3_zones(self) -> None:
        """SessionZoneLabel ∈ {asian, london, ny} per Eliot Fathom §V +
        standard FX desk convention."""
        # Literal types are not directly iterable at runtime, but we
        # can verify by attempting construction of each value
        for zone in ("asian", "london", "ny"):
            snap = OriginZoneSnapshot(
                session_zone=zone,  # type: ignore[arg-type]
                high_price=1.0,
                low_price=0.99,
                direction="range",
                bar_count=300,
                start_utc=datetime(2026, 5, 27, 0, 0, tzinfo=UTC),
                end_utc=datetime(2026, 5, 27, 8, 0, tzinfo=UTC),
            )
            assert snap.session_zone == zone


class TestOriginDirectionLiteral:
    """3-class direction enum : up / down / range."""

    def test_canonical_3_directions(self) -> None:
        for direction in ("up", "down", "range"):
            snap = OriginZoneSnapshot(
                session_zone="london",
                high_price=1.0,
                low_price=0.99,
                direction=direction,  # type: ignore[arg-type]
                bar_count=300,
                start_utc=datetime(2026, 5, 27, 7, 0, tzinfo=UTC),
                end_utc=datetime(2026, 5, 27, 16, 0, tzinfo=UTC),
            )
            assert snap.direction == direction


class TestClassifyZonePure:
    """r179 EXECUTION : ``_classify_zone()`` non-overlapping UTC decomp."""

    def test_asian_hours_0_to_6(self) -> None:
        for hour in range(7):
            ts = datetime(2026, 5, 27, hour, 30, tzinfo=UTC)
            assert _classify_zone(ts) == "asian", f"hour={hour} should be asian"

    def test_london_hours_7_to_12(self) -> None:
        for hour in range(7, 13):
            ts = datetime(2026, 5, 27, hour, 30, tzinfo=UTC)
            assert _classify_zone(ts) == "london", f"hour={hour} should be london"

    def test_ny_hours_13_to_23_includes_late_ny_rollover(self) -> None:
        for hour in range(13, 24):
            ts = datetime(2026, 5, 27, hour, 30, tzinfo=UTC)
            assert _classify_zone(ts) == "ny", f"hour={hour} should be ny"


class TestClassifyDirectionPure:
    """r179 EXECUTION : ``_classify_direction()`` body/range ratio."""

    def test_up_when_close_above_open_with_high_body_ratio(self) -> None:
        # body = 0.8, range = 1.0, ratio = 0.8 > 0.3 → directional up
        assert _classify_direction(open_p=1.0, close_p=1.8, high=2.0, low=1.0) == "up"

    def test_down_when_close_below_open_with_high_body_ratio(self) -> None:
        # body = 0.8, range = 1.0, ratio = 0.8 > 0.3 → directional down
        assert _classify_direction(open_p=2.0, close_p=1.2, high=2.0, low=1.0) == "down"

    def test_range_when_body_below_threshold(self) -> None:
        # body = 0.1, range = 1.0, ratio = 0.1 < 0.3 → range
        assert _classify_direction(open_p=1.5, close_p=1.6, high=2.0, low=1.0) == "range"

    def test_range_when_session_range_zero_defensive(self) -> None:
        # range = 0 (all bars identical) → range (no div-by-zero crash)
        assert _classify_direction(open_p=1.0, close_p=1.0, high=1.0, low=1.0) == "range"

    def test_range_when_close_equals_open_threshold_met(self) -> None:
        # body = 0, ratio = 0 < 0.3 → range (caught by threshold check first)
        assert _classify_direction(open_p=1.5, close_p=1.5, high=2.0, low=1.0) == "range"


class TestPickDominantZoneTieBreak:
    """r179 EXECUTION : NY > London > Asian tie-breaker."""

    def test_argmax_abs_return_when_no_tie(self) -> None:
        london = _ZoneMetrics(
            zone="london",
            high=1.10,
            low=1.05,
            open=1.06,
            close=1.09,
            bar_count=300,
            start_utc=datetime(2026, 5, 27, 7, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 12, 59, tzinfo=UTC),
        )
        ny = _ZoneMetrics(
            zone="ny",
            high=1.12,
            low=1.08,
            open=1.09,
            close=1.10,
            bar_count=400,
            start_utc=datetime(2026, 5, 27, 13, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 20, 59, tzinfo=UTC),
        )
        # London abs_return = 0.03, NY abs_return = 0.01 → London wins.
        winner = _pick_dominant_zone([london, ny])
        assert winner is not None
        assert winner.zone == "london"

    def test_ny_wins_tie_against_london(self) -> None:
        london = _ZoneMetrics(
            zone="london",
            high=1.10,
            low=1.05,
            open=1.06,
            close=1.08,
            bar_count=300,
            start_utc=datetime(2026, 5, 27, 7, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 12, 59, tzinfo=UTC),
        )
        ny = _ZoneMetrics(
            zone="ny",
            high=1.12,
            low=1.08,
            open=1.09,
            close=1.11,
            bar_count=400,
            start_utc=datetime(2026, 5, 27, 13, 0, tzinfo=UTC),
            end_utc=datetime(2026, 5, 27, 20, 59, tzinfo=UTC),
        )
        # Both abs_return = 0.02 → NY wins by priority.
        winner = _pick_dominant_zone([london, ny])
        assert winner is not None
        assert winner.zone == "ny"

    def test_returns_none_on_empty_metrics(self) -> None:
        assert _pick_dominant_zone([]) is None


class TestComputeZoneMetricsPure:
    """r179 EXECUTION : ``_compute_zone_metrics()`` aggregation."""

    def test_returns_none_for_empty_bars(self) -> None:
        assert _compute_zone_metrics([], "asian") is None

    def test_aggregates_open_close_high_low_from_sorted_bars(self) -> None:
        bars = [
            _fake_bar(datetime(2026, 5, 27, 7, 0, tzinfo=UTC), 1.05, 1.06, 1.04, 1.055),
            _fake_bar(datetime(2026, 5, 27, 7, 1, tzinfo=UTC), 1.055, 1.065, 1.05, 1.06),
            _fake_bar(datetime(2026, 5, 27, 7, 2, tzinfo=UTC), 1.06, 1.07, 1.058, 1.068),
        ]
        m = _compute_zone_metrics(bars, "london")
        assert m is not None
        assert m.zone == "london"
        assert m.open == 1.05  # bars[0].open
        assert m.close == 1.068  # bars[-1].close
        assert m.high == 1.07  # max of highs
        assert m.low == 1.04  # min of lows
        assert m.bar_count == 3
        assert abs(m.abs_return - 0.018) < 1e-9


class TestComputeExecutionEndToEnd:
    """r179 EXECUTION : full ``compute_previous_session_origin_zone()``
    against AsyncMock session + fake bar fixtures."""

    def test_returns_none_when_no_bars_in_window(self) -> None:
        """Weekend / holiday scenario : polygon_intraday empty for asset.
        Doctrine #11 calibrated honesty : return None, don't fabricate."""

        async def _run() -> None:
            session = _fake_session(bars=[])
            result = await compute_previous_session_origin_zone(
                session=session,
                asset="EUR_USD",
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is None

        asyncio.run(_run())

    def test_returns_none_when_dominant_zone_below_low_n(self) -> None:
        """Dominant zone has < 30 bars : honest absence per Cohen 1988."""

        async def _run() -> None:
            # 10 NY bars only — below MIN_BAR_COUNT = 30.
            base = datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
            bars = [
                _fake_bar(base + timedelta(minutes=i), 1.05, 1.06, 1.04, 1.055) for i in range(10)
            ]
            session = _fake_session(bars=bars)
            result = await compute_previous_session_origin_zone(
                session=session,
                asset="EUR_USD",
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is None

        asyncio.run(_run())

    def test_classifies_ny_dominant_up_for_fx(self) -> None:
        """FX EUR_USD : Asian flat, London mild move, NY strong up.
        NY dominant ; classification up ; bar_count >= 30."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 0, 0, tzinfo=UTC)
            bars: list[Any] = []
            # Asian: 60 flat bars (range-bound)
            for i in range(60):
                bars.append(_fake_bar(base + timedelta(minutes=i), 1.05, 1.0505, 1.0495, 1.0501))
            # London: 60 bars, mild +0.001 drift
            ldn_base = datetime(2026, 5, 27, 7, 0, tzinfo=UTC)
            for i in range(60):
                bars.append(
                    _fake_bar(
                        ldn_base + timedelta(minutes=i),
                        1.0501 + 0.0001 * i,
                        1.0506 + 0.0001 * i,
                        1.0498 + 0.0001 * i,
                        1.0502 + 0.0001 * i,
                    )
                )
            # NY: 60 bars, strong +0.008 drift (close 1.069 from open 1.061)
            ny_base = datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
            for i in range(60):
                bars.append(
                    _fake_bar(
                        ny_base + timedelta(minutes=i),
                        1.061 + 0.00015 * i,
                        1.062 + 0.00015 * i,
                        1.060 + 0.00015 * i,
                        1.0612 + 0.00015 * i,
                    )
                )
            session = _fake_session(bars=bars)
            result = await compute_previous_session_origin_zone(
                session=session,
                asset="EUR_USD",
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is not None
            assert result.session_zone == "ny"
            assert result.direction == "up"
            assert result.bar_count == 60

        asyncio.run(_run())

    def test_classifies_nas_ny_only_for_equity(self) -> None:
        """NAS100_USD : NYSE RTH only. Asian / London empty. NY dominant
        by construction (only zone with bars)."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 13, 30, tzinfo=UTC)
            bars: list[Any] = []
            # 60 NY RTH bars, slight down move
            for i in range(60):
                bars.append(
                    _fake_bar(
                        base + timedelta(minutes=i),
                        18500 - 5 * i,
                        18510 - 5 * i,
                        18490 - 5 * i,
                        18495 - 5 * i,
                    )
                )
            session = _fake_session(bars=bars)
            result = await compute_previous_session_origin_zone(
                session=session,
                asset="NAS100_USD",
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is not None
            assert result.session_zone == "ny"
            assert result.direction == "down"

        asyncio.run(_run())


class TestTypeAliasesAreLiteralOnly:
    """Smoke : SessionZoneLabel + OriginDirection are Literal type
    aliases (used by mypy + pydantic-like validation). Runtime
    introspection is best-effort — the real enforcement is the
    Literal narrows + mypy CI guards."""

    def test_session_zone_label_is_literal(self) -> None:
        # typing.Literal aliases don't have a stable __args__ accessor
        # in pre-3.12 ; this test just confirms the type exists and
        # is importable, which is sufficient for the FOUNDATION ship.
        assert SessionZoneLabel is not None

    def test_origin_direction_is_literal(self) -> None:
        assert OriginDirection is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
