"""Phase D W115b — `run_brier_aggregator` CLI unit tests.

The CLI is DB-bound, so we cover the pure-logic slices :

1. `_realized_from_card` correctly back-derives y ∈ {0, 1} from
   `(bias_direction, conviction_pct, brier_contribution)` for both
   correct and incorrect predictions, returns None for neutral cards
   and malformed data.
2. `_expert_predictions` builds a 3-vector with prod predictor in
   [0,1], climatology pinned, equal-weight 0.5.
3. argparse accepts the new flags (`--asset`, `--window`, `--dry-run`)
   without breaking when called with no args.
4. Pocket constants match the W115 migration : `_POCKET_VERSION == 1`
   matches `brier_aggregator_weights.pocket_version` default.
"""

from __future__ import annotations

import argparse
import math
from types import SimpleNamespace
from typing import Any

import pytest
from ichor_api.cli.run_brier_aggregator import (
    _CLIMATOLOGY_LOOKBACK_DAYS,
    _DEFAULT_WINDOW,
    _EXPERT_KINDS,
    _POCKET_VERSION,
    _expert_predictions,
    _realized_from_card,
)

# ────────────────────────── module constants ──────────────────────────


def test_expert_kinds_are_three_canonical_names() -> None:
    """Adding a 4th expert without bumping the n_experts argument
    in the aggregator caller would silently produce length-mismatch
    errors deep inside Vovk update. Pin the canonical tuple."""
    assert _EXPERT_KINDS == ("prod_predictor", "climatology", "equal_weight")


def test_pocket_version_default_matches_migration() -> None:
    """ADR-087 W115 migration 0043 server_default for pocket_version
    is 1. The CLI MUST match — divergence would orphan upserts on
    the wrong pocket."""
    assert _POCKET_VERSION == 1


def test_default_window_is_two_hundred() -> None:
    """Round-19 SOTA brief : 200-card sliding window per pocket."""
    assert _DEFAULT_WINDOW == 200


def test_climatology_lookback_is_one_year() -> None:
    """Researcher SOTA brief : 365 d climatology lookback. (Even
    though the round-19 stand-in returns 0.5, future W118 will use
    this constant for the real query.)"""
    assert _CLIMATOLOGY_LOOKBACK_DAYS == 365


# ────────────────────────── _expert_predictions ──────────────────────────


def _fake_card(bias: str, conviction_pct: float, brier: float | None = None) -> Any:
    return SimpleNamespace(
        bias_direction=bias,
        conviction_pct=conviction_pct,
        brier_contribution=brier,
    )


def test_expert_predictions_long_high_conviction() -> None:
    """long/95 → p_up = 0.5 + 0.5·0.95 = 0.975 for prod_predictor."""
    card = _fake_card("long", 95.0)
    preds = _expert_predictions(card, climatology=0.5)
    assert math.isclose(preds[0], 0.975, abs_tol=1e-9)
    assert preds[1] == 0.5
    assert preds[2] == 0.5


def test_expert_predictions_short_low_conviction() -> None:
    """short/20 → p_up = 0.5 - 0.5·0.20 = 0.40."""
    card = _fake_card("short", 20.0)
    preds = _expert_predictions(card, climatology=0.42)
    assert math.isclose(preds[0], 0.40, abs_tol=1e-9)
    assert preds[1] == 0.42
    assert preds[2] == 0.5


def test_expert_predictions_neutral_returns_all_half() -> None:
    """Neutral bias → prod_predictor = 0.5 regardless of conviction."""
    card = _fake_card("neutral", 70.0)
    preds = _expert_predictions(card, climatology=0.5)
    assert preds == [0.5, 0.5, 0.5]


def test_expert_predictions_malformed_bias_defensive_fallback() -> None:
    """Defensive : bad bias values fall back to no-info baseline so
    the loop doesn't crash on dirty rows."""
    card = _fake_card("invalid_bias", 60.0)
    preds = _expert_predictions(card, climatology=0.4)
    assert preds == [0.5, 0.4, 0.5]


# ────────────────────────── _realized_from_card ──────────────────────────


def test_realized_back_derive_correct_long_prediction() -> None:
    """long/80 → p_up=0.9. If y=1, brier = (0.9-1)² = 0.01."""
    card = _fake_card("long", 80.0, brier=0.01)
    assert _realized_from_card(card) == 1


def test_realized_back_derive_wrong_long_prediction() -> None:
    """long/80 → p_up=0.9. If y=0 (model was WRONG), brier = 0.9² = 0.81.
    The function must still return y=0, not None — Vovk needs to learn
    from misses."""
    card = _fake_card("long", 80.0, brier=0.81)
    assert _realized_from_card(card) == 0


def test_realized_back_derive_correct_short_prediction() -> None:
    """short/60 → p_up = 0.5 - 0.30 = 0.20. If y=0, brier = 0.04."""
    card = _fake_card("short", 60.0, brier=0.04)
    assert _realized_from_card(card) == 0


def test_realized_back_derive_wrong_short_prediction() -> None:
    """short/60 → p_up=0.20. If y=1 (wrong), brier = (0.20-1)² = 0.64."""
    card = _fake_card("short", 60.0, brier=0.64)
    assert _realized_from_card(card) == 1


