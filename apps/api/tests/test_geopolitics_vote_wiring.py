"""S06 Chantier C — geopolitics vote wiring tests.

Covers the NEW glue that turns the pure ``geopolitics_vote.build_geopolitics_vote``
producer into a card snapshot the verdict fuser folds in (gated by the
``geopolitics_dimension_vote_enabled`` flag), mirroring the COT C-3b / volume C-3 wiring:

* ``data_pool.build_geopolitics_vote_for_asset`` — the async write-side builder: it reads
  the AI-GPR flash z-score (``evaluate_geopol_flash``, ``persist=False`` — never fires an
  alert), recomputes liveness, and maps to ONE non-directional vote. Tested with the flash
  monkeypatched so no DB is needed (the mapper + liveness are pure / date-based).
* the single-source-of-truth flag constant.
* a fresh geo vote survives the snapshot round-trip (write → read codec).
* cot + volume + geo coexist in one snapshot (all three provenances intact).

The flag-OFF byte-identical guarantee of the read/write sites themselves is held by the
existing golden harnesses (``test_fuser_golden_harness`` + ``test_card_golden_harness``) —
this file proves the producer glue is correct.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from ichor_api.services.data_pool import build_geopolitics_vote_for_asset
from ichor_api.services.dimension_vote import votes_from_snapshot, votes_to_snapshot
from ichor_api.services.geopol_flash_check import GeopolFlashResult
from ichor_api.services.geopolitics_vote import GEOPOLITICS_DIMENSION_VOTE_FLAG

_NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


def _flash(
    *,
    current_date: date | None = date(2026, 6, 12),  # age 0 vs _NOW → fresh
    z_score: float | None = 2.0,  # full-strength spike
) -> GeopolFlashResult:
    return GeopolFlashResult(
        current_value=180.0,
        current_date=current_date,
        baseline_mean=100.0,
        baseline_std=40.0,
        z_score=z_score,
        n_history=30,
        alert_fired=False,
    )


def _patch_flash(monkeypatch: pytest.MonkeyPatch, result: GeopolFlashResult) -> dict[str, bool]:
    """Monkeypatch evaluate_geopol_flash to return ``result`` and record that persist=False
    was passed (the vote read must NEVER fire/persist the alert)."""
    seen: dict[str, bool] = {}

    async def fake_flash(session: object, *, persist: bool = True) -> GeopolFlashResult:
        seen["persist"] = persist
        return result

    monkeypatch.setattr("ichor_api.services.geopol_flash_check.evaluate_geopol_flash", fake_flash)
    return seen


def test_flag_constant_is_the_documented_key() -> None:
    # The write site and the read site both import THIS constant — guard the exact
    # string so a rename can't silently desync them from the DB flag row.
    assert GEOPOLITICS_DIMENSION_VOTE_FLAG == "geopolitics_dimension_vote_enabled"


def test_builder_maps_fresh_spike_to_nondirectional_vote(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_flash(monkeypatch, _flash(z_score=2.0))
    vote = asyncio.run(build_geopolitics_vote_for_asset(None, "XAU_USD", now_utc=_NOW))  # type: ignore[arg-type]

    assert vote.provenance == "geopolitics"
    assert vote.honest_absence is False
    # ADR-017: geopolitics is NON-directional — regime-conditional sign, never a tilt.
    assert vote.directional is False
    assert vote.direction_hint == "neutral"
    assert vote.strength == pytest.approx(1.0)  # z=2.0 = full-strength spike bar
    assert 0.0 < vote.freshness <= 1.0
    assert vote.signed_contribution() == 0.0
    assert vote.uncertainty_credit() > 0.0
    # The vote read must be side-effect-free (no alert persisted).
    assert seen["persist"] is False


def test_builder_is_global_same_vote_for_every_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI-GPR is one global scalar → every asset receives the identical credit."""
    _patch_flash(monkeypatch, _flash(z_score=1.25))  # midpoint → strength 0.5
    votes = [
        asyncio.run(build_geopolitics_vote_for_asset(None, a, now_utc=_NOW))  # type: ignore[arg-type]
        for a in ("XAU_USD", "SPX500_USD", "EUR_USD", "GBP_USD", "NAS100_USD")
    ]
    strengths = {v.strength for v in votes}
    assert len(strengths) == 1  # identical across assets
    assert votes[0].strength == pytest.approx(0.5)


def test_builder_stale_flash_abstains_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # current_date ~40 days old → liveness STALE (max 14) → fail-closed abstain on a spike.
    _patch_flash(monkeypatch, _flash(current_date=date(2026, 5, 3), z_score=2.0))
    vote = asyncio.run(build_geopolitics_vote_for_asset(None, "XAU_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.honest_absence is True
    assert vote.direction_hint == "neutral"
    assert vote.strength == 0.0


def test_builder_not_warm_zscore_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    # z_score=None (< 20 obs / degenerate baseline) → not-yet-warm → abstain even if fresh.
    _patch_flash(monkeypatch, _flash(z_score=None))
    vote = asyncio.run(build_geopolitics_vote_for_asset(None, "XAU_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.honest_absence is True
    assert vote.strength == 0.0


def test_builder_empty_table_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    # No observations → current_date None + z None → abstain.
    _patch_flash(monkeypatch, _flash(current_date=None, z_score=None))
    vote = asyncio.run(build_geopolitics_vote_for_asset(None, "XAU_USD", now_utc=_NOW))  # type: ignore[arg-type]
    assert vote.honest_absence is True


def test_fresh_vote_survives_the_card_snapshot_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    # The write side stores votes_to_snapshot([...]); the read side reconstructs via
    # votes_from_snapshot(card.dimension_votes). A real non-directional geo vote must
    # round-trip to an EQUAL vote (not degrade to honest-absence).
    _patch_flash(monkeypatch, _flash(z_score=1.7))
    vote = asyncio.run(build_geopolitics_vote_for_asset(None, "EUR_USD", now_utc=_NOW))  # type: ignore[arg-type]

    snapshot = votes_to_snapshot([vote])
    assert isinstance(snapshot, list) and len(snapshot) == 1

    (restored,) = votes_from_snapshot(snapshot)
    assert restored.provenance == vote.provenance
    assert restored.direction_hint == vote.direction_hint
    assert restored.strength == vote.strength
    assert restored.freshness == vote.freshness
    assert restored.honest_absence == vote.honest_absence
    assert restored.directional == vote.directional


def test_cot_volume_geo_votes_coexist_in_one_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    # All three flags ON ⇒ the write side freezes [cot, volume, geo]; the read side reads
    # all three. Prove a combined snapshot round-trips every provenance intact (directional
    # COT + non-directional volume + non-directional geo in one snapshot).
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
    _patch_flash(monkeypatch, _flash(z_score=2.0))
    geo = asyncio.run(build_geopolitics_vote_for_asset(None, "SPX500_USD", now_utc=_NOW))  # type: ignore[arg-type]

    snapshot = votes_to_snapshot([cot, vol, geo])
    restored = votes_from_snapshot(snapshot)
    by_prov = {v.provenance: v for v in restored}
    assert set(by_prov) == {"cot", "volume", "geopolitics"}
    assert by_prov["cot"].directional is True
    assert by_prov["volume"].directional is False
    assert by_prov["geopolitics"].directional is False
