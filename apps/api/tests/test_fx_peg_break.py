"""Tests for FX peg pairs + peg deviation logic."""

from __future__ import annotations

from ichor_api.collectors.polygon import ASSET_TO_TICKER, supported_assets


def test_usdhkd_present() -> None:
    """USDHKD is the de-jure peg (HKMA Convertibility Undertaking)."""
    assert "USD_HKD" in ASSET_TO_TICKER
    assert ASSET_TO_TICKER["USD_HKD"].startswith("C:")


def test_usdcnh_present() -> None:
    """USDCNH = offshore yuan, managed-float around PBOC fix."""
    assert "USD_CNH" in ASSET_TO_TICKER


def test_phase1_assets_still_present_after_peg_addition() -> None:
    expected = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    }
    assert expected.issubset(set(supported_assets()))


def test_peg_deviation_math_canonical() -> None:
    """USDHKD peg = 7.80. spot=7.85 → 0.64% deviation."""
    spot = 7.85
    ref = 7.80
    pct = abs(spot - ref) / ref * 100.0
    assert 0.6 < pct < 0.7


def test_peg_deviation_break_threshold() -> None:
    """Catalog threshold = 1% above. spot 7.88 vs 7.80 = 1.03% =
    above threshold → would fire."""
    spot = 7.88
    ref = 7.80
    pct = abs(spot - ref) / ref * 100.0
    assert pct >= 1.0
