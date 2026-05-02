"""Unit tests for the French TTS text normalizer."""

from __future__ import annotations

from ichor_agents.voice.text_normalize import preprocess_finance_fr


def test_substitutes_currency_pairs() -> None:
    out = preprocess_finance_fr("L'EURUSD a perdu 30 bps face à USDJPY")
    assert "euro-dollar" in out
    assert "dollar-yen" in out
    assert "30 points de base" in out


def test_substitutes_central_banks() -> None:
    out = preprocess_finance_fr("La BCE et le FOMC alignés vs. BoJ dovish")
    assert "B C E" in out
    assert "F O M C" in out
    assert "B O J" in out
    assert "dovish" in out


def test_normalizes_dollar_amounts() -> None:
    out = preprocess_finance_fr("L'auction Treasury de $1.5B suivait $50B précédent")
    assert "1.5 milliards de dollars" in out
    assert "50 milliards de dollars" in out


def test_normalizes_percentages() -> None:
    out = preprocess_finance_fr("Inflation 3.5% vs. 3.2% attendu")
    assert "3,5 pour cent" in out
    assert "3,2 pour cent" in out


def test_strips_markdown() -> None:
    out = preprocess_finance_fr("# Titre\n**Gras** et *italique* avec [un lien](http://x.com)")
    assert "#" not in out
    assert "**" not in out
    assert "Titre" in out
    assert "Gras" in out
    assert "italique" in out
    assert "un lien" in out
    assert "http://x.com" not in out


def test_idempotent() -> None:
    s = "L'EURUSD à 1.0850 vs. la BCE dovish, NFP +200K, $1B inflows"
    out1 = preprocess_finance_fr(s)
    out2 = preprocess_finance_fr(out1)
    assert out1 == out2  # second pass produces no further changes
