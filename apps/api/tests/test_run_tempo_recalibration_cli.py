"""r126 ADR-099 §Impl(r126) — run_tempo_recalibration CLI smoke tests.

The heavy lifting is unit-tested in `test_tempo_recalibration.py` (the
service module). These tests cover the CLI thin shell :
  - `_parse_assets` handles canonical + degenerate inputs
  - argparse hooks the right defaults
"""

from __future__ import annotations

import argparse

import pytest
from ichor_api.cli.run_tempo_recalibration import _parse_assets
from ichor_api.services.tempo_recalibration import (
    DEFAULT_MIN_SAMPLE_DAYS,
    DEFAULT_RECALIBRATION_ASSETS,
    DEFAULT_WINDOW_DAYS,
)

# ─────────────── _parse_assets ────────────────


def test_parse_assets_single_value() -> None:
    assert _parse_assets("EUR_USD") == ("EUR_USD",)


def test_parse_assets_comma_separated() -> None:
    assert _parse_assets("EUR_USD,GBP_USD,XAU_USD") == (
        "EUR_USD",
        "GBP_USD",
        "XAU_USD",
    )


def test_parse_assets_strips_whitespace() -> None:
    assert _parse_assets(" EUR_USD , GBP_USD ") == ("EUR_USD", "GBP_USD")


def test_parse_assets_empty_string_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_assets("")


def test_parse_assets_whitespace_only_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_assets(",  , ,")


def test_parse_assets_preserves_case() -> None:
    """Canonical convention is underscore-uppercase, but we don't UPPER()
    here — `_parse_assets` is a pure parser. The service-layer caller
    validates against ADR-083 universe."""
    # lowercase passes through unchanged.
    assert _parse_assets("eur_usd") == ("eur_usd",)


# ─────────────── default constants reused by frontend r127 ────────────────


def test_default_constants_are_stable() -> None:
    """The r127 frontend fetcher will read these defaults — pin them so a
    backend-only change can't silently shift them."""
    assert DEFAULT_WINDOW_DAYS == 90
    assert DEFAULT_MIN_SAMPLE_DAYS == 7
    assert len(DEFAULT_RECALIBRATION_ASSETS) == 5
    assert "EUR_USD" in DEFAULT_RECALIBRATION_ASSETS
    assert "XAU_USD" in DEFAULT_RECALIBRATION_ASSETS
    assert "USD_CAD" not in DEFAULT_RECALIBRATION_ASSETS  # 6th D1 asset not yet shipped
