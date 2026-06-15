"""S06 verdict-engine hardening tests (2026-06-15 adversarial-audit follow-up).

Closes three coverage gaps the fresh-context audit named explicitly:

  * **DST window** — ``_window_stamps_paris`` had zero test coverage ; the NY
    execution window (13h→20h Paris, cut + expiry) must resolve identically in
    CET (winter) and CEST (summer). A naive fixed-offset would drift one hour.
  * **Daily reset** — ``build_session_verdict`` must return ``None`` (→ HTTP
    404) when no card exists since today's Paris-midnight, so yesterday's
    directional read can NEVER pollute today (« repartir de zéro chaque jour »).
  * **C-5 calibrator fail-open** — the OOS conviction calibrator block is the
    lone optional enrichment in the builder ; a transient DB error in the
    pooled history read (when ``conviction_calibrator_oos_enabled`` is ON)
    must NOT 500 the verdict endpoint — it falls back to the raw bucket-derived
    conviction (prompt ⑥ « robuste, fiable et permanent »).

All pure / single-mock — no real DB, no LLM, runner-independent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from ichor_api.services import session_verdict_builder as svb
from ichor_api.services.session_verdict_builder import (
    _window_stamps_paris,
    build_session_verdict,
)

_PARIS = ZoneInfo("Europe/Paris")


# ── F · DST-correct NY window (pure) ────────────────────────────────────────


@pytest.mark.parametrize(
    ("now_utc", "season"),
    [
        (datetime(2026, 1, 15, 10, 0, tzinfo=UTC), "CET"),  # winter, UTC+1
        (datetime(2026, 7, 15, 10, 0, tzinfo=UTC), "CEST"),  # summer, UTC+2
    ],
)
def test_window_stamps_are_14h_20h_paris_in_both_dst_regimes(
    now_utc: datetime, season: str
) -> None:
    window_open, window_close, expires_utc = _window_stamps_paris(now_utc)
    # The execution window opens 13h / closes 20h Paris-wall-clock in BOTH
    # CET and CEST — proof the ZoneInfo idiom resolves the offset per date,
    # not a fixed +1/+2 (which would slip an hour across the DST boundary).
    assert window_open.astimezone(_PARIS).hour == 13, season
    assert window_close.astimezone(_PARIS).hour == 20, season
    # Expiry is exactly the 20h close + a 15-min buffer, in both seasons.
    assert (expires_utc - window_close).total_seconds() == 15 * 60, season


# ── G · daily reset — no card today ⇒ None (no yesterday carry-over) ─────────


@pytest.mark.asyncio
async def test_build_verdict_returns_none_when_no_card_since_today_midnight() -> None:
    # The card fetch (the first and — on this path — only DB call) yields no
    # row for today's Paris session → the builder returns None (caller → 404)
    # rather than serving a stale card from a prior day.
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=empty)

    verdict = await build_session_verdict(
        session, asset="EUR_USD", now_utc=datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    )
    assert verdict is None


# ── B · C-5 calibrator fail-open ────────────────────────────────────────────


def _populated_card() -> SimpleNamespace:
    """Card with a clean bullish 7-bucket decomposition (mild_bull 0.60,
    mild_bear 0.30 → direction 'up', raw conviction 60) and NULL S04/vote
    snapshots so the fuser stays on the bucket-only path."""
    scenarios = [
        {"label": "melt_up", "p": 0.0},
        {"label": "strong_bull", "p": 0.0},
        {"label": "mild_bull", "p": 0.60},
        {"label": "base", "p": 0.10},
        {"label": "mild_bear", "p": 0.30},
        {"label": "strong_bear", "p": 0.0},
        {"label": "crash_flush", "p": 0.0},
    ]
    return SimpleNamespace(
        id="card-abc",
        asset="EUR_USD",
        scenarios=scenarios,
        confluence_snapshot=None,
        theme_snapshot=None,
        dollar_snapshot=None,
        dimension_votes=None,
        generated_at=datetime(2026, 6, 15, 11, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_calibrator_db_error_fails_open_to_raw_conviction(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    card_result = MagicMock()
    card_result.scalar_one_or_none.return_value = _populated_card()
    session = MagicMock()
    session.execute = AsyncMock(return_value=card_result)

    # Calibrator flag ON, dimension-vote flags OFF (so votes stays () and no
    # extra DB read fires) — isolate the calibrator path.
    async def _is_enabled(_session, flag):  # type: ignore[no-untyped-def]
        return flag == "conviction_calibrator_oos_enabled"

    # The pooled history read RAISES — simulating a transient DB fault on the
    # owner-gated calibration path. The fail-open guard must swallow it.
    async def _raise(_session):  # type: ignore[no-untyped-def]
        raise RuntimeError("transient DB blip on reconciled-history read")

    async def _no_triggers(*_a, **_k):  # type: ignore[no-untyped-def]
        return []

    async def _tradeable(*_a, **_k):  # type: ignore[no-untyped-def]
        return "tradeable"

    async def _no_invalidation(*_a, **_k):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("ichor_api.services.feature_flags.is_enabled", _is_enabled)
    monkeypatch.setattr(svb, "_load_reconciled_p_up_y", _raise)
    monkeypatch.setattr(svb, "_assemble_live_triggers", _no_triggers)
    monkeypatch.setattr(svb, "_safe_evaluate_tradeability", _tradeable)
    monkeypatch.setattr(
        "ichor_api.services.scenario_invalidation_monitor.evaluate_scenario_invalidations",
        _no_invalidation,
    )

    verdict = await build_session_verdict(
        session, asset="EUR_USD", now_utc=datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    )

    # The verdict is emitted (no 500) with the RAW bucket-derived conviction —
    # the calibrator fault did not corrupt or block the read.
    assert verdict is not None
    assert verdict.direction == "up"
    assert verdict.conviction_pct == 60.0
