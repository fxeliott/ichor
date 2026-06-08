"""Tests for the S04 TIER-2 relative-volume / participation layer.

Covers the pure RVOL + z-score + bucket logic (no DB), the render block
(ADR-017-safe), and the data_pool section wiring (asset-gate + liveness gate)
without opening Postgres — mirroring the project's pure-section test discipline
(AsyncMock session, monkeypatch the I/O entrypoint at its use-site).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import (
    _ASSET_TO_POLYGON,
    _VOLUME_ASSETS,
    _section_volume_rvol,
)
from ichor_api.services.microstructure import (
    RelativeVolumeReading,
    _volume_bucket,
    _volume_zscore,
    classify_relative_volume,
    render_relative_volume_block,
)

# ───────────────────────────── pure: _volume_zscore ─────────────────────────


def test_zscore_none_below_min_history() -> None:
    # 59 < _MIN_VOLUME_ZSCORE_HISTORY (60) → not credible yet.
    assert _volume_zscore([1000.0] * 59, 2000.0) is None


def test_zscore_none_zero_std() -> None:
    # Flat history → std 0 → guarded to None (no divide-by-zero).
    assert _volume_zscore([1000.0] * 60, 5000.0) is None


def test_zscore_value() -> None:
    history = [100.0, 200.0] * 30  # mean 150, std 50, n=60
    assert _volume_zscore(history, 300.0) == pytest.approx(3.0)


# ───────────────────────────── pure: _volume_bucket ─────────────────────────


@pytest.mark.parametrize(
    ("ratio", "z", "expected"),
    [
        (None, None, "insufficient-history"),
        (3.0, None, "volume spike"),
        (1.3, 2.5, "volume spike"),  # z-driven spike even with moderate ratio
        (1.5, 0.5, "elevated participation"),
        (1.0, 0.0, "average participation"),
        (0.7, -0.3, "below-average participation"),
        (0.3, -1.0, "very light participation"),
    ],
)
def test_volume_bucket(ratio: float | None, z: float | None, expected: str) -> None:
    assert _volume_bucket(ratio, z) == expected


# ────────────────────────── pure: classify_relative_volume ──────────────────


def test_classify_no_venue_volume() -> None:
    r = classify_relative_volume([], asset="EUR_USD", latest_date=None, volume_available=False)
    assert r.volume_available is False
    assert r.bucket == "n/a — no venue volume"
    assert r.current_volume is None and r.rvol_ratio is None


def test_classify_empty_is_absent() -> None:
    r = classify_relative_volume([], asset="SPX500_USD", latest_date=None, volume_available=True)
    assert r.volume_available is True
    assert r.bucket == "absent"
    assert r.current_volume is None


def test_classify_insufficient_history() -> None:
    vols = [1000.0] * 5 + [1000.0]  # history of 5 < _MIN_RVOL_HISTORY
    r = classify_relative_volume(
        vols, asset="XAU_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    assert r.rvol_ratio is None
    assert r.avg_volume is None
    assert r.bucket == "insufficient-history"
    assert r.n_history == 5


def test_classify_average() -> None:
    vols = [1000.0] * 60 + [1000.0]
    r = classify_relative_volume(
        vols, asset="SPX500_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    assert r.rvol_ratio == pytest.approx(1.0)
    assert r.bucket == "average participation"
    assert r.volume_zscore is None  # flat history → zero std → None


def test_classify_elevated() -> None:
    vols = [1000.0] * 60 + [1500.0]
    r = classify_relative_volume(
        vols, asset="NAS100_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    assert r.rvol_ratio == pytest.approx(1.5)
    assert r.bucket == "elevated participation"


def test_classify_spike_by_ratio() -> None:
    vols = [1000.0] * 60 + [3000.0]
    r = classify_relative_volume(
        vols, asset="SPX500_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    assert r.rvol_ratio == pytest.approx(3.0)
    assert r.bucket == "volume spike"


def test_classify_ratio_without_zscore_when_history_short() -> None:
    # 59 history obs: ratio computable (≥ _MIN_RVOL_HISTORY) but z-score not yet.
    vols = [1000.0] * 59 + [2000.0]
    r = classify_relative_volume(
        vols, asset="XAU_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    assert r.rvol_ratio == pytest.approx(2.0)
    assert r.volume_zscore is None
    assert r.bucket == "volume spike"


# ────────────────────────── pure: render_relative_volume_block ──────────────


def test_render_no_venue_volume_is_honest_and_adr017_clean() -> None:
    r = classify_relative_volume([], asset="GBP_USD", latest_date=None, volume_available=False)
    md, src = render_relative_volume_block(r)
    assert "N/A" in md
    assert "no consolidated venue" in md
    assert src == []
    assert is_adr017_clean(md)


def test_render_absent_band() -> None:
    r = classify_relative_volume([], asset="SPX500_USD", latest_date=None, volume_available=True)
    md, src = render_relative_volume_block(r)
    assert "ABSENT" in md
    assert src == []
    assert is_adr017_clean(md)


def test_render_fresh_is_adr017_clean_and_complete() -> None:
    vols = [1000.0] * 60 + [2500.0]
    r = classify_relative_volume(
        vols, asset="SPX500_USD", latest_date=date(2026, 6, 8), volume_available=True
    )
    md, src = render_relative_volume_block(r)
    assert "RVOL" in md
    assert "Participation:" in md
    assert "Latest daily bar 2026-06-08" in md
    assert src == ["market_data:SPX500_USD:volume@2026-06-08"]
    assert is_adr017_clean(md)


# ────────────────────────── section: _section_volume_rvol ───────────────────


def test_volume_assets_subset_of_known_assets() -> None:
    # Guard (mirror consumer⊆collector): every volume asset is a real Ichor asset.
    missing = _VOLUME_ASSETS - set(_ASSET_TO_POLYGON)
    assert not missing, f"_VOLUME_ASSETS not in _ASSET_TO_POLYGON: {sorted(missing)}"


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"])
async def test_section_fx_is_honest_na_zero_db(asset: str) -> None:
    session = AsyncMock()
    md, src, degraded = await _section_volume_rvol(session, asset)
    assert "N/A" in md
    assert src == []
    assert degraded == []  # data property, NOT a degraded source
    assert session.execute.await_count == 0  # zero DB I/O for FX
    assert is_adr017_clean(md)


async def test_section_volume_asset_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    today = datetime.now(UTC).date()
    reading = RelativeVolumeReading(
        asset="SPX500_USD",
        volume_available=True,
        latest_date=today,
        current_volume=5.0e9,
        avg_volume=4.0e9,
        rvol_ratio=1.25,
        volume_zscore=1.2,
        n_history=200,
        bucket="elevated participation",
    )

    async def _stub(session: object, asset: str) -> RelativeVolumeReading:
        return reading

    monkeypatch.setattr("ichor_api.services.data_pool.assess_relative_volume", _stub)
    md, src, degraded = await _section_volume_rvol(AsyncMock(), "SPX500_USD")
    assert degraded == []  # fresh → not degraded
    assert "elevated participation" in md
    assert "STALE" not in md
    assert src == [f"market_data:SPX500_USD:volume@{today.isoformat()}"]
    assert is_adr017_clean(md)


async def test_section_volume_asset_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    reading = RelativeVolumeReading(
        asset="NAS100_USD",
        volume_available=True,
        latest_date=date(2020, 1, 1),  # far beyond max-age
        current_volume=5.0e9,
        avg_volume=4.0e9,
        rvol_ratio=1.1,
        volume_zscore=0.5,
        n_history=200,
        bucket="average participation",
    )

    async def _stub(session: object, asset: str) -> RelativeVolumeReading:
        return reading

    monkeypatch.setattr("ichor_api.services.data_pool.assess_relative_volume", _stub)
    md, _src, degraded = await _section_volume_rvol(AsyncMock(), "NAS100_USD")
    assert len(degraded) == 1
    assert degraded[0].status == "stale"
    assert degraded[0].series_id == "market_data:NAS100_USD:volume"
    assert "STALE" in md


async def test_section_volume_asset_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    reading = RelativeVolumeReading(
        asset="XAU_USD",
        volume_available=True,
        latest_date=None,
        current_volume=None,
        avg_volume=None,
        rvol_ratio=None,
        volume_zscore=None,
        n_history=0,
        bucket="absent",
    )

    async def _stub(session: object, asset: str) -> RelativeVolumeReading:
        return reading

    monkeypatch.setattr("ichor_api.services.data_pool.assess_relative_volume", _stub)
    md, _src, degraded = await _section_volume_rvol(AsyncMock(), "XAU_USD")
    assert len(degraded) == 1
    assert degraded[0].status == "absent"
    assert "ABSENT" in md
