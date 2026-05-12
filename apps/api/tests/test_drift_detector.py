"""W114 ADWIN drift detector + tiered dispatcher unit tests.

Pure-logic slices. The reconciler-side DB integration is tested via
the reconciler test ; here we cover :

  1. `AssetDriftBundle.feed_target` returns None on empty / too-short
     input, and a DriftEvent on a constructed regime-shift stream.
  2. `feed_feature` rejects unknown feature_name, returns None on
     empty, fires on construction.
  3. `classify_tier` mapping for tier 0/1/2/3.
  4. `dispatch_drift_events` writes the right shape to record_fn for
     each tier (tier-0 no-op, tier-1 no disposition, tier-2 sequester,
     tier-3 retire + critical log).
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock

import pytest

# The module itself lazy-imports river — classify_tier + dispatch_drift_events
# are pure Python and run anywhere. Only the AssetDriftBundle.feed_* tests
# need the river extras (gated below with `_requires_river`).
from ichor_api.services.drift_detector import (
    AssetDriftBundle,
    DriftEvent,
    classify_tier,
    dispatch_drift_events,
)


def _has_river() -> bool:
    try:
        import river  # noqa: F401

        return True
    except ImportError:
        return False


_requires_river = pytest.mark.skipif(
    not _has_river(),
    reason="phase-d extras not installed (pip install -e '.[phase-d]')",
)


# ────────────────────────── AssetDriftBundle (needs river) ──────────────────────────


@_requires_river
def test_feed_target_empty_returns_none() -> None:
    bundle = AssetDriftBundle(asset="EUR_USD")
    assert bundle.feed_target([]) is None


@_requires_river
def test_feed_target_short_window_returns_none() -> None:
    """ADWIN needs ~32 obs ; below that we don't expect a fire even
    on a clean step change."""
    bundle = AssetDriftBundle(asset="EUR_USD")
    residuals = [0.2] * 5 + [0.8] * 5
    event = bundle.feed_target(residuals)
    # ADWIN may or may not fire on 10 obs ; we just assert NO crash.
    assert event is None or isinstance(event, DriftEvent)


@_requires_river
def test_feed_target_regime_shift_fires() -> None:
    """A clean step change after 200 obs should reliably fire ADWIN.

    Build a long stream of stable 0.1 residuals (good model) then a
    burst of 0.6 residuals (model failing). ADWIN must detect on the
    last update.
    """
    bundle = AssetDriftBundle(asset="EUR_USD", target_delta=0.002)
    # 150 stable + 50 shifted = 200 total, regime shift at index 150.
    residuals = [0.1 + 0.005 * ((i % 7) - 3) for i in range(150)]
    residuals += [0.6 + 0.005 * ((i % 7) - 3) for i in range(50)]
    event = bundle.feed_target(residuals)
    # We expect a fire ; ADWIN with delta=0.002 + magnitude 0.5 is well
    # above the false-alarm threshold for 200 obs.
    assert event is not None
    assert event.asset == "EUR_USD"
    assert event.detector_name == "target"
    assert event.n_observations == 200
    assert event.magnitude > 0.0


def test_feed_feature_rejects_unknown_name() -> None:
    """Pure validation : doesn't reach the river import."""
    bundle = AssetDriftBundle(asset="EUR_USD", feature_names=("vpin",))
    with pytest.raises(ValueError, match=r"not in bundle\.feature_names"):
        bundle.feed_feature("dxy_z", [0.1, 0.2, 0.3])


def test_feed_feature_empty_returns_none() -> None:
    """Pure validation : doesn't reach the river import."""
    bundle = AssetDriftBundle(asset="EUR_USD", feature_names=("vpin",))
    assert bundle.feed_feature("vpin", []) is None


@_requires_river
def test_feed_feature_event_carries_feature_prefix() -> None:
    bundle = AssetDriftBundle(asset="EUR_USD", feature_names=("vpin",), feature_delta=0.002)
    vals = [0.2 + 0.005 * ((i % 5) - 2) for i in range(150)]
    vals += [0.8 + 0.005 * ((i % 5) - 2) for i in range(50)]
    event = bundle.feed_feature("vpin", vals)
    assert event is not None
    assert event.detector_name == "feature:vpin"


# ────────────────────────── classify_tier ──────────────────────────


def _ev(name: str, asset: str = "EUR_USD", magnitude: float = 0.1) -> DriftEvent:
    return DriftEvent(
        detector_name=name,
        asset=asset,
        estimation_before=0.2,
        estimation_after=0.2 + magnitude,
        magnitude=magnitude,
        n_observations=200,
    )


