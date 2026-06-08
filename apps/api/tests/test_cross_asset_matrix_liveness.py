"""Unit tests for the S04 liveness gate inside `_section_cross_asset_matrix`.

The depth audit named the highest structural « zone d'ombre » : non-FRED
régime inputs (NY Fed MCT, Cleveland nowcast) were read with NO age check,
so a dead collector's frozen value kept voting in the Pass-1 régime band
indefinitely with zero trace (the TGA-bug class). These tests pin the gate:

  - a STALE MCT is withheld from the régime band (value → n/a, MCT-driven
    bias hints stop firing) WITHOUT re-emitting a duplicate DegradedInput
    (NYFED:MCT staleness is already surfaced by `_section_nyfed_mct`);
  - a STALE Cleveland nowcast is withheld from the surprise band AND emits
    a `CLEVELAND:NOWCAST` DegradedInput (it is surfaced nowhere else);
  - fresh inputs emit no degraded entries (no false positives).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.data_pool import (
    _MCT_MAX_AGE_DAYS,
    _NOWCAST_MAX_AGE_DAYS,
    _section_cross_asset_matrix,
)


def _row(**attrs: object) -> MagicMock:
    row = MagicMock()
    for k, v in attrs.items():
        setattr(row, k, v)
    return row


def _session(
    *,
    mct_val: float,
    mct_obs_month: date,
    nowcast_val: float,
    nowcast_rev: date,
    skew_val: float = 140.0,
    sbet_val: float = 105.0,
) -> MagicMock:
    """Session whose .execute() returns, in `_section_cross_asset_matrix`
    query order: MCT → Cleveland nowcast → SKEW → SBET."""
    results = [
        _row(mct_trend_pct=mct_val, observation_month=mct_obs_month),
        _row(nowcast_value=nowcast_val, revision_date=nowcast_rev),
        _row(skew_value=skew_val, observation_date=date(2026, 5, 13)),
        _row(sboi=sbet_val, report_month=date(2026, 4, 1)),
    ]

    def execute_side_effect(_stmt: object) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=results.pop(0))
        return r

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


@pytest.fixture
def _fresh_fred(monkeypatch: pytest.MonkeyPatch) -> None:
    """NFCI loose + VIX complacent (goldilocks) so the matrix has sources
    and would normally fire the MCT-driven 'Fed easing path' EUR hint."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)


@pytest.mark.asyncio
async def test_stale_mct_withheld_no_duplicate_degraded(_fresh_fred: None) -> None:
    """A MCT row older than _MCT_MAX_AGE_DAYS is withheld from the régime
    band (value → n/a, the inflation-anchored EUR hint stops firing) and is
    NOT re-emitted as a DegradedInput here (avoid double-count vs nyfed_mct)."""
    today = datetime.now(UTC).date()
    session = _session(
        mct_val=2.10,  # would be 'anchored' → 'Fed easing path' EUR hint IF fresh
        mct_obs_month=today - timedelta(days=_MCT_MAX_AGE_DAYS + 60),  # STALE
        nowcast_val=2.05,
        nowcast_rev=today - timedelta(days=2),  # fresh
        skew_val=120.0,  # tail_calm
        sbet_val=105.0,  # sentiment_strong
    )
    md, _src, degraded = await _section_cross_asset_matrix(session)

    # MCT withheld → table shows n/a, not the 2.10 value.
    assert "Inflation persistence (MCT) | n/a | n/a |" in md
    assert "2.10%" not in md
    # The MCT-driven EUR hint (needs inflation_anchored) must NOT fire.
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]
    assert "Fed easing path" not in eur_block
    # No duplicate NYFED:MCT degraded entry (surfaced by _section_nyfed_mct).
    assert all(d.series_id != "NYFED:MCT" for d in degraded)


@pytest.mark.asyncio
async def test_stale_nowcast_emits_degraded_and_withholds_surprise(_fresh_fred: None) -> None:
    """A Cleveland nowcast older than _NOWCAST_MAX_AGE_DAYS is withheld from
    the surprise band AND emits a CLEVELAND:NOWCAST DegradedInput."""
    today = datetime.now(UTC).date()
    session = _session(
        mct_val=2.10,
        mct_obs_month=today - timedelta(days=30),  # fresh
        nowcast_val=2.05,
        nowcast_rev=today - timedelta(days=_NOWCAST_MAX_AGE_DAYS + 20),  # STALE
    )
    md, _src, degraded = await _section_cross_asset_matrix(session)

    # Surprise band withheld.
    assert "Inflation surprise (CorePCE - MCT) | n/a | n/a |" in md
    # MCT itself fresh → its value still rendered.
    assert "Inflation persistence (MCT) | 2.10% |" in md
    # Exactly one degraded entry, for the nowcast, marked stale.
    nowcast_degraded = [d for d in degraded if d.series_id == "CLEVELAND:NOWCAST"]
    assert len(nowcast_degraded) == 1
    assert nowcast_degraded[0].status == "stale"
    assert (
        nowcast_degraded[0].age_days is not None
        and nowcast_degraded[0].age_days > _NOWCAST_MAX_AGE_DAYS
    )


@pytest.mark.asyncio
async def test_fresh_inputs_emit_no_degraded(_fresh_fred: None) -> None:
    """Both régime inputs fresh → no degraded entries (no false positives)."""
    today = datetime.now(UTC).date()
    session = _session(
        mct_val=2.10,
        mct_obs_month=today - timedelta(days=30),
        nowcast_val=2.05,
        nowcast_rev=today - timedelta(days=2),
    )
    md, _src, degraded = await _section_cross_asset_matrix(session)
    assert degraded == []
    assert "Inflation persistence (MCT) | 2.10% |" in md
