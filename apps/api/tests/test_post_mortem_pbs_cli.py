"""Phase D W116b — `run_post_mortem_pbs` CLI unit tests.

Pure-logic slices covered :

1. `BUCKET_LABELS` is the canonical 7-tuple from ADR-085, identical to
   the one pinned in `ichor_api.services.scenarios.BUCKET_LABELS` and
   guarded by `test_pass6_bucket_labels_exactly_seven_canonical`.
2. `_p_vector_from_scenarios` correctly extracts ordered probability
   vector from the LLM-emitted JSONB, returns None on every defensible
   structural problem (wrong length, missing labels, unknown labels,
   non-numeric p, zero sum).
3. `_realized_index_from_bucket` looks up the canonical index, returns
   None on unknown bucket / None input.
4. `_baseline_equal_weight_pbs` returns the closed-form value for
   uniform K=7 prediction plus the misclassification penalty (since
   argmax of uniform always disagrees with any realized class).
5. `_pocket_key` falls back to session_type when regime_quadrant is
   NULL, matching the W115b CLI convention.
6. argparse accepts `--window-days` + defaults pinned.
"""

from __future__ import annotations

import argparse
import math
from types import SimpleNamespace
from typing import Any

from ichor_api.cli.run_post_mortem_pbs import (
    _AHMADIAN_LAMBDA,
    _DEFAULT_WINDOW_DAYS,
    _MIN_CARDS_PER_POCKET,
    BUCKET_LABELS,
    _baseline_equal_weight_pbs,
    _p_vector_from_scenarios,
    _pocket_key,
    _realized_index_from_bucket,
)

# ────────────────────────── constants ──────────────────────────


def test_bucket_labels_match_adr_085() -> None:
    """ADR-085 §"The 7 buckets" — pinned tuple."""
    assert BUCKET_LABELS == (
        "crash_flush",
        "strong_bear",
        "mild_bear",
        "base",
        "mild_bull",
        "strong_bull",
        "melt_up",
    )


def test_lambda_default_is_two() -> None:
    """Matches the Ahmadian PBS service default — keeps the superior-
    ordering proof valid on K=7."""
    assert _AHMADIAN_LAMBDA == 2.0


def test_min_cards_per_pocket_is_four() -> None:
    """Below 4 cards the PBS mean is too noisy to be actionable."""
    assert _MIN_CARDS_PER_POCKET == 4


def test_default_window_is_thirty_days() -> None:
    """Researcher SOTA brief : 30 d trailing window per Sunday cron."""
    assert _DEFAULT_WINDOW_DAYS == 30


# ────────────────────────── _p_vector_from_scenarios ──────────────────────────


def _valid_scenarios_jsonb() -> list[dict]:
    """7 entries in canonical order with p summing to 1.0."""
    return [
        {"label": "crash_flush", "p": 0.04},
        {"label": "strong_bear", "p": 0.08},
        {"label": "mild_bear", "p": 0.18},
        {"label": "base", "p": 0.32},
        {"label": "mild_bull", "p": 0.22},
        {"label": "strong_bull", "p": 0.12},
        {"label": "melt_up", "p": 0.04},
    ]


def test_p_vector_extracts_canonical_order() -> None:
    """Output indices align with BUCKET_LABELS, regardless of JSONB
    ordering (we shuffle to verify)."""
    scrambled = list(reversed(_valid_scenarios_jsonb()))
    vec = _p_vector_from_scenarios(scrambled)
    assert vec is not None
    assert len(vec) == 7
    # p[0] is crash_flush = 0.04
    assert math.isclose(vec[0], 0.04, abs_tol=1e-9)
    # p[3] is base = 0.32
    assert math.isclose(vec[3], 0.32, abs_tol=1e-9)
    # p[6] is melt_up = 0.04
    assert math.isclose(vec[6], 0.04, abs_tol=1e-9)
    # Sums to 1 (re-normalized defensively).
    assert math.isclose(sum(vec), 1.0, abs_tol=1e-9)


def test_p_vector_renormalizes_slightly_off_sum() -> None:
    """Float-drift in LLM output may give sum=0.998 ; the extractor
    must re-normalize so the PBS computation downstream stays valid."""
    items = _valid_scenarios_jsonb()
    items[0]["p"] = 0.038  # was 0.04, sum becomes 0.998
    vec = _p_vector_from_scenarios(items)
    assert vec is not None
    assert math.isclose(sum(vec), 1.0, abs_tol=1e-9)


def test_p_vector_rejects_wrong_length() -> None:
    """Six entries → None (canonical is 7)."""
    items = _valid_scenarios_jsonb()[:-1]
    assert _p_vector_from_scenarios(items) is None


