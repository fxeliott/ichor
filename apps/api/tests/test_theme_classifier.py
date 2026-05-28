"""r181 FOUNDATION specs for theme_classifier.py.

Pins the FOUNDATION-only contract :
- Pydantic frozen ThemeRanking shape (fields + types + frozenness)
- ThemeDriverKey Literal 8 canonical drivers (Eliot Fathom transcript
  page 1 étape 1 verbatim)
- THEME_DRIVERS ordered tuple stable render order
- classify_dominant_theme() returns None unconditionally at r181
  (skeleton). r182+ EXECUTION-phase will refine.
- provenance defaults to "practitioner_stamp" per Pattern #20 mechanical
  R59-pre-commit-mandatory (the 8-driver taxonomy is practitioner-stamp,
  NOT peer-reviewed)

Mirror r160 Dukascopy + r174 G5 FOUNDATION test pattern : structural
pinning of the shell, no compute-logic assertions.

Doctrine #5 pure-module discipline : no I/O, no DB hit (the skeleton
fn takes a ``session`` arg but never uses it). CI-gated since r181.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from ichor_api.services.theme_classifier import (
    THEME_DRIVERS,
    ThemeDriverKey,
    ThemeRanking,
    classify_dominant_theme,
)


class TestThemeRankingShape:
    """Pin the FOUNDATION Pydantic frozen shape — fields + types + frozenness."""

    def test_ranking_is_frozen(self) -> None:
        """``ThemeRanking`` MUST be a frozen Pydantic model for cache
        safety + structural-immutability discipline."""
        assert ThemeRanking.model_config.get("frozen") is True

    def test_ranking_has_all_required_fields(self) -> None:
        """The 5 canonical fields documented in the class docstring
        MUST all be present. r182+ EXECUTION consumers depend on this
        exact contract."""
        field_names = set(ThemeRanking.model_fields.keys())
        assert field_names == {
            "top_theme",
            "secondary_themes",
            "driver_strengths",
            "computed_at_utc",
            "provenance",
        }

    def test_ranking_can_be_constructed(self) -> None:
        """Smoke test : valid ranking constructible with realistic
        practitioner-stamp values."""
        ranking = ThemeRanking(
            top_theme="geopolitics",
            secondary_themes=["fiscal_policy", "market_interconnexions"],
            driver_strengths={
                "geopolitics": 0.85,
                "fiscal_policy": 0.62,
                "market_interconnexions": 0.55,
            },
            computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
        )
        assert ranking.top_theme == "geopolitics"
        assert ranking.secondary_themes == [
            "fiscal_policy",
            "market_interconnexions",
        ]
        assert ranking.driver_strengths["geopolitics"] == 0.85
        assert ranking.provenance == "practitioner_stamp"  # default

    def test_ranking_provenance_default_is_practitioner_stamp(self) -> None:
        """Pattern #20 mechanical R59-pre-commit-mandatory : the 8-driver
        taxonomy is practitioner-stamp by default (Eliot Fathom transcript
        page 1) — honest disclosure when no peer-reviewed cite anchors it.
        """
        ranking = ThemeRanking(
            top_theme="macroeconomic",
            computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
        )
        assert ranking.provenance == "practitioner_stamp"

    def test_ranking_extra_fields_forbidden(self) -> None:
        """Pydantic ``extra='forbid'`` MUST reject unknown fields —
        prevents typos + future schema drift."""
        with pytest.raises(Exception):  # noqa: PT011 (Pydantic raises ValidationError)
            ThemeRanking(
                top_theme="macroeconomic",
                computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                unknown_field="should-be-rejected",  # type: ignore[call-arg]
            )

    def test_secondary_themes_max_length_3(self) -> None:
        """Pydantic ``max_length=3`` MUST cap secondary_themes — UI
        constraint (Pass-2 narrative reads at most 3-5 in practice)."""
        with pytest.raises(Exception):  # ValidationError
            ThemeRanking(
                top_theme="macroeconomic",
                secondary_themes=[
                    "monetary_policy",
                    "economic_data",
                    "fiscal_policy",
                    "geopolitics",  # 4th element exceeds max_length=3
                ],
                computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )


class TestThemeDriversCanonicalEight:
    """The 8-driver enum is intentionally bounded — new drivers land
    via Eliot directive update OR R59 sub-agent peer-reviewed cite."""

    def test_canonical_8_drivers_verbatim_eliot_fathom(self) -> None:
        """THEME_DRIVERS MUST contain EXACTLY 8 canonical drivers from
        Eliot Fathom transcript page 1 étape 1, in stable render order."""
        assert THEME_DRIVERS == (
            "macroeconomic",
            "monetary_policy",
            "economic_data",
            "fiscal_policy",
            "market_interconnexions",
            "geopolitics",
            "price_action_flow",
            "supply_demand",
        )

    def test_theme_drivers_tuple_is_immutable(self) -> None:
        """``THEME_DRIVERS`` is a tuple — Python language guarantees
        immutability ; ``Final`` annotation guards against rebinding."""
        assert isinstance(THEME_DRIVERS, tuple)
        with pytest.raises(AttributeError):
            THEME_DRIVERS.append("new_driver")  # type: ignore[attr-defined]

    def test_each_driver_is_constructible_as_top_theme(self) -> None:
        """Cross-driver smoke : each canonical driver constructs cleanly
        as ``top_theme``. Defense-in-depth runtime check that the Literal
        Pydantic field accepts all 8 canonical values."""
        for driver in THEME_DRIVERS:
            ranking = ThemeRanking(
                top_theme=driver,
                computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert ranking.top_theme == driver


class TestThemeDriverKeyLiteral:
    """Literal type alias smoke — used by mypy + pydantic validation."""

    def test_theme_driver_key_is_importable(self) -> None:
        # typing.Literal aliases don't have a stable __args__ accessor ;
        # this test just confirms the type exists and is importable.
        assert ThemeDriverKey is not None


class TestClassifyDominantThemeSkeletonReturnsNone:
    """r181 FOUNDATION : skeleton fn returns None unconditionally.
    r182+ EXECUTION-phase will refine the contract — but the function
    signature (session, *, now_utc) is FROZEN by this ship so consumers
    can integrate incrementally."""

    def test_skeleton_returns_none(self) -> None:
        """r181 FOUNDATION : zero behavior change at deploy. Skeleton
        returns None regardless of inputs. r182+ EXECUTION-phase will
        implement the 5-step compute."""

        async def _run() -> None:
            # Skeleton accepts None for session (it's reserved for r182+)
            result = await classify_dominant_theme(
                session=None,  # type: ignore[arg-type]
                now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )
            assert result is None

        asyncio.run(_run())

    def test_skeleton_returns_none_across_time_window(self) -> None:
        """Skeleton is time-agnostic at FOUNDATION : same None output
        across pre-Londres / NY mid / NY close windows."""

        async def _run() -> None:
            for hour in (7, 13, 20):
                result = await classify_dominant_theme(
                    session=None,  # type: ignore[arg-type]
                    now_utc=datetime(2026, 5, 28, hour, 0, tzinfo=UTC),
                )
                assert result is None, f"hour={hour}: skeleton must return None at r181"

        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
