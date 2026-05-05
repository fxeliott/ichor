"""Tests for the AGE graph entity extraction.

The AGE write path is NOT unit-tested (would need a live Postgres+AGE
instance). Live integration tested via scripts/hetzner/.
"""

from __future__ import annotations

from ichor_api.graph.populator import extract_entities


def test_extract_eur_usd_synonyms() -> None:
    for text in [
        "EUR/USD jumped 0.5%",
        "EURUSD breakout",
        "the euro is strong against the dollar",
    ]:
        assets, _ = extract_entities(text)
        assert "EUR_USD" in assets


def test_extract_gbp_usd_synonyms() -> None:
    assets, _ = extract_entities("Cable rallies on BoE pivot")
    assert "GBP_USD" in assets


def test_extract_xau_synonyms() -> None:
    assets, _ = extract_entities("Gold prints new ATH at 2961")
    assert "XAU_USD" in assets


def test_extract_index_synonyms() -> None:
    assets, _ = extract_entities("S&P 500 closes at 7230, Nasdaq 100 follows")
    assert "SPX500_USD" in assets
    assert "NAS100_USD" in assets


def test_extract_central_banks() -> None:
    _, insts = extract_entities("Fed and ECB both signaled patience")
    assert "Fed" in insts
    assert "ECB" in insts


def test_extract_lowercase_central_banks() -> None:
    _, insts = extract_entities("the fomc meets next week")
    assert "Fed" in insts


def test_extract_no_match_returns_empty() -> None:
    assets, insts = extract_entities("This article is about the weather")
    assert assets == []
    assert insts == []


def test_extract_multiple_assets_in_one_text() -> None:
    assets, _ = extract_entities("EUR/USD up, USD/JPY down, gold flat")
    assert sorted(assets) == ["EUR_USD", "USD_JPY", "XAU_USD"]


def test_extract_summary_field_also_scanned() -> None:
    assets, insts = extract_entities(
        "Title without entities", "But summary mentions Fed and EUR/USD"
    )
    assert "EUR_USD" in assets
    assert "Fed" in insts


def test_extract_canonical_codes_only() -> None:
    """No ad-hoc codes — only the 8 Phase-0 canonicals."""
    assets, _ = extract_entities("EUR/USD GBP/USD USD/JPY AUD/USD USD/CAD XAU NAS100 SPX500")
    canonical = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    }
    assert set(assets) <= canonical
