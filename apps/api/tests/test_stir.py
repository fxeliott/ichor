"""Tests for the STIR implied-Fed-path service (pure helpers).

The full DB path is integration-verified live (curl /v1/stir). These tests pin
the pure curve math + tone + ADR-017-clean narrative, anchored on the real ZQ
curve observed 2026-05-29 (front 3.645 → Jan-27 3.770).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.stir import (
    _build_note,
    _compute_meetings,
    _move_probabilities,
    _point_from_rows,
    _tone,
)

_NOW = datetime(2026, 5, 29, tzinfo=UTC)
_BACK = datetime(2026, 5, 22, tzinfo=UTC)


def test_point_from_rows_computes_cum_and_repricing() -> None:
    # F27 implied 3.77 now vs 3.75 five sessions back; front = 3.645.
    rows = [(_NOW, 3.77), (datetime(2026, 5, 27, tzinfo=UTC), 3.76), (_BACK, 3.75)]
    p = _point_from_rows("ZQ_F27_IMPLIED_EFFR", "Jan 2027", 3.645, rows)
    assert p.implied_effr == 3.77
    assert round(p.cum_bps_vs_front, 1) == 12.5  # (3.77-3.645)*100
    assert round(p.repricing_bps, 1) == 2.0  # (3.77-3.75)*100
    assert p.sessions_in_window == 2


def test_point_from_rows_empty_is_safe() -> None:
    p = _point_from_rows("ZQ_F27_IMPLIED_EFFR", "Jan 2027", 3.645, [])
    assert p.implied_effr is None
    assert p.cum_bps_vs_front is None
    assert p.repricing_bps is None
    assert p.sessions_in_window == 0


def test_point_from_rows_no_front_yields_none_cum() -> None:
    p = _point_from_rows("ZQ_K26_IMPLIED_EFFR", "May 2026", None, [(_NOW, 3.6275)])
    assert p.implied_effr == 3.6275
    assert p.cum_bps_vs_front is None
    assert p.repricing_bps is None  # single row, no window


def test_tone_thresholds() -> None:
    assert _tone(12.5) == "tightening_priced"
    assert _tone(-15.0) == "easing_priced"
    assert _tone(5.0) == "flat"
    assert _tone(None) == "flat"


def test_build_note_is_adr017_clean_and_informative() -> None:
    note = _build_note(
        policy_rate=3.62,
        front_implied=3.645,
        horizon_label="Jan 2027",
        net_bps=12.5,
        cuts=-0.5,
        tone="tightening_priced",
        reprice_horizon=2.0,
    )
    assert "resserrement" in note
    # 12.5 rounds half-up to 13 (matches frontend fmtBps toFixed) — note and
    # the header badge can never disagree at a .5 boundary (code-review Y-1).
    assert "13 pb" in note
    assert "Jan 2027" in note
    assert "pas une prévision" in note
    assert is_adr017_clean(note)


def test_build_note_easing_path_adr017_clean() -> None:
    note = _build_note(
        policy_rate=3.62,
        front_implied=3.645,
        horizon_label="Jan 2027",
        net_bps=-45.0,
        cuts=1.8,
        tone="easing_priced",
        reprice_horizon=-8.0,
    )
    assert "assouplissement" in note
    assert "1.8 baisses" in note
    assert is_adr017_clean(note)


def test_build_note_handles_missing_data() -> None:
    note = _build_note(None, None, None, None, None, "flat", None)
    assert "indisponible" in note
    assert is_adr017_clean(note)


# ── Per-meeting FedWatch (CME methodology) ───────────────────────────────


def test_move_probabilities_single_step() -> None:
    assert _move_probabilities(-25.0) == (1.0, 0.0, 0.0)  # full cut
    assert _move_probabilities(-12.5) == (0.5, 0.5, 0.0)  # 50% cut
    assert _move_probabilities(25.0) == (0.0, 0.0, 1.0)  # full hike
    assert _move_probabilities(0.0) == (0.0, 1.0, 0.0)  # hold
    assert _move_probabilities(None) == (None, None, None)


def test_move_probabilities_caps_beyond_one_move() -> None:
    p_cut, p_hold, p_hike = _move_probabilities(-50.0)  # 2 cuts priced
    assert p_cut == 1.0 and p_hold == 0.0 and p_hike == 0.0


def _easing_chain() -> dict[str, float]:
    """3 cuts (Jun/Sep/Dec) + 2 holds (Jul/Oct), built from the EXACT day-
    weighted monthly averages so the day-weight solve must recover ±25 bp."""
    return {
        "ZQ_K26_IMPLIED_EFFR": 3.60,  # May clean anchor (pre-Jun)
        "ZQ_M26_IMPLIED_EFFR": (17 * 3.60 + 13 * 3.35) / 30,  # Jun avg → post 3.35
        "ZQ_Q26_IMPLIED_EFFR": 3.35,  # Aug clean = post-Jul (Jul holds)
        "ZQ_U26_IMPLIED_EFFR": (16 * 3.35 + 14 * 3.10) / 30,  # Sep avg → post 3.10
        "ZQ_X26_IMPLIED_EFFR": 3.10,  # Nov clean = post-Oct (Oct holds)
        "ZQ_Z26_IMPLIED_EFFR": (9 * 3.10 + 22 * 2.85) / 31,  # Dec avg → post 2.85
    }


def test_compute_meetings_recovers_chain() -> None:
    meetings = _compute_meetings(_easing_chain())
    by = {m.label: m for m in meetings}
    assert round(by["Jun 2026"].implied_change_bps, 1) == -25.0
    assert by["Jun 2026"].p_cut == 1.0
    assert round(by["Jul 2026"].implied_change_bps, 1) == 0.0
    assert round(by["Jul 2026"].p_hold, 3) == 1.0
    assert round(by["Sep 2026"].implied_change_bps, 1) == -25.0
    assert round(by["Oct 2026"].implied_change_bps, 1) == 0.0
    assert round(by["Dec 2026"].implied_change_bps, 1) == -25.0


def test_compute_meetings_telescopes_to_cumulative() -> None:
    """ΣΔ_meetings must equal post-Dec − pre-Jun (internal consistency)."""
    meetings = _compute_meetings(_easing_chain())
    total = sum(m.implied_change_bps for m in meetings if m.implied_change_bps is not None)
    assert round(total, 1) == -75.0  # 3.60 → 2.85 = −75 bp across the year


def test_compute_meetings_partial_probability() -> None:
    """A meeting pricing a 60% cut (−15 bp) → p_cut 0.6 / p_hold 0.4."""
    chain = {
        "ZQ_K26_IMPLIED_EFFR": 3.60,
        "ZQ_M26_IMPLIED_EFFR": (17 * 3.60 + 13 * 3.45) / 30,  # post 3.45 = −15 bp
    }
    meetings = _compute_meetings(chain)
    jun = next(m for m in meetings if m.label == "Jun 2026")
    assert round(jun.implied_change_bps, 1) == -15.0
    assert round(jun.p_cut, 2) == 0.60
    assert round(jun.p_hold, 2) == 0.40


def test_compute_meetings_missing_data_safe() -> None:
    meetings = _compute_meetings({})  # cold start
    assert len(meetings) == 5
    assert all(m.implied_change_bps is None for m in meetings)
    assert all(m.p_cut is None for m in meetings)
