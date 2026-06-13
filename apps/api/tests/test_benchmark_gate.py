"""Tests for ``benchmark_gate`` (ADR-114, Chantier A slice-1).

Every numeric assertion is hand-computed in the docstring of its test so the
maths is verified, not tautological.
"""

from __future__ import annotations

from datetime import date

import pytest
from ichor_api.services.benchmark_gate import (
    BenchmarkReport,
    VerdictOutcomeSample,
    _assert_adr017_clean,
    _compute_metrics,
    _persistence_predictions,
    _position_return_pct,
    _sorted_by_asset_date,
    brier_score,
    classic_buy_and_hold_total_return_pct,
    evaluate,
    evaluate_walk_forward,
    format_report_markdown,
    hit_rate_ci95,
    walk_forward_splits,
)


def _s(
    *,
    asset: str = "EUR_USD",
    day: int,
    predicted: str = "neutral",
    conviction: float = 0.0,
    realized: float,
) -> VerdictOutcomeSample:
    return VerdictOutcomeSample(
        asset=asset,
        session_date=date(2026, 5, day),
        predicted_direction=predicted,  # type: ignore[arg-type]
        conviction_pct=conviction,
        realized_return_pct=realized,
    )


class TestPositionReturn:
    def test_long_pays_cost(self) -> None:
        # up, realized +1.0, cost 0.1 → 1.0 - 0.1 = 0.9
        assert _position_return_pct("up", 1.0, 0.1) == pytest.approx(0.9)

    def test_short_on_up_loses_plus_cost(self) -> None:
        # down, realized +1.0, cost 0.1 → -1.0 - 0.1 = -1.1
        assert _position_return_pct("down", 1.0, 0.1) == pytest.approx(-1.1)

    def test_short_on_down_wins(self) -> None:
        # down, realized -1.0, cost 0.1 → +1.0 - 0.1 = 0.9
        assert _position_return_pct("down", -1.0, 0.1) == pytest.approx(0.9)

    def test_neutral_is_flat_no_cost(self) -> None:
        assert _position_return_pct("neutral", 5.0, 0.1) == 0.0


class TestRealizedDirection:
    def test_dead_band_is_inclusive_neutral(self) -> None:
        # exactly on the band → neutral (not strictly greater)
        assert _s(day=1, realized=0.1).realized_direction(0.1) == "neutral"
        assert _s(day=1, realized=0.11).realized_direction(0.1) == "up"
        assert _s(day=1, realized=-0.11).realized_direction(0.1) == "down"
        assert _s(day=1, realized=0.05).realized_direction(0.1) == "neutral"


# Shared 4-session single-asset fixture (dead_band=0, cost=0 unless noted).
# realized dirs: s1 up(+1.0), s2 down(-2.0), s3 up(+0.5), s4 neutral(0.0)
def _four_samples(predicted: list[str]) -> list[VerdictOutcomeSample]:
    realized = [1.0, -2.0, 0.5, 0.0]
    return [_s(day=i + 1, predicted=predicted[i], realized=realized[i]) for i in range(4)]


class TestComputeMetrics:
    def test_ichor_headline(self) -> None:
        """ichor preds [up,down,down,up], cost 0:
        nets = +1.0, +2.0(short on -2), -0.5(short on +0.5), 0.0 → total 2.5
        hits = up/up✓, down/down✓, down/up✗, up/neutral✗ → 2/4 = 0.5
        wins = +1>0, +2>0, -0.5, 0.0 → 2/4 = 0.5
        """
        samples = _four_samples(["up", "down", "down", "up"])
        m = _compute_metrics(
            "ichor",
            samples,
            ["up", "down", "down", "up"],
            cost_pct=0.0,
            dead_band_pct=0.0,
        )
        assert m.total_return_pct == pytest.approx(2.5)
        assert m.n_positions == 4
        assert m.coverage == pytest.approx(1.0)
        assert m.hit_rate == pytest.approx(0.5)
        assert m.win_rate == pytest.approx(0.5)
        assert m.mean_return_per_session_pct == pytest.approx(0.625)

    def test_cost_shifts_total_by_cost_per_position(self) -> None:
        """Same as above with cost 0.1 over 4 positions → 2.5 - 4*0.1 = 2.1."""
        samples = _four_samples(["up", "down", "down", "up"])
        m = _compute_metrics(
            "ichor",
            samples,
            ["up", "down", "down", "up"],
            cost_pct=0.1,
            dead_band_pct=0.0,
        )
        assert m.total_return_pct == pytest.approx(2.1)

    def test_always_long(self) -> None:
        """always-long [up,up,up,up], cost 0:
        nets = +1.0, -2.0, +0.5, 0.0 → total -0.5 ; hits 2/4 ; wins 2/4."""
        samples = _four_samples(["up", "down", "down", "up"])
        m = _compute_metrics(
            "always_long",
            samples,
            ["up", "up", "up", "up"],
            cost_pct=0.0,
            dead_band_pct=0.0,
        )
        assert m.total_return_pct == pytest.approx(-0.5)
        assert m.hit_rate == pytest.approx(0.5)
        assert m.win_rate == pytest.approx(0.5)

    def test_length_mismatch_raises(self) -> None:
        samples = _four_samples(["up", "down", "down", "up"])
        with pytest.raises(ValueError, match="same length"):
            _compute_metrics("x", samples, ["up"], cost_pct=0.0, dead_band_pct=0.0)

    def test_all_neutral_has_no_rates(self) -> None:
        samples = _four_samples(["neutral"] * 4)
        m = _compute_metrics("x", samples, ["neutral"] * 4, cost_pct=0.0, dead_band_pct=0.0)
        assert m.n_positions == 0
        assert m.hit_rate is None
        assert m.win_rate is None
        assert m.total_return_pct == 0.0


