"""Pure tests for the CB intervention probability model."""

from __future__ import annotations

import pytest

from ichor_api.services.cb_intervention import (
    assess,
    render_intervention_block,
    supported_pairs,
)


# ─────────────────────────── Coverage ──────────────────────────────────


def test_supported_pairs_includes_jpy_chf_cnh() -> None:
    assert "USD_JPY" in supported_pairs()
    assert "EUR_CHF" in supported_pairs()
    assert "USD_CNH" in supported_pairs()


def test_eur_usd_returns_none_no_intervention_history() -> None:
    """G10 crosses without intervention precedent return None."""
    assert assess("EUR_USD", 1.10) is None


def test_aud_usd_returns_none() -> None:
    assert assess("AUD_USD", 0.65) is None


# ─────────────────────────── BoJ on USD/JPY ────────────────────────────


def test_usd_jpy_at_threshold_152_is_50pct() -> None:
    """At the empirical threshold, sigmoid(0) = 0.5 → 50%."""
    risk = assess("USD_JPY", 152.0)
    assert risk is not None
    assert risk.probability_pct == pytest.approx(50.0, abs=0.5)
    assert risk.band == "high"


def test_usd_jpy_at_140_is_low_band() -> None:
    risk = assess("USD_JPY", 140.0)
    assert risk is not None
    assert risk.band == "low"
    assert risk.probability_pct < 10.0


def test_usd_jpy_at_158_is_imminent() -> None:
    risk = assess("USD_JPY", 158.0)
    assert risk is not None
    assert risk.band == "imminent"
    assert risk.probability_pct > 60.0


def test_usd_jpy_at_155_is_high_band() -> None:
    risk = assess("USD_JPY", 155.0)
    assert risk is not None
    assert risk.band in ("high", "imminent")


# ─────────────────────────── SNB on EUR/CHF (inverse) ─────────────────


def test_eur_chf_below_095_is_imminent() -> None:
    """SNB defends CHF strength from below — low spot = high P."""
    risk = assess("EUR_CHF", 0.92)
    assert risk is not None
    assert risk.probability_pct > 60.0
    assert risk.band == "imminent"


def test_eur_chf_above_098_is_low() -> None:
    risk = assess("EUR_CHF", 1.00)
    assert risk is not None
    assert risk.probability_pct < 10.0


def test_eur_chf_at_threshold_095_is_50pct() -> None:
    risk = assess("EUR_CHF", 0.95)
    assert risk is not None
    assert risk.probability_pct == pytest.approx(50.0, abs=0.5)


# ─────────────────────────── PBoC on USD/CNH ───────────────────────────


def test_usd_cnh_at_threshold_730_is_50pct() -> None:
    risk = assess("USD_CNH", 7.30)
    assert risk is not None
    assert risk.probability_pct == pytest.approx(50.0, abs=0.5)


def test_usd_cnh_at_745_is_imminent() -> None:
    risk = assess("USD_CNH", 7.45)
    assert risk is not None
    assert risk.probability_pct > 60.0


# ─────────────────────────── Markdown rendering ────────────────────────


def test_render_intervention_block_includes_threshold_and_band() -> None:
    risk = assess("USD_JPY", 156.0)
    assert risk is not None
    md, sources = render_intervention_block(risk)
    assert "USD_JPY" in md
    assert "156." in md
    assert risk.band in md
    assert "threshold" in md.lower()
    assert sources == ["empirical_model:cb_intervention:USD_JPY"]


def test_render_intervention_block_cites_central_bank() -> None:
    risk = assess("EUR_CHF", 0.92)
    assert risk is not None
    md, _ = render_intervention_block(risk)
    assert "SNB" in md


def test_probability_monotonically_increases_with_distance_for_jpy() -> None:
    """Higher USD/JPY → higher intervention probability."""
    p140 = assess("USD_JPY", 140.0)
    p150 = assess("USD_JPY", 150.0)
    p155 = assess("USD_JPY", 155.0)
    p160 = assess("USD_JPY", 160.0)
    assert p140 and p150 and p155 and p160
    assert p140.probability_pct < p150.probability_pct
    assert p150.probability_pct < p155.probability_pct
    assert p155.probability_pct < p160.probability_pct


def test_probability_monotonically_decreases_with_distance_for_chf() -> None:
    """Higher EUR/CHF → lower intervention probability (SNB direction=-1)."""
    p092 = assess("EUR_CHF", 0.92)
    p095 = assess("EUR_CHF", 0.95)
    p100 = assess("EUR_CHF", 1.00)
    assert p092 and p095 and p100
    assert p092.probability_pct > p095.probability_pct
    assert p095.probability_pct > p100.probability_pct
