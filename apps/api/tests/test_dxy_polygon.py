"""Verify DXY is wired into the polygon collector."""

from __future__ import annotations

from ichor_api.collectors.polygon import ASSET_TO_TICKER, supported_assets


def test_dxy_present_in_asset_map() -> None:
    """DXY must be in the ticker map so _run_polygon picks it up."""
    assert "DXY" in ASSET_TO_TICKER


def test_dxy_uses_indices_namespace() -> None:
    """Polygon convention : I: prefix for indices."""
    assert ASSET_TO_TICKER["DXY"].startswith("I:")


def test_dxy_in_supported_assets_iter() -> None:
    assert "DXY" in supported_assets()


def test_phase1_assets_still_present() -> None:
    """Adding DXY mustn't drop any Phase 1 asset."""
    phase1 = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    }
    actual = set(supported_assets())
    assert phase1.issubset(actual), f"missing: {phase1 - actual}"