class TestPersistence:
    def test_causal_per_asset(self) -> None:
        """Single asset s1..s4 realised up,down,up,neutral.
        persistence preds: neutral(no prior), up(s1), down(s2), up(s3)."""
        samples = _four_samples(["neutral"] * 4)  # predicted irrelevant here
        preds = _persistence_predictions(samples, dead_band_pct=0.0)
        assert preds == ["neutral", "up", "down", "up"]

    def test_first_of_each_asset_is_neutral(self) -> None:
        samples = [
            _s(asset="EUR_USD", day=1, realized=1.0),
            _s(asset="XAU_USD", day=1, realized=-1.0),
            _s(asset="EUR_USD", day=2, realized=-1.0),
        ]
        preds = _persistence_predictions(_sorted_by_asset_date(samples), dead_band_pct=0.0)
        # sorted: EUR d1, EUR d2, XAU d1
        # EUR d1 → neutral ; EUR d2 → up (EUR d1 was +1) ; XAU d1 → neutral
        assert preds == ["neutral", "up", "neutral"]


class TestClassicBuyHold:
    def test_single_round_trip_cost(self) -> None:
        # sum realised = 1.0-2.0+0.5+0.0 = -0.5 ; minus one cost 0.1 → -0.6
        samples = _four_samples(["neutral"] * 4)
        assert classic_buy_and_hold_total_return_pct(samples, cost_pct=0.1) == pytest.approx(-0.6)

    def test_empty(self) -> None:
        assert classic_buy_and_hold_total_return_pct([], cost_pct=0.1) == 0.0


class TestBrier:
    def test_hand_computed(self) -> None:
        """s1 up/conv80/realized up → (0.8-1)^2=0.04
        s2 down/conv60/realized down → (0.6-1)^2=0.16
        s3 down/conv50/realized up → (0.5-0)^2=0.25
        s4 neutral → skipped
        brier = (0.04+0.16+0.25)/3 = 0.15
        """
        samples = [
            _s(day=1, predicted="up", conviction=80, realized=1.0),
            _s(day=2, predicted="down", conviction=60, realized=-2.0),
            _s(day=3, predicted="down", conviction=50, realized=0.5),
            _s(day=4, predicted="neutral", conviction=0, realized=0.0),
        ]
        assert brier_score(samples, dead_band_pct=0.0) == pytest.approx(0.15)

    def test_none_when_all_neutral(self) -> None:
        samples = _four_samples(["neutral"] * 4)
        assert brier_score(samples, dead_band_pct=0.0) is None


class TestWalkForwardSplits:
    def test_rolling_windows(self) -> None:
        # n=10, train=4, test=2, step=2 → 3 splits
        splits = walk_forward_splits(10, train_size=4, test_size=2, step=2)
        assert splits == [
            ((0, 1, 2, 3), (4, 5)),
            ((2, 3, 4, 5), (6, 7)),
            ((4, 5, 6, 7), (8, 9)),
        ]

    def test_too_short_returns_empty(self) -> None:
        assert walk_forward_splits(5, train_size=4, test_size=2, step=2) == []

    def test_invalid_sizes_raise(self) -> None:
        with pytest.raises(ValueError):
            walk_forward_splits(10, train_size=0, test_size=2, step=1)


