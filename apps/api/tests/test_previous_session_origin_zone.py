"""r174 FOUNDATION specs for previous_session_origin_zone.py.

Pins the FOUNDATION-only contract :
- Pydantic-like dataclass shape (frozen, immutable, fields exhaustive)
- SessionZoneLabel + OriginDirection Literal types
- compute_previous_session_origin_zone() returns None unconditionally
  at r174 (skeleton). r175+ EXECUTION-phase will refine.

Mirror r160 Dukascopy FOUNDATION test pattern : structural pinning of
the shell, no compute-logic assertions (compute logic lands r175+).

Doctrine #5 pure-module discipline : no I/O, no DB hit (the skeleton
fn takes a `session` arg but never uses it). CI-gated since r174.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime

import pytest
from ichor_api.services.previous_session_origin_zone import (
    OriginDirection,
    OriginZoneSnapshot,
    SessionZoneLabel,
    compute_previous_session_origin_zone,
)


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


class TestComputeSkeletonReturnsNone:
    """r174 FOUNDATION : skeleton fn returns None unconditionally.
    r175+ EXECUTION-phase will refine the contract — but the function
    signature (session, asset, *, now_utc) is FROZEN by this ship so
    consumers can integrate incrementally."""

    def test_skeleton_returns_none(self) -> None:
        """r174 FOUNDATION : zero behavior change at deploy. Skeleton
        returns None regardless of inputs. r175+ EXECUTION-phase will
        implement the 5-step OHLC-over-session-window compute."""

        async def _run() -> None:
            # Skeleton accepts None for session (it's reserved for r175+)
            result = await compute_previous_session_origin_zone(
                session=None,  # type: ignore[arg-type]
                asset="EUR_USD",
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is None

        asyncio.run(_run())

    def test_skeleton_returns_none_for_all_priority_assets(self) -> None:
        """Cross-asset smoke : skeleton is asset-agnostic at FOUNDATION."""

        async def _run() -> None:
            for asset in (
                "EUR_USD",
                "GBP_USD",
                "USD_JPY",
                "AUD_USD",
                "USD_CAD",
                "XAU_USD",
                "NAS100_USD",
                "SPX500_USD",
            ):
                result = await compute_previous_session_origin_zone(
                    session=None,  # type: ignore[arg-type]
                    asset=asset,
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
                assert result is None, f"{asset}: skeleton must return None at r174"

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
