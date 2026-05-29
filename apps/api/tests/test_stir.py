"""Tests for the STIR implied-Fed-path service (pure helpers).

The full DB path is integration-verified live (curl /v1/stir). These tests pin
the pure curve math + tone + ADR-017-clean narrative, anchored on the real ZQ
curve observed 2026-05-29 (front 3.645 → Jan-27 3.770).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.stir import _build_note, _point_from_rows, _tone

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
    assert "12 pb" in note
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