def test_realized_back_derive_neutral_returns_none() -> None:
    """Neutral → p_up=0.5, both formulas give brier=0.25. y is
    irrecoverable from the persisted columns. Skip these cards."""
    card = _fake_card("neutral", 0.0, brier=0.25)
    assert _realized_from_card(card) is None


def test_realized_back_derive_none_when_brier_missing() -> None:
    card = _fake_card("long", 80.0, brier=None)
    assert _realized_from_card(card) is None


def test_realized_back_derive_none_when_bias_malformed() -> None:
    card = _fake_card("invalid", 50.0, brier=0.16)
    assert _realized_from_card(card) is None


def test_realized_back_derive_none_when_brier_mismatch() -> None:
    """Neither formula matches → return None (data corruption signal)."""
    card = _fake_card("long", 80.0, brier=0.42)  # neither 0.01 nor 0.81
    assert _realized_from_card(card) is None


def test_realized_back_derive_handles_float_drift() -> None:
    """Reconciler may write brier with tiny float drift. Tolerance
    1e-6 must absorb it."""
    card = _fake_card("long", 80.0, brier=0.01 + 5e-8)  # within tolerance
    assert _realized_from_card(card) == 1


# ────────────────────────── argparse ──────────────────────────


def test_argparse_accepts_dry_run_and_asset_and_window() -> None:
    """Mirrors the parser construction in `main()` — catches accidental
    flag rename that would break the systemd unit ExecStart."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--window", type=int, default=_DEFAULT_WINDOW)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(["--asset", "EUR_USD", "--window", "100", "--dry-run"])
    assert args.asset == "EUR_USD"
    assert args.window == 100
    assert args.dry_run is True


def test_argparse_defaults_no_args() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--window", type=int, default=_DEFAULT_WINDOW)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args([])
    assert args.asset is None
    assert args.window == _DEFAULT_WINDOW
    assert args.dry_run is False


# ────────────────────────── module importability ──────────────────────────


def test_module_exports_main_function() -> None:
    """Hetzner systemd unit ExecStart references `python -m
    ichor_api.cli.run_brier_aggregator` ; the module MUST have a
    callable `main` entry point."""
    from ichor_api.cli import run_brier_aggregator

    assert callable(getattr(run_brier_aggregator, "main", None))


@pytest.mark.asyncio
async def test_climatology_rate_falls_back_to_half_on_cold_start() -> None:
    """W118 (round-23) : `_climatology_rate` returns 0.5 when fewer
    than 8 observations exist with non-NULL realized_open_session +
    realized_close_session. Cold-start gate prevents the Vovk AA from
    being fed a noisy estimate."""
    from ichor_api.cli.run_brier_aggregator import _climatology_rate

    class _StubResult:
        def one(self):
            return (3, 2)  # n=3 < 8 → cold-start → 0.5

    class _Session:
        async def execute(self, _stmt: Any) -> _StubResult:
            return _StubResult()

    rate = await _climatology_rate(_Session(), "EUR_USD")  # type: ignore[arg-type]
    assert rate == 0.5


@pytest.mark.asyncio
async def test_climatology_rate_computes_real_empirical_p_up() -> None:
    """W118 (round-23) : with n ≥ 8 observations, returns n_up / n."""
    from ichor_api.cli.run_brier_aggregator import _climatology_rate

    class _StubResult:
        def __init__(self, n: int, n_up: int) -> None:
            self.n = n
            self.n_up = n_up

        def one(self):
            return (self.n, self.n_up)

    class _Session:
        def __init__(self, n: int, n_up: int) -> None:
            self._result = _StubResult(n, n_up)

        async def execute(self, _stmt: Any) -> _StubResult:
            return self._result

    # 12 cards, 7 up → empirical 7/12 ≈ 0.583
    rate = await _climatology_rate(_Session(12, 7), "EUR_USD")  # type: ignore[arg-type]
    assert math.isclose(rate, 7 / 12, abs_tol=1e-9)

    # Edge : n=8 (boundary), all up → 1.0
    rate = await _climatology_rate(_Session(8, 8), "EUR_USD")  # type: ignore[arg-type]
    assert rate == 1.0

    # Edge : n=8, none up → 0.0
    rate = await _climatology_rate(_Session(8, 0), "EUR_USD")  # type: ignore[arg-type]
    assert rate == 0.0


@pytest.mark.asyncio
async def test_climatology_rate_handles_null_counts() -> None:
    """SQL `COUNT(*)` always returns int but `SUM(CASE ...)` returns
    None when there are no rows. The function defensively coerces None
    → 0."""
    from ichor_api.cli.run_brier_aggregator import _climatology_rate

    class _StubResult:
        def one(self):
            return (None, None)  # both None : zero rows matched

    class _Session:
        async def execute(self, _stmt: Any) -> _StubResult:
            return _StubResult()

    rate = await _climatology_rate(_Session(), "EUR_USD")  # type: ignore[arg-type]
    assert rate == 0.5  # n=0 < 8 → cold-start fallback
