"""S06 Chantier C — positioning_tff vote wiring tests.

Covers the glue that turns the pure ``positioning_tff_vote.build_positioning_tff_vote``
producer into a card snapshot the verdict fuser folds in (gated by
``positioning_tff_dimension_vote_enabled``), mirroring the COT C-3b / volume C-3 wiring:

* ``data_pool._tff_vote_from_rows`` — the pure ORM-rows→vote mapper (no DB).
* ``data_pool.build_positioning_tff_vote_for_asset`` — the DB-free abstain branch for
  every non-SPX500 (COT-covered) asset.
* the single-source-of-truth flag constant.
* a fresh TFF vote survives the snapshot round-trip (write → read codec).

Flag-OFF byte-identity is held by the golden harnesses — this proves the glue.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from ichor_api.models import CftcTffObservation
from ichor_api.services.data_pool import (
    _tff_vote_from_rows,
    build_positioning_tff_vote_for_asset,
)
from ichor_api.services.dimension_vote import votes_from_snapshot, votes_to_snapshot
from ichor_api.services.positioning_tff_vote import POSITIONING_TFF_DIMENSION_VOTE_FLAG

_NOW = date(2026, 6, 12)  # cur report 2026-06-09 → age 3 → fresh (max 14, lag 3 → 1.0)
_SPX_MARKET = "13874A"


def _row(report_date: date, lev_net: int, *, oi: int = 100_000) -> CftcTffObservation:
    """In-memory CftcTffObservation carrying only the fields the mapper reads
    (lev_money_long/short → net, open_interest, report_date)."""
    return CftcTffObservation(
        report_date=report_date,
        market_code=_SPX_MARKET,
        open_interest=oi,
        lev_money_long=lev_net if lev_net > 0 else 0,
        lev_money_short=-lev_net if lev_net < 0 else 0,
    )


def test_flag_constant_is_the_documented_key() -> None:
    assert POSITIONING_TFF_DIMENSION_VOTE_FLAG == "positioning_tff_dimension_vote_enabled"


def test_fresh_spx500_rows_map_to_directional_up_vote() -> None:
    rows = [
        _row(date(2026, 6, 9), 15_000),  # current
        _row(date(2026, 5, 12), 5_000),  # 28d back → Δ4w +10_000 = full strength
    ]
    vote = _tff_vote_from_rows("SPX500_USD", _SPX_MARKET, rows, now_date=_NOW)
    assert vote.provenance == "positioning_tff"
    assert vote.honest_absence is False
    assert vote.directional is True
    assert vote.direction_hint == "up"
    assert vote.strength == 1.0
    assert 0.0 < vote.freshness <= 1.0
    assert vote.signed_contribution() != 0.0


def test_stale_rows_abstain_fail_closed() -> None:
    rows = [
        _row(date(2026, 5, 3), 15_000),  # ~40d old → STALE (max 14)
        _row(date(2026, 4, 5), 5_000),
    ]
    vote = _tff_vote_from_rows("SPX500_USD", _SPX_MARKET, rows, now_date=_NOW)
    assert vote.honest_absence is True
    assert vote.strength == 0.0


def test_empty_rows_abstain() -> None:
    vote = _tff_vote_from_rows("SPX500_USD", _SPX_MARKET, [], now_date=_NOW)
    assert vote.honest_absence is True


def test_builder_abstains_db_free_for_cot_covered_asset() -> None:
    # EUR_USD is COT-covered → builder must abstain WITHOUT touching the session (None safe).
    vote = asyncio.run(
        build_positioning_tff_vote_for_asset(
            None,  # type: ignore[arg-type]
            "EUR_USD",
            now_utc=datetime(2026, 6, 12, tzinfo=UTC),
        )
    )
    assert vote.provenance == "positioning_tff"
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"


def test_builder_abstains_db_free_for_unknown_asset() -> None:
    vote = asyncio.run(
        build_positioning_tff_vote_for_asset(
            None,  # type: ignore[arg-type]
            "ZZZ_ZZZ",
            now_utc=datetime(2026, 6, 12, tzinfo=UTC),
        )
    )
    assert vote.honest_absence is True


def test_fresh_vote_survives_the_card_snapshot_round_trip() -> None:
    rows = [_row(date(2026, 6, 9), 12_000), _row(date(2026, 5, 12), 5_000)]
    vote = _tff_vote_from_rows("SPX500_USD", _SPX_MARKET, rows, now_date=_NOW)

    snapshot = votes_to_snapshot([vote])
    assert isinstance(snapshot, list) and len(snapshot) == 1

    (restored,) = votes_from_snapshot(snapshot)
    assert restored.provenance == vote.provenance
    assert restored.direction_hint == vote.direction_hint
    assert restored.strength == vote.strength
    assert restored.freshness == vote.freshness
    assert restored.directional == vote.directional


def test_all_four_votes_coexist_in_one_snapshot() -> None:
    # COT + volume + geopolitics + positioning_tff in one snapshot, all provenances intact.
    from ichor_api.services.dimension_vote import DimensionVote

    cot = DimensionVote(
        provenance="cot",
        direction_hint="up",
        strength=0.6,
        freshness=0.9,
        honest_absence=False,
        directional=True,
    )
    vol = DimensionVote(
        provenance="volume",
        direction_hint="neutral",
        strength=0.5,
        freshness=0.8,
        honest_absence=False,
        directional=False,
    )
    geo = DimensionVote(
        provenance="geopolitics",
        direction_hint="neutral",
        strength=0.4,
        freshness=0.7,
        honest_absence=False,
        directional=False,
    )
    tff = _tff_vote_from_rows(
        "SPX500_USD",
        _SPX_MARKET,
        [_row(date(2026, 6, 9), 15_000), _row(date(2026, 5, 12), 5_000)],
        now_date=_NOW,
    )
    restored = votes_from_snapshot(votes_to_snapshot([cot, vol, geo, tff]))
    by_prov = {v.provenance: v for v in restored}
    assert set(by_prov) == {"cot", "volume", "geopolitics", "positioning_tff"}
    assert by_prov["positioning_tff"].directional is True