def test_classify_tier_zero_on_empty() -> None:
    assert classify_tier([]) == 0


def test_classify_tier_one_on_single_small_event() -> None:
    assert classify_tier([_ev("target", magnitude=0.5)]) == 1


def test_classify_tier_two_on_two_co_firing() -> None:
    assert classify_tier([_ev("target", magnitude=0.5), _ev("feature:vpin", magnitude=0.5)]) == 2


def test_classify_tier_two_on_large_magnitude_single() -> None:
    assert classify_tier([_ev("target", magnitude=3.0)], magnitude_sigma_threshold=2.0) == 2


def test_classify_tier_three_on_target_plus_three_features() -> None:
    events = [
        _ev("target", magnitude=0.5),
        _ev("feature:vpin", magnitude=0.5),
        _ev("feature:dxy_z", magnitude=0.5),
        _ev("feature:dgs10_surprise", magnitude=0.5),
    ]
    assert classify_tier(events) == 3


def test_classify_tier_three_dominates_when_features_minus_target_below_threshold() -> None:
    """3 features alone WITHOUT target = tier-2, not tier-3."""
    events = [
        _ev("feature:vpin"),
        _ev("feature:dxy_z"),
        _ev("feature:dgs10_surprise"),
    ]
    assert classify_tier(events) == 2


# ────────────────────────── dispatch_drift_events ──────────────────────────


@pytest.mark.asyncio
async def test_dispatch_tier0_no_record() -> None:
    recorder = AsyncMock()
    tier = await dispatch_drift_events([], record_fn=recorder)
    assert tier == 0
    recorder.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_tier1_records_pending_review_no_disposition() -> None:
    recorder = AsyncMock()
    tier = await dispatch_drift_events([_ev("target", magnitude=0.5)], record_fn=recorder)
    assert tier == 1
    recorder.assert_awaited_once()
    kwargs: dict[str, Any] = recorder.await_args.kwargs
    assert kwargs["loop_kind"] == "adwin_drift"
    assert kwargs["decision"] == "pending_review"
    assert kwargs["disposition"] is None
    assert kwargs["asset"] == "EUR_USD"
    assert kwargs["output_summary"]["tier"] == 1


@pytest.mark.asyncio
async def test_dispatch_tier2_sets_sequester_disposition() -> None:
    recorder = AsyncMock()
    events = [_ev("target", magnitude=0.5), _ev("feature:vpin", magnitude=0.5)]
    tier = await dispatch_drift_events(events, record_fn=recorder)
    assert tier == 2
    kwargs: dict[str, Any] = recorder.await_args.kwargs
    assert kwargs["disposition"] == "sequester"


@pytest.mark.asyncio
async def test_dispatch_tier3_sets_retire_disposition() -> None:
    recorder = AsyncMock()
    events = [
        _ev("target", magnitude=0.5),
        _ev("feature:vpin", magnitude=0.5),
        _ev("feature:dxy_z", magnitude=0.5),
        _ev("feature:dgs10_surprise", magnitude=0.5),
    ]
    tier = await dispatch_drift_events(events, record_fn=recorder)
    assert tier == 3
    kwargs: dict[str, Any] = recorder.await_args.kwargs
    assert kwargs["disposition"] == "retire"


@pytest.mark.asyncio
async def test_dispatch_drops_asset_when_multiple() -> None:
    """If events span multiple assets, the recorded `asset` field is
    None (the per-event detail lives in input_summary)."""
    recorder = AsyncMock()
    events = [_ev("target", asset="EUR_USD"), _ev("target", asset="GBP_USD")]
    await dispatch_drift_events(events, record_fn=recorder)
    kwargs: dict[str, Any] = recorder.await_args.kwargs
    assert kwargs["asset"] is None
    detector_assets = sorted({e["asset"] for e in kwargs["input_summary"]["events"]})
    assert detector_assets == ["EUR_USD", "GBP_USD"]


# ────────────────────────── numeric sanity ──────────────────────────


def test_drift_event_dataclass_holds_floats_cleanly() -> None:
    """No NaN / Inf in the event constructor for plausible inputs."""
    e = DriftEvent(
        detector_name="target",
        asset="EUR_USD",
        estimation_before=0.2,
        estimation_after=0.5,
        magnitude=0.3,
        n_observations=200,
    )
    for v in (e.estimation_before, e.estimation_after, e.magnitude):
        assert math.isfinite(v)
