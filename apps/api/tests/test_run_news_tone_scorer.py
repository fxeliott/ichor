"""Unit tests for the news-tone scorer CLI."""

from __future__ import annotations

import pytest

from ichor_api.cli.run_news_tone_scorer import _BATCH_SIZE, _MAX_AGE_HOURS, _signed_score


def test_signed_score_positive() -> None:
    assert _signed_score("positive", 0.8) == 0.8


def test_signed_score_negative_inverts() -> None:
    assert _signed_score("negative", 0.7) == -0.7


def test_signed_score_neutral_is_zero() -> None:
    assert _signed_score("neutral", 0.99) == 0.0


def test_signed_score_unknown_label_falls_to_neutral() -> None:
    """Defensive : if the model returns an unexpected label, treat
    as neutral (don't push fake +/- signal into NEWS_NEGATIVE_BURST)."""
    assert _signed_score("unknown_label", 0.5) == 0.0


def test_batch_size_amortizes_model_overhead() -> None:
    """≥16 batch size is the floor where FinBERT GPU/CPU amortization
    becomes worthwhile."""
    assert _BATCH_SIZE >= 16


def test_max_age_hours_bounds_retry_loop() -> None:
    """If a row stays NULL after this window, we stop retrying."""
    assert _MAX_AGE_HOURS <= 24


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_news_tone_scorer")
    assert hasattr(mod, "run")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_news_tone_scorer import main

    with pytest.raises(SystemExit):
        main(["run_news_tone_scorer", "--help"])
