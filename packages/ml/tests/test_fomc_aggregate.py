"""Tests for FOMC tone aggregation — the only path that doesn't need the
1.4 GB RoBERTa weights to be downloaded.

The classifier itself is mocked via direct construction of FomcToneScore.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest


# Import fomc_roberta directly without going through ichor_ml.__init__,
# which eagerly imports finbert_tone (numpy + transformers). The aggregate
# function only depends on the standard library, so we keep this test light.
_FOMC_PATH = pathlib.Path(__file__).resolve().parents[1] / "src" / "ichor_ml" / "nlp" / "fomc_roberta.py"
_spec = importlib.util.spec_from_file_location("ichor_ml_fomc_roberta_test", _FOMC_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
FomcToneScore = _mod.FomcToneScore
aggregate_fomc_chunks = _mod.aggregate_fomc_chunks


def _score(haw: float, dov: float, neu: float) -> FomcToneScore:
    """Helper: build a FomcToneScore from a softmax-like distribution."""
    dist = {"HAWKISH": haw, "DOVISH": dov, "NEUTRAL": neu}
    label = max(dist, key=lambda k: dist[k])
    return FomcToneScore(label=label, confidence=dist[label], distribution=dist)  # type: ignore[arg-type]


def test_aggregate_empty_returns_zero_baseline() -> None:
    res = aggregate_fomc_chunks([])
    assert res == {
        "net_hawkish": 0.0,
        "mean_hawkish": 0.0,
        "mean_dovish": 0.0,
        "mean_neutral": 0.0,
    }


def test_aggregate_pure_hawkish() -> None:
    res = aggregate_fomc_chunks([_score(0.9, 0.05, 0.05)])
    assert res["net_hawkish"] == pytest.approx(0.85)
    assert res["mean_hawkish"] == pytest.approx(0.9)
    assert res["mean_dovish"] == pytest.approx(0.05)


def test_aggregate_pure_dovish_is_negative() -> None:
    res = aggregate_fomc_chunks([_score(0.05, 0.9, 0.05)])
    assert res["net_hawkish"] == pytest.approx(-0.85)


def test_aggregate_balances_to_zero() -> None:
    """Equal hawkish and dovish chunks → net_hawkish = 0."""
    chunks = [_score(0.8, 0.1, 0.1), _score(0.1, 0.8, 0.1)]
    res = aggregate_fomc_chunks(chunks)
    assert res["net_hawkish"] == pytest.approx(0.0)
    assert res["mean_hawkish"] == pytest.approx(0.45)
    assert res["mean_dovish"] == pytest.approx(0.45)


def test_aggregate_neutral_dominant() -> None:
    res = aggregate_fomc_chunks([_score(0.1, 0.1, 0.8)])
    assert res["mean_neutral"] == pytest.approx(0.8)
    assert abs(res["net_hawkish"]) < 1e-6


def test_net_hawkish_in_range() -> None:
    """Math invariant: net_hawkish ∈ [-1, +1] for any valid distribution."""
    cases = [
        [_score(1.0, 0.0, 0.0)],
        [_score(0.0, 1.0, 0.0)],
        [_score(0.33, 0.33, 0.34)],
        [_score(0.5, 0.5, 0.0)],
    ]
    for chunks in cases:
        res = aggregate_fomc_chunks(chunks)
        assert -1.0 <= res["net_hawkish"] <= 1.0


def test_aggregate_averages_over_chunks() -> None:
    """N chunks → arithmetic mean of per-class scores (not sum)."""
    chunks = [_score(0.8, 0.1, 0.1) for _ in range(5)]
    res = aggregate_fomc_chunks(chunks)
    assert res["mean_hawkish"] == pytest.approx(0.8)
