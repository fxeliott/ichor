"""Pure-parsing tests for AI-GPR Index collector."""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.ai_gpr import (
    AiGprObservation,
    _parse_csv,
    delta_30d,
    latest_n_days,
)


def test_parse_csv_iso_dates() -> None:
    body = b"""date,GPR_DAILY
2026-04-30,5.2
2026-05-01,5.5
2026-05-02,6.1
"""
    rows = _parse_csv(body)
    assert len(rows) == 3
    assert rows[0].observation_date == date(2026, 4, 30)
    assert rows[0].ai_gpr == 5.2
    assert rows[2].ai_gpr == 6.1


def test_parse_csv_us_dates() -> None:
    body = b"""date,GPR_DAILY
04/30/2026,5.2
05/01/2026,5.5
"""
    rows = _parse_csv(body)
    assert len(rows) == 2
    assert rows[0].observation_date == date(2026, 4, 30)


def test_parse_csv_skips_na_values() -> None:
    body = b"""date,GPR_DAILY
2026-04-30,5.2
2026-05-01,NA
2026-05-02,6.1
"""
    rows = _parse_csv(body)
    assert len(rows) == 2
    assert rows[0].ai_gpr == 5.2
    assert rows[1].ai_gpr == 6.1


def test_parse_csv_handles_ai_gpr_column_name() -> None:
    body = b"""date,AI_GPR
2026-04-30,5.2
"""
    rows = _parse_csv(body)
    assert len(rows) == 1


def test_parse_csv_returns_empty_on_unknown_header() -> None:
    body = b"""foo,bar
1,2
"""
    assert _parse_csv(body) == []


def test_latest_n_days() -> None:
    rows = [
        AiGprObservation(date(2026, m, 1), float(m), None)  # type: ignore[arg-type]
        for m in range(1, 6)
    ]
    last3 = latest_n_days(rows, n=3)
    assert len(last3) == 3
    assert last3[0].ai_gpr == 3.0
    assert last3[-1].ai_gpr == 5.0


def test_delta_30d_returns_none_when_insufficient_data() -> None:
    rows = [
        AiGprObservation(date(2026, 1, d), 5.0, None)  # type: ignore[arg-type]
        for d in range(1, 11)
    ]
    assert delta_30d(rows) is None


def test_delta_30d_zero_when_no_variance() -> None:
    rows = [
        AiGprObservation(date(2026, 1, d), 5.0, None)  # type: ignore[arg-type]
        for d in range(1, 31)
    ]
    # All values 5.0 → std = 0 → returns 0.0
    assert delta_30d(rows) == 0.0


def test_delta_30d_positive_for_recent_spike() -> None:
    base = [
        AiGprObservation(date(2026, 1, d), 5.0, None)  # type: ignore[arg-type]
        for d in range(1, 30)
    ]
    spike = [AiGprObservation(date(2026, 1, 30), 100.0, None)]  # type: ignore[arg-type]
    rows = base + spike
    z = delta_30d(rows)
    assert z is not None
    assert z > 1.0  # spike should be > 1 std above mean