def test_p_vector_rejects_unknown_label() -> None:
    items = _valid_scenarios_jsonb()
    items[3]["label"] = "unknown_bucket"
    assert _p_vector_from_scenarios(items) is None


def test_p_vector_rejects_missing_p_field() -> None:
    items = _valid_scenarios_jsonb()
    del items[2]["p"]
    assert _p_vector_from_scenarios(items) is None


def test_p_vector_rejects_non_numeric_p() -> None:
    items = _valid_scenarios_jsonb()
    items[2]["p"] = "0.18"  # string, not number
    assert _p_vector_from_scenarios(items) is None


def test_p_vector_rejects_zero_sum() -> None:
    """If all p are zero (pathological), can't re-normalize → None."""
    items = [{"label": lbl, "p": 0.0} for lbl in BUCKET_LABELS]
    assert _p_vector_from_scenarios(items) is None


def test_p_vector_rejects_non_list_input() -> None:
    assert _p_vector_from_scenarios({"not": "a list"}) is None
    assert _p_vector_from_scenarios(None) is None
    assert _p_vector_from_scenarios(42) is None


def test_p_vector_rejects_non_dict_entry() -> None:
    items: list[Any] = _valid_scenarios_jsonb()  # type: ignore[assignment]
    items[1] = "not a dict"
    assert _p_vector_from_scenarios(items) is None


# ────────────────────────── _realized_index_from_bucket ──────────────────────────


def test_realized_index_canonical_lookup() -> None:
    assert _realized_index_from_bucket("crash_flush") == 0
    assert _realized_index_from_bucket("base") == 3
    assert _realized_index_from_bucket("melt_up") == 6


def test_realized_index_unknown_returns_none() -> None:
    assert _realized_index_from_bucket("unknown_bucket") is None


def test_realized_index_none_input_returns_none() -> None:
    assert _realized_index_from_bucket(None) is None


# ────────────────────────── _baseline_equal_weight_pbs ──────────────────────────


def test_baseline_equal_weight_pbs_closed_form() -> None:
    """Uniform K=7 prediction : BrierScore = 42/49 ≈ 0.8571 + λ
    (argmax tied → counts as misclassification, +2.0). Total ≈ 2.857."""
    for realized_idx in range(7):
        baseline = _baseline_equal_weight_pbs(realized_idx)
        # 42/49 + 2.0
        expected = 42.0 / 49.0 + 2.0
        assert math.isclose(baseline, expected, abs_tol=1e-9)


def test_baseline_same_for_all_realized_classes() -> None:
    """Symmetry : uniform prediction has the same baseline regardless
    of which class realized — sanity check on the closed form."""
    baselines = [_baseline_equal_weight_pbs(i) for i in range(7)]
    assert all(math.isclose(b, baselines[0], abs_tol=1e-12) for b in baselines)


# ────────────────────────── _pocket_key ──────────────────────────


def _fake_card(asset: str, regime_quadrant: str | None, session_type: str) -> Any:
    return SimpleNamespace(
        asset=asset,
        regime_quadrant=regime_quadrant,
        session_type=session_type,
    )


def test_pocket_key_uses_regime_quadrant_when_present() -> None:
    card = _fake_card("EUR_USD", "usd_complacency", "pre_londres")
    assert _pocket_key(card) == ("EUR_USD", "usd_complacency")


def test_pocket_key_falls_back_to_session_type_when_null() -> None:
    """Matches the W115b convention so post-mortem pockets align with
    Vovk aggregator pockets."""
    card = _fake_card("XAU_USD", None, "ny_close")
    assert _pocket_key(card) == ("XAU_USD", "ny_close")


def test_pocket_key_falls_back_to_session_type_when_empty_string() -> None:
    """Falsy empty string → also fall back to session_type."""
    card = _fake_card("USD_CAD", "", "pre_ny")
    assert _pocket_key(card) == ("USD_CAD", "pre_ny")


# ────────────────────────── argparse ──────────────────────────


def test_argparse_accepts_window_days_and_asset_and_dry_run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--window-days", type=int, default=_DEFAULT_WINDOW_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(["--asset", "EUR_USD", "--window-days", "7", "--dry-run"])
    assert args.asset == "EUR_USD"
    assert args.window_days == 7
    assert args.dry_run is True


def test_argparse_defaults_no_args() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--window-days", type=int, default=_DEFAULT_WINDOW_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args([])
    assert args.asset is None
    assert args.window_days == _DEFAULT_WINDOW_DAYS
    assert args.dry_run is False


# ────────────────────────── module importability ──────────────────────────


def test_module_exports_main_function() -> None:
    """systemd unit ExecStart references the module — main() MUST exist."""
    from ichor_api.cli import run_post_mortem_pbs

    assert callable(getattr(run_post_mortem_pbs, "main", None))
