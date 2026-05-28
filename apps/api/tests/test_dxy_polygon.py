"""Verify DXY is wired into the polygon collector."""

from __future__ import annotations

from ichor_api.collectors.polygon import ASSET_TO_TICKER, supported_assets


def test_dxy_present_in_asset_map() -> None:
    """DXY must be in the ticker map so _run_polygon picks it up."""
    assert "DXY" in ASSET_TO_TICKER


def test_dxy_uses_uup_etf_proxy() -> None:
    """r172 : DXY is aliased to UUP (NYSE Arca ETF), NOT the I: indices
    namespace — the Polygon Indices plan is unbudgeted, so I:DXY returns
    403. Mirrors the SPX500_USD -> SPY proxy (ADR-089). Reversible 1-line
    revert to "I:DXY" when the Indices plan is budgeted."""
    assert ASSET_TO_TICKER["DXY"] == "UUP"
    assert not ASSET_TO_TICKER["DXY"].startswith("I:")


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
