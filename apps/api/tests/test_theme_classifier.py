"""r181 FOUNDATION + r182 EXECUTION specs for theme_classifier.py.

r181 (preserved) pins the FOUNDATION-only contract.
r182 (this commit) ships EXECUTION compute logic :
- 4 hetero inputs (FRED VIXCLS + DTWEXBGS + DGS10 + economic_events
  FOMC proximity + economic_events recent high-impact releases +
  GprObservation 90d percentile rank)
- 8-driver strength scoring with practitioner-grade thresholds
- ``_rank_drivers`` pure helper unit-tested in isolation
- DB-touching main async fn tested via AsyncMock + monkeypatch
  on the internal helpers (cleaner than mocking session.execute
  multi-call sequence)

Doctrine #5 pure-module discipline : helper fns are pure (no I/O,
no DB hit at the helper layer for ``_rank_drivers``). The DB-touching
helpers are tested via AsyncMock session.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from ichor_api.services import theme_classifier as tc_mod
from ichor_api.services.theme_classifier import (
    THEME_DRIVERS,
    ThemeDriverKey,
    ThemeRanking,
    _rank_drivers,
    _value_above_percentile,
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


class TestRankDriversPure:
    """r182 EXECUTION : ``_rank_drivers`` pure helper unit tests."""

    def test_returns_none_on_empty_strengths(self) -> None:
        assert _rank_drivers({}) is None

    def test_returns_none_when_top_below_dominance_threshold(self) -> None:
        """All drivers at baseline 0.2 < dominance 0.5 → None."""
        strengths: dict[ThemeDriverKey, float] = dict.fromkeys(THEME_DRIVERS, 0.2)
        assert _rank_drivers(strengths) is None

    def test_picks_argmax_top_with_secondaries(self) -> None:
        """Sorted by strength desc, top=monetary_policy, secondaries
        include drivers > 0.4 in decreasing order, capped at 3."""
        strengths: dict[ThemeDriverKey, float] = {
            "monetary_policy": 0.85,
            "geopolitics": 0.75,
            "market_interconnexions": 0.70,
            "economic_data": 0.50,
            "macroeconomic": 0.30,
            "fiscal_policy": 0.20,
            "price_action_flow": 0.20,
            "supply_demand": 0.20,
        }
        result = _rank_drivers(strengths)
        assert result is not None
        top, secondary = result
        assert top == "monetary_policy"
        assert secondary == [
            "geopolitics",
            "market_interconnexions",
            "economic_data",
        ]  # top 3 above 0.4, decreasing

    def test_secondary_caps_at_max_length_3(self) -> None:
        """Even if 5 drivers are above 0.4, secondary list caps at 3."""
        strengths: dict[ThemeDriverKey, float] = {
            "monetary_policy": 0.9,
            "geopolitics": 0.8,
            "market_interconnexions": 0.7,
            "economic_data": 0.6,
            "macroeconomic": 0.5,
            "fiscal_policy": 0.2,
            "price_action_flow": 0.2,
            "supply_demand": 0.2,
        }
        result = _rank_drivers(strengths)
        assert result is not None
        _, secondary = result
        assert len(secondary) == 3


class TestClassifyDominantThemeExecution:
    """r182 EXECUTION : end-to-end with monkeypatched helpers.

    Pattern : monkeypatch the 4 helpers (``_latest_fred_value``,
    ``_fomc_proximity_days``, ``_count_recent_high_impact_releases``,
    ``_is_ai_gpr_elevated``) to known values, verify
    ``classify_dominant_theme`` ranks correctly.
    """

    def test_returns_none_when_all_inputs_absent(self) -> None:
        """Doctrine #11 calibrated honesty : when no FRED, no FOMC, no
        releases, no GPR → no driver dominates → None."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is None

        asyncio.run(_run())

    def test_monetary_policy_dominates_on_fomc_proximity(self) -> None:
        """FOMC in 2 days → monetary_policy = 0.7 + 0.05*(5-2) = 0.85."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=2)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "monetary_policy"
            assert result.driver_strengths["monetary_policy"] == pytest.approx(0.85)

        asyncio.run(_run())

    def test_geopolitics_dominates_when_gpr_elevated(self) -> None:
        """ai_gpr > 80th percentile → geopolitics = 0.75 dominates."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=True)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "geopolitics"
            assert result.driver_strengths["geopolitics"] == pytest.approx(0.75)

        asyncio.run(_run())

    def test_market_interconnexions_dominates_on_vix_panic(self) -> None:
        """VIX > 30 alone → market_interconnexions = 0.7 dominates
        (DXY absent, so macroeconomic stays at baseline)."""

        async def _run() -> None:
            # Provide VIX=35, but DXY None (so co-occurrence rule
            # doesn't fire and macroeconomic stays baseline).
            async def fake_fred(session: Any, series_id: str, **kwargs: Any) -> float | None:
                return 35.0 if series_id == "VIXCLS" else None

            with (
                patch.object(tc_mod, "_latest_fred_value", side_effect=fake_fred),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "market_interconnexions"
            assert result.driver_strengths["market_interconnexions"] == pytest.approx(0.7)

        asyncio.run(_run())

    def test_economic_data_dominates_on_multiple_releases(self) -> None:
        """3 recent high-impact releases → economic_data = 0.7 dominates."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=3)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "economic_data"
            assert result.driver_strengths["economic_data"] == pytest.approx(0.7)

        asyncio.run(_run())

    def test_macroeconomic_dominates_on_vix_panic_dxy_extreme_cooccurrence(
        self,
    ) -> None:
        """VIX > 30 AND DXY > 105 co-occurrence → macroeconomic = 0.65
        ; market_interconnexions = 0.7 wins as top, macroeconomic in
        secondary."""

        async def _run() -> None:
            async def fake_fred(session: Any, series_id: str, **kwargs: Any) -> float | None:
                if series_id == "VIXCLS":
                    return 35.0
                if series_id == "DTWEXBGS":
                    return 108.0  # > 105 threshold
                return None

            with (
                patch.object(tc_mod, "_latest_fred_value", side_effect=fake_fred),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            # market_interconnexions (0.7) > macroeconomic (0.65) → top
            assert result.top_theme == "market_interconnexions"
            assert "macroeconomic" in result.secondary_themes
            assert result.driver_strengths["macroeconomic"] == pytest.approx(0.65)

        asyncio.run(_run())

    def test_multi_driver_coincidence_picks_strongest(self) -> None:
        """FOMC + gpr elevated + VIX panic all firing → monetary_policy
        wins (0.85 max FOMC distance=0), geopolitics + market_inter
        in secondary, ADR-017 boundary preserved."""

        async def _run() -> None:
            async def fake_fred(session: Any, series_id: str, **kwargs: Any) -> float | None:
                return 32.0 if series_id == "VIXCLS" else None

            with (
                patch.object(tc_mod, "_latest_fred_value", side_effect=fake_fred),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=True)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "monetary_policy"
            assert result.driver_strengths["monetary_policy"] == pytest.approx(0.95)
            assert "geopolitics" in result.secondary_themes
            assert "market_interconnexions" in result.secondary_themes
            assert result.provenance == "practitioner_stamp"

        asyncio.run(_run())


class TestValueAbovePercentilePure:
    """r189 : shared ``_value_above_percentile`` pure helper (Doctrine #4
    SSOT — used by both the GPR and the VVIX/SKEW drivers)."""

    def test_returns_false_on_insufficient_history(self) -> None:
        """< 30 observations → honest absence (False), Cohen 1988 floor."""
        assert _value_above_percentile([100.0] * 29, 0.80) is False

    def test_returns_false_on_empty(self) -> None:
        assert _value_above_percentile([], 0.80) is False

    def test_today_at_top_is_above_percentile(self) -> None:
        """Newest value is the max → percentile rank 1.0 ≥ 0.80 → True."""
        values = [50.0] + [float(i) for i in range(40)]  # newest=50 > all
        assert _value_above_percentile(values, 0.80) is True

    def test_today_at_bottom_is_below_percentile(self) -> None:
        """Newest value is the min → low percentile → False."""
        values = [-1.0] + [float(i) for i in range(40)]  # newest=-1 < all
        assert _value_above_percentile(values, 0.80) is False

    def test_today_at_median_below_80th(self) -> None:
        """Newest value near the median (~52nd pct) < 80th → False."""
        values = [20.0] + [float(i) for i in range(41)]
        assert _value_above_percentile(values, 0.80) is False


class TestPriceActionFlowDriver:
    """r189 EXECUTION : price_action_flow wired via VVIX/SKEW percentile.

    The DB-touching ``_is_price_action_flow_elevated`` is monkeypatched
    here (its own percentile logic is covered by
    ``TestValueAbovePercentilePure``) — same pattern as the GPR driver."""

    def test_price_action_flow_dominates_when_vol_of_vol_elevated(self) -> None:
        """VVIX OR SKEW above 80th pct → price_action_flow = 0.7 dominates
        (all other drivers at/below baseline ; VIX absent → market_inter 0.3)."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=True)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is not None
            assert result.top_theme == "price_action_flow"
            assert result.driver_strengths["price_action_flow"] == pytest.approx(0.7)

        asyncio.run(_run())

    def test_price_action_flow_baseline_when_not_elevated(self) -> None:
        """Not elevated + nothing else firing → all baseline → None
        (honest absence, doctrine #11)."""

        async def _run() -> None:
            with (
                patch.object(tc_mod, "_latest_fred_value", AsyncMock(return_value=None)),
                patch.object(tc_mod, "_fomc_proximity_days", AsyncMock(return_value=None)),
                patch.object(
                    tc_mod, "_count_recent_high_impact_releases", AsyncMock(return_value=0)
                ),
                patch.object(tc_mod, "_count_recent_fiscal_events", AsyncMock(return_value=0)),
                patch.object(
                    tc_mod, "_is_price_action_flow_elevated", AsyncMock(return_value=False)
                ),
                patch.object(tc_mod, "_is_ai_gpr_elevated", AsyncMock(return_value=False)),
            ):
                result = await classify_dominant_theme(
                    session=AsyncMock(),
                    now_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
                )
            assert result is None

        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
