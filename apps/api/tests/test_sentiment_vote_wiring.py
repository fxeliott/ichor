"""S06 Chantier C — sentiment vote wiring tests.

Covers the glue that turns the pure ``sentiment_vote.build_sentiment_vote`` producer into
a card snapshot the verdict fuser folds in (gated by ``sentiment_dimension_vote_enabled``):

* ``data_pool.build_sentiment_vote_for_asset`` — the async write-side builder: maps the
  Ichor asset to its MyFXBook pair, reads the latest snapshot, recomputes liveness, maps to
  one CONTRARIAN vote. Tested with a tiny fake AsyncSession (no real DB) for the covered
  path, and ``session=None`` for the DB-free abstain path.
* the single-source-of-truth flag constant.
* a fresh sentiment vote survives the snapshot round-trip.

Flag-OFF byte-identity is held by the golden harnesses — this proves the glue.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from ichor_api.models import MyfxbookOutlook
from ichor_api.services.data_pool import build_sentiment_vote_for_asset
from ichor_api.services.dimension_vote import votes_from_snapshot, votes_to_snapshot
from ichor_api.services.sentiment_vote import SENTIMENT_DIMENSION_VOTE_FLAG

_NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


class _FakeResult:
    def __init__(self, row: object) -> None:
        self._row = row

    def scalars(self) -> _FakeResult:
        return self

    def first(self) -> object:
        return self._row


class _FakeSession:
    """Minimal AsyncSession stub: returns one row for any select (the builder issues a
    single latest-snapshot query)."""

    def __init__(self, row: object) -> None:
        self._row = row

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._row)


def _row(
    *, pair: str = "EURUSD", long_pct: float = 85.0, short_pct: float = 15.0
) -> MyfxbookOutlook:
    return MyfxbookOutlook(
        pair=pair,
        long_pct=long_pct,
        short_pct=short_pct,
        fetched_at=datetime(2026, 6, 12, 6, 0, tzinfo=UTC),  # age 0 → fresh
    )


def test_flag_constant_is_the_documented_key() -> None:
    assert SENTIMENT_DIMENSION_VOTE_FLAG == "sentiment_dimension_vote_enabled"


def test_builder_maps_crowd_long_to_contrarian_down_vote() -> None:
    session = _FakeSession(_row(long_pct=85.0, short_pct=15.0))
    vote = asyncio.run(build_sentiment_vote_for_asset(session, "EUR_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.provenance == "sentiment"
    assert vote.honest_absence is False
    assert vote.directional is True
    assert vote.direction_hint == "down"  # contrarian fade of the long crowd
    assert vote.strength == 1.0
    assert 0.0 < vote.freshness <= 1.0


def test_builder_abstains_when_collector_dormant() -> None:
    # Dormant collector → no row → honest-absence (the default prod state without creds).
    session = _FakeSession(None)
    vote = asyncio.run(build_sentiment_vote_for_asset(session, "EUR_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"


def test_builder_abstains_db_free_for_index() -> None:
    # SPX500/NAS100 have no MyFXBook pair → abstain WITHOUT touching the session (None safe).
    for asset in ("SPX500_USD", "NAS100_USD", "ZZZ_ZZZ"):
        vote = asyncio.run(
            build_sentiment_vote_for_asset(None, asset, now_utc=_NOW)  # type: ignore[arg-type]
        )
        assert vote.honest_absence is True
        assert vote.provenance == "sentiment"


def test_builder_xau_maps_directly_no_reversal() -> None:
    session = _FakeSession(_row(pair="XAUUSD", long_pct=80.0, short_pct=20.0))
    vote = asyncio.run(build_sentiment_vote_for_asset(session, "XAU_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.direction_hint == "down"  # crowd-long gold → contrarian down, no reversal


def test_fresh_vote_survives_the_card_snapshot_round_trip() -> None:
    session = _FakeSession(_row(long_pct=78.0, short_pct=22.0))
    vote = asyncio.run(build_sentiment_vote_for_asset(session, "GBP_USD", now_utc=_NOW))  # type: ignore[arg-type]

    snapshot = votes_to_snapshot([vote])
    (restored,) = votes_from_snapshot(snapshot)
    assert restored.provenance == vote.provenance
    assert restored.direction_hint == vote.direction_hint
    assert restored.strength == vote.strength
    assert restored.freshness == vote.freshness
    assert restored.directional == vote.directional