class TestEvaluate:
    def test_in_sample_report(self) -> None:
        samples = _four_samples(["up", "down", "down", "up"])
        report = evaluate(samples, cost_pct=0.0, dead_band_pct=0.0)
        assert isinstance(report, BenchmarkReport)
        assert report.window == "in_sample"
        assert report.n_sessions == 4
        assert report.assets == ("EUR_USD",)
        assert report.ichor.total_return_pct == pytest.approx(2.5)
        assert report.always_long.total_return_pct == pytest.approx(-0.5)
        assert report.persistence.total_return_pct == pytest.approx(-2.5)
        # ichor 2.5 > always_long -0.5 and > persistence -2.5
        assert report.ichor_beats_always_long is True
        assert report.ichor_beats_persistence is True
        assert "confirmé" in report.honest_verdict

    def test_honest_verdict_is_adr017_clean(self) -> None:
        report = evaluate(_four_samples(["up", "down", "down", "up"]))
        # must not smuggle a trade token
        _assert_adr017_clean(report.honest_verdict)

    def test_empty_samples_does_not_crash(self) -> None:
        report = evaluate([])
        assert report.n_sessions == 0
        assert report.ichor.hit_rate is None
        assert report.brier is None
        assert report.ichor_beats_always_long is False  # 0 > 0 is False

    def test_no_fabricated_win_when_ichor_loses(self) -> None:
        # ichor always wrong-way (short every up) → should lose to always_long
        realized = [1.0, 1.0, 1.0, 1.0]
        samples = [_s(day=i + 1, predicted="down", realized=realized[i]) for i in range(4)]
        report = evaluate(samples)
        assert report.ichor_beats_always_long is False
        assert "non confirmé" in report.honest_verdict


class TestEvaluateWalkForward:
    def test_thin_history_returns_none(self) -> None:
        samples = [_s(day=i + 1, predicted="up", realized=1.0) for i in range(3)]
        assert evaluate_walk_forward(samples, train_size=4, test_size=2, step=2) is None

    def test_pools_out_of_sample_test_windows(self) -> None:
        # 8 sessions single asset, train=4,test=2,step=2 → test idx {4,5,6,7}
        samples = [_s(day=i + 1, predicted="up", realized=1.0) for i in range(8)]
        report = evaluate_walk_forward(samples, train_size=4, test_size=2, step=2)
        assert report is not None
        assert report.window == "walk_forward_oos"
        assert report.n_sessions == 4  # only the pooled test sessions

    def test_overlapping_test_windows_counted_once(self) -> None:
        # step=1 makes test windows overlap; each session counted once
        samples = [_s(day=i + 1, predicted="up", realized=1.0) for i in range(8)]
        report = evaluate_walk_forward(samples, train_size=4, test_size=2, step=1)
        assert report is not None
        # splits test windows: (4,5),(5,6),(6,7) → unique {4,5,6,7} = 4
        assert report.n_sessions == 4

    def test_multi_asset_pooling_isolates_per_asset_indices(self) -> None:
        """Two assets, 6 sessions each, train=4/test=2/step=2 → per asset one
        split with test idx {4,5}; pooled across both assets = 4 OOS sessions.
        Proves ``seen_test`` resets per asset (a shared set would let asset B's
        idx collide with asset A's and silently drop sessions)."""
        rows = [(a, i) for a in ("EUR_USD", "XAU_USD") for i in range(6)]
        samples = [_s(asset=a, day=i + 1, predicted="up", realized=1.0) for a, i in rows]
        report = evaluate_walk_forward(samples, train_size=4, test_size=2, step=2)
        assert report is not None
        assert report.n_sessions == 4  # 2 OOS sessions × 2 assets, none dropped
        assert report.assets == ("EUR_USD", "XAU_USD")


class TestVerdictOutcomeSampleValidation:
    """ADR-022 fail-closed boundary on the module's own input (verifier-flagged
    minor: the dataclass field was previously unvalidated)."""

    def test_rejects_conviction_above_cap(self) -> None:
        with pytest.raises(ValueError, match="ADR-022"):
            _s(day=1, conviction=95.01, realized=1.0)

    def test_rejects_negative_conviction(self) -> None:
        with pytest.raises(ValueError, match="ADR-022"):
            _s(day=1, conviction=-0.1, realized=1.0)

    def test_accepts_boundary_values(self) -> None:
        assert _s(day=1, conviction=0.0, realized=1.0).conviction_pct == 0.0
        assert _s(day=1, conviction=95.0, realized=1.0).conviction_pct == 95.0


