"""S06 Chantier C — C-3b wiring tests.

Covers the NEW glue that turns the pure ``cot_vote.build_cot_vote`` producer into
a card snapshot the verdict fuser folds in (gated by the
``cot_dimension_vote_enabled`` flag) :

* ``data_pool._cot_vote_from_rows`` — the pure row→vote mapper (no DB).
* ``data_pool.build_cot_vote_for_asset`` — the whitelist abstain branch (no DB).
* the single-source-of-truth flag constant.
* a fresh COT vote survives the snapshot round-trip (write → read codec).

The flag-OFF byte-identical guarantee of the read/write sites themselves is held
by the existing golden harnesses (``test_fuser_golden_harness`` +
``test_card_golden_harness``) — this file proves the producer glue is correct.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from ichor_api.services.cot_vote import COT_DIMENSION_VOTE_FLAG
from ichor_api.services.data_pool import _cot_vote_from_rows, build_cot_vote_for_asset
from ichor_api.services.dimension_vote import votes_from_snapshot, votes_to_snapshot


def _row(report_date: date, net: int, oi: int = 600_000) -> SimpleNamespace:
    """A CotPosition-shaped duck for the pure mapper (report_date /
    managed_money_net / open_interest are the only fields it reads)."""
    return SimpleNamespace(report_date=report_date, managed_money_net=net, open_interest=oi)


def _weekly_building_rows(newest: date) -> list[SimpleNamespace]:
    """13 weekly reports, managed-money net BUILDING toward the present (a clear
    4-week long accumulation): current 60k, ~4-weeks-back 30k → Δ4w +30k on a
    600k OI = 0.05 fraction, well above the 0.01 noise floor."""
    nets = [
        60_000,
        55_000,
        45_000,
        38_000,
        30_000,
        28_000,
        26_000,
        24_000,
        22_000,
        20_000,
        18_000,
        16_000,
        14_000,
    ]
    return [_row(newest - timedelta(weeks=i), nets[i]) for i in range(len(nets))]


def test_flag_constant_is_the_documented_key() -> None:
    # The write site and the read site both import THIS constant — guard the
    # exact string so a rename can't silently desync them from the DB flag row.
    assert COT_DIMENSION_VOTE_FLAG == "cot_dimension_vote_enabled"


def test_fresh_building_rows_map_to_directional_up_vote_for_eur() -> None:
    newest = date(2026, 6, 9)  # Tuesday data date
    now_date = date(2026, 6, 12)  # released Fri → 3-day-old report → fresh
    rows = _weekly_building_rows(newest)

    vote = _cot_vote_from_rows("EUR_USD", "099741", rows, now_date=now_date)

    assert vote.provenance == "cot"
    assert vote.honest_absence is False
    assert vote.directional is True
    # EUR_USD polarity +1, funds building longs → EUR_USD "up".
    assert vote.direction_hint == "up"
    assert 0.0 < vote.strength <= 1.0
    assert 0.0 < vote.freshness <= 1.0


def test_empty_rows_abstain() -> None:
    vote = _cot_vote_from_rows("EUR_USD", "099741", [], now_date=date(2026, 6, 12))
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"
    assert vote.strength == 0.0


def test_stale_rows_abstain_fail_closed() -> None:
    # Newest report ~10 weeks old → liveness STALE → fail-closed abstain even
    # though the flow itself is a clean build.
    newest = date(2026, 4, 1)
    rows = _weekly_building_rows(newest)
    vote = _cot_vote_from_rows("EUR_USD", "099741", rows, now_date=date(2026, 6, 12))
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"


def test_fetch_helper_abstains_for_asset_outside_cot_whitelist() -> None:
    # market=None branch never touches the session → safe to pass None.
    vote = asyncio.run(
        build_cot_vote_for_asset(None, "BTC_USD", now_utc=datetime(2026, 6, 12, tzinfo=UTC))  # type: ignore[arg-type]
    )
    assert vote.provenance == "cot"
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"


def test_fresh_vote_survives_the_card_snapshot_round_trip() -> None:
    # The write side stores votes_to_snapshot([vote]); the read side reconstructs
    # via votes_from_snapshot(card.dimension_votes). A real directional COT vote
    # must round-trip to an equal vote (not degrade to honest-absence).
    rows = _weekly_building_rows(date(2026, 6, 9))
    vote = _cot_vote_from_rows("EUR_USD", "099741", rows, now_date=date(2026, 6, 12))

    snapshot = votes_to_snapshot([vote])
    assert isinstance(snapshot, list) and len(snapshot) == 1

    (restored,) = votes_from_snapshot(snapshot)
    assert restored.provenance == vote.provenance
    assert restored.direction_hint == vote.direction_hint
    assert restored.strength == vote.strength
    assert restored.freshness == vote.freshness
    assert restored.honest_absence == vote.honest_absence
    assert restored.directional == vote.directional


def test_legacy_null_dimension_votes_reads_as_empty() -> None:
    # A pre-0056 card (or flag-OFF card) has dimension_votes = NULL → the read
    # side must see () → byte-identical to the legacy fuser path (votes=()).
    assert votes_from_snapshot(None) == ()
