"""S06 Chantier C — C-3 volume wiring tests.

Covers the NEW glue that turns the pure ``volume_vote.build_volume_vote`` producer
into a card snapshot the verdict fuser folds in (gated by the
``volume_dimension_vote_enabled`` flag), mirroring the COT C-3b wiring:

* ``data_pool._volume_vote_from_reading`` — the pure reading→vote mapper (no DB).
* ``data_pool.build_volume_vote_for_asset`` — the FX/no-venue-volume abstain branch
  (no DB).
* the single-source-of-truth flag constant.
* a fresh volume vote survives the snapshot round-trip (write → read codec).

The flag-OFF byte-identical guarantee of the read/write sites themselves is held by
the existing golden harnesses (``test_fuser_golden_harness`` +
``test_card_golden_harness``) — this file proves the producer glue is correct.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from ichor_api.services.data_pool import (
    _volume_vote_from_reading,
    build_volume_vote_for_asset,
)
from ichor_api.services.dimension_vote import votes_from_snapshot, votes_to_snapshot
from ichor_api.services.microstructure import RelativeVolumeReading
from ichor_api.services.volume_vote import VOLUME_DIMENSION_VOTE_FLAG


def _reading(
    *,
    asset: str = "SPX500_USD",
    latest_date: date | None = date(2026, 6, 11),
    rvol_ratio: float | None = 3.0,
    volume_available: bool = True,
    volume_zscore: float | None = 2.4,
    bucket: str = "volume spike",
) -> RelativeVolumeReading:
    """A RelativeVolumeReading for the pure mapper (the mapper reads
    latest_date / rvol_ratio / volume_zscore / volume_available)."""
    return RelativeVolumeReading(
        asset=asset,
        volume_available=volume_available,
        latest_date=latest_date,
        current_volume=3_000_000.0 if rvol_ratio else None,
        avg_volume=1_000_000.0 if rvol_ratio else None,
        rvol_ratio=rvol_ratio,
        volume_zscore=volume_zscore,
        n_history=120,
        bucket=bucket,
    )


_NOW = date(2026, 6, 12)  # latest_date 2026-06-11 → age 1 day → fresh (max 5)


def test_flag_constant_is_the_documented_key() -> None:
    # The write site and the read site both import THIS constant — guard the exact
    # string so a rename can't silently desync them from the DB flag row.
    assert VOLUME_DIMENSION_VOTE_FLAG == "volume_dimension_vote_enabled"


def test_fresh_spike_reading_maps_to_nondirectional_vote() -> None:
    vote = _volume_vote_from_reading("SPX500_USD", _reading(rvol_ratio=3.0), now_date=_NOW)

    assert vote.provenance == "volume"
    assert vote.honest_absence is False
    # ADR-017: volume is NON-directional — confirms participation, never direction.
    assert vote.directional is False
    assert vote.direction_hint == "neutral"
    assert vote.strength == 1.0  # 3.0× = full strength bar
    assert 0.0 < vote.freshness <= 1.0
    assert vote.signed_contribution() == 0.0
    assert vote.uncertainty_credit() > 0.0


def test_fx_unavailable_reading_abstains() -> None:
    # An FX-style reading (no consolidated venue volume) → honest absence.
    vote = _volume_vote_from_reading(
        "EUR_USD",
        _reading(asset="EUR_USD", volume_available=False, rvol_ratio=None, bucket="n/a"),
        now_date=_NOW,
    )
    assert vote.honest_absence is True
    assert vote.directional is False
    assert vote.strength == 0.0


def test_stale_reading_abstains_fail_closed() -> None:
    # latest_date ~30 days old → liveness STALE → fail-closed abstain even on a spike.
    vote = _volume_vote_from_reading(
        "SPX500_USD",
        _reading(latest_date=date(2026, 5, 12), rvol_ratio=3.0),
        now_date=_NOW,
    )
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"
    assert vote.strength == 0.0


def test_below_baseline_reading_is_present_but_zero_strength() -> None:
    vote = _volume_vote_from_reading("SPX500_USD", _reading(rvol_ratio=1.0), now_date=_NOW)
    assert vote.honest_absence is False  # data present
    assert vote.strength == 0.0  # at/below the elevated cut → no confirmation
    assert vote.is_effective is False
    assert vote.uncertainty_credit() == 0.0


def test_fetch_helper_abstains_for_fx_asset() -> None:
    # FX branch never touches the session → safe to pass None.
    vote = asyncio.run(
        build_volume_vote_for_asset(None, "EUR_USD", now_utc=datetime(2026, 6, 12, tzinfo=UTC))  # type: ignore[arg-type]
    )
    assert vote.provenance == "volume"
    assert vote.honest_absence is True
    assert vote.directional is False
    assert vote.direction_hint == "neutral"


def test_fresh_vote_survives_the_card_snapshot_round_trip() -> None:
    # The write side stores votes_to_snapshot([...]); the read side reconstructs via
    # votes_from_snapshot(card.dimension_votes). A real non-directional volume vote
    # must round-trip to an EQUAL vote (not degrade to honest-absence).
    vote = _volume_vote_from_reading("NAS100_USD", _reading(asset="NAS100_USD"), now_date=_NOW)

    snapshot = votes_to_snapshot([vote])
    assert isinstance(snapshot, list) and len(snapshot) == 1

    (restored,) = votes_from_snapshot(snapshot)
    assert restored.provenance == vote.provenance
    assert restored.direction_hint == vote.direction_hint
    assert restored.strength == vote.strength
    assert restored.freshness == vote.freshness
    assert restored.honest_absence == vote.honest_absence
    assert restored.directional == vote.directional


def test_cot_and_volume_votes_coexist_in_one_snapshot() -> None:
    # Both flags ON ⇒ the write side freezes [cot_vote, volume_vote]; the read side
    # reads both. Prove a combined snapshot round-trips both provenances intact (a
    # directional COT vote + a non-directional volume vote in one snapshot).
    from ichor_api.services.dimension_vote import DimensionVote

    cot = DimensionVote(
        provenance="cot",
        direction_hint="up",
        strength=0.6,
        freshness=0.9,
        honest_absence=False,
        directional=True,
    )
    vol = _volume_vote_from_reading("SPX500_USD", _reading(), now_date=_NOW)

    snapshot = votes_to_snapshot([cot, vol])
    restored = votes_from_snapshot(snapshot)
    by_prov = {v.provenance: v for v in restored}
    assert set(by_prov) == {"cot", "volume"}
    assert by_prov["cot"].directional is True
    assert by_prov["volume"].directional is False