class TestAdr017Guard:
    def test_forbidden_token_raises(self) -> None:
        with pytest.raises(ValueError, match="ADR-017"):
            _assert_adr017_clean("you should BUY now")

    def test_clean_text_passes(self) -> None:
        # pass-through: clean text is returned VERBATIM (not merely "not None",
        # which a bare truthy-string return would satisfy tautologically).
        assert _assert_adr017_clean("rendu net 1.2% vs baseline") == "rendu net 1.2% vs baseline"


class TestFormatReportMarkdown:
    def _realistic_dataset(self) -> list[VerdictOutcomeSample]:
        # 2 assets, 6 sessions each, mixed directions/outcomes — realistic shape.
        rows = [
            ("EUR_USD", "up", 70, 0.6),
            ("EUR_USD", "up", 65, -0.3),
            ("EUR_USD", "down", 55, -0.4),
            ("EUR_USD", "neutral", 0, 0.02),
            ("EUR_USD", "up", 80, 0.9),
            ("EUR_USD", "down", 60, 0.1),
            ("XAU_USD", "down", 75, -1.1),
            ("XAU_USD", "up", 50, 0.2),
            ("XAU_USD", "down", 68, -0.5),
            ("XAU_USD", "neutral", 0, -0.01),
            ("XAU_USD", "up", 72, 0.7),
            ("XAU_USD", "down", 58, -0.2),
        ]
        return [
            _s(asset=a, day=i + 1, predicted=d, conviction=c, realized=r)
            for i, (a, d, c, r) in enumerate(rows)
        ]

    def test_full_pipeline_renders_report(self) -> None:
        report = evaluate(self._realistic_dataset(), cost_pct=0.02, dead_band_pct=0.05)
        md = format_report_markdown(report)
        # structural assertions — the report is the gate-A deliverable
        assert "# Benchmark gate" in md
        assert "Seances : **12**" in md
        assert "| ichor |" in md
        assert "| always_long |" in md
        assert "| persistence |" in md
        assert "EUR_USD" in md and "XAU_USD" in md
        assert report.honest_verdict in md
        # ADR-017 : not a single trade token in the whole rendered report
        # (format_report_markdown also runs _assert_adr017_clean internally)
        assert "BUY" not in md.upper()
        assert "SELL" not in md.upper()

    def test_walk_forward_report_renders(self) -> None:
        report = evaluate_walk_forward(
            self._realistic_dataset(),
            train_size=3,
            test_size=2,
            step=2,
            cost_pct=0.02,
            dead_band_pct=0.05,
        )
        assert report is not None
        assert report.window == "walk_forward_oos"
        md = format_report_markdown(report)
        assert "walk_forward_oos" in md

    def test_empty_report_renders_without_crash(self) -> None:
        md = format_report_markdown(evaluate([]))
        assert "Seances : **0**" in md
        assert "(aucun)" in md


class TestHitRateCi95:
    def test_hand_computed(self) -> None:
        """hit 0.5, n 100 → se = sqrt(0.25/100) = 0.05 ; half = 1.96*0.05 ≈ 0.098
        → CI ≈ [0.402, 0.598]."""
        ci = hit_rate_ci95(0.5, 100)
        assert ci is not None
        lo, hi = ci
        assert lo == pytest.approx(0.40200361, abs=1e-4)
        assert hi == pytest.approx(0.59799639, abs=1e-4)

    def test_none_without_positions(self) -> None:
        assert hit_rate_ci95(None, 10) is None
        assert hit_rate_ci95(0.5, 0) is None

    def test_bounds_are_clamped(self) -> None:
        # hit 0.95, n 4 → wide CI overshoots 1.0 → clamped
        ci = hit_rate_ci95(0.95, 4)
        assert ci is not None
        assert ci[1] == 1.0
        assert 0.0 <= ci[0] <= 1.0


class TestSignificanceSection:
    def test_thin_sample_warns(self) -> None:
        # 4 sessions ≪ 60 → small-sample warning rendered
        report = evaluate(_four_samples(["up", "down", "down", "up"]))
        md = format_report_markdown(report)
        assert "Significativite" in md
        assert "echantillon mince" in md
        assert "4 seances" in md

    def test_no_positions_states_nothing_to_test(self) -> None:
        report = evaluate(_four_samples(["neutral"] * 4))
        md = format_report_markdown(report)
        assert "aucune position directionnelle" in md

    def test_ci_spanning_half_flags_chance(self) -> None:
        # ichor wrong half the time on a tiny sample → CI spans 0.5
        report = evaluate(_four_samples(["up", "down", "down", "up"]))
        md = format_report_markdown(report)
        assert "indistinguible du hasard" in md
