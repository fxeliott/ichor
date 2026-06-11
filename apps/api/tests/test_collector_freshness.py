"""S03 Chantier D — collector-freshness monitor pure-logic tests.

No DB, no HTTP: registry invariants, minute-granular classification,
ADR-105 market gating (weekend + Monday-reopen false-alarm kill), and
the transition-based exit contract (mirrors runner-health-check).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ichor_api.services.collector_freshness import (
    FRESHNESS_REGISTRY,
    FreshnessSpec,
    decide_exit,
    evaluate_freshness,
    market_open_for_gate,
    should_check,
)
from ichor_api.services.market_session import compute_session_status

# A plain Wednesday, 14:00 UTC (16:00 Paris) — FX + US equities open.
WEDNESDAY_OPEN = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
# Saturday noon UTC — everything closed.
SATURDAY = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
# Monday 00:30 UTC (02:30 Paris) — FX reopened Sunday ~22:00 Paris.
MONDAY_EARLY = datetime(2026, 6, 15, 0, 30, tzinfo=UTC)


def _spec(**kw) -> FreshnessSpec:
    base = {
        "source_key": "test",
        "table": "test_table",
        "ts_column": "fetched_at",
        "max_age": timedelta(minutes=15),
        "criticality": "critical",
    }
    base.update(kw)
    return FreshnessSpec(**base)


# ── Registry invariants ───────────────────────────────────────────────


def test_registry_keys_and_tables_unique() -> None:
    keys = [s.source_key for s in FRESHNESS_REGISTRY]
    tables = [s.table for s in FRESHNESS_REGISTRY]
    assert len(keys) == len(set(keys))
    assert len(tables) == len(set(tables))


def test_registry_has_critical_realtime_tier() -> None:
    """The Chantier D gate needs a fast critical tier: killed collector
    → alert <= 15 min (5-min timer + <=15-min max_age)."""
    crit = {s.source_key: s for s in FRESHNESS_REGISTRY if s.criticality == "critical"}
    assert {"fx_ticks", "polygon_intraday", "polymarket", "news_items"} <= set(crit)
    assert crit["fx_ticks"].max_age <= timedelta(minutes=15)
    assert crit["polygon_intraday"].max_age <= timedelta(minutes=15)


def test_registry_market_gates_are_coherent() -> None:
    """Market-gated specs must have max_age shorter than the shortest
    market closure (weekend ~49h) — otherwise the both-endpoints-open
    gating logic would never re-arm after a closure."""
    for s in FRESHNESS_REGISTRY:
        if s.gate != "none":
            assert s.max_age < timedelta(hours=49), s.source_key


def test_spec_rejects_sql_unsafe_identifiers() -> None:
    with pytest.raises(ValueError):
        _spec(table="bad-table; DROP")
    with pytest.raises(ValueError):
        _spec(ts_column="1col")


# ── Classification ────────────────────────────────────────────────────


def test_fresh_within_window() -> None:
    r = evaluate_freshness(_spec(), WEDNESDAY_OPEN - timedelta(minutes=5), now=WEDNESDAY_OPEN)
    assert r.status == "fresh"
    assert not r.is_degraded


def test_stale_past_window_minute_granular() -> None:
    """A 20-min outage on a 15-min window MUST classify stale — the
    day-granular classify_liveness cannot see this; that's why this
    module exists."""
    r = evaluate_freshness(_spec(), WEDNESDAY_OPEN - timedelta(minutes=20), now=WEDNESDAY_OPEN)
    assert r.status == "stale"
    assert r.is_degraded


def test_absent_when_table_empty() -> None:
    r = evaluate_freshness(_spec(), None, now=WEDNESDAY_OPEN)
    assert r.status == "absent"
    assert r.is_degraded


def test_naive_timestamp_coerced_to_utc() -> None:
    naive = (WEDNESDAY_OPEN - timedelta(minutes=5)).replace(tzinfo=None)
    r = evaluate_freshness(_spec(), naive, now=WEDNESDAY_OPEN)
    assert r.status == "fresh"


# ── ADR-105 market gating ─────────────────────────────────────────────


def test_fx_gate_skips_weekend() -> None:
    spec = _spec(gate="fx")
    status = compute_session_status(SATURDAY)
    assert market_open_for_gate("fx", status) is False
    assert should_check(spec, status_now=status, status_window_start=status) is False


def test_fx_gate_skips_monday_reopen_grace() -> None:
    """Seconds after the Sunday reopen, the latest fx tick is Friday-old.
    Window start (now - 15min) falls inside the weekend → skip. This is
    the Monday-reopen false-alarm kill."""
    status_now = compute_session_status(MONDAY_EARLY)
    assert status_now.market_closed_fx is False  # market IS open again
    # 15 minutes before MONDAY_EARLY is still Sunday 21:45-ish Paris? No —
    # 02:15 Paris Monday is open too; use a wider window to cross midnight
    # into the weekend.
    wide = _spec(gate="fx", max_age=timedelta(hours=5))
    window_start = compute_session_status(MONDAY_EARLY - timedelta(hours=5))
    assert window_start.market_closed_fx is True
    assert should_check(wide, status_now=status_now, status_window_start=window_start) is False


def test_ungated_always_checked() -> None:
    spec = _spec(gate="none")
    status = compute_session_status(SATURDAY)
    assert should_check(spec, status_now=status, status_window_start=status) is True


def test_open_market_is_checked() -> None:
    spec = _spec(gate="fx")
    status = compute_session_status(WEDNESDAY_OPEN)
    assert should_check(spec, status_now=status, status_window_start=status) is True


# ── Transition exit contract ──────────────────────────────────────────


def test_exit_healthy_steady() -> None:
    code, state = decide_exit(None, critical_degraded=False, now_epoch=1000)
    assert code == 0
    assert state["status"] == "ok"


def test_exit_2_on_transition_only() -> None:
    code, state = decide_exit(
        {"status": "ok", "last_notify_epoch": 0}, critical_degraded=True, now_epoch=1000
    )
    assert code == 2
    assert state == {"status": "degraded", "last_notify_epoch": 1000}
    # Next tick, still degraded, within renotify window → steady 0.
    code2, state2 = decide_exit(state, critical_degraded=True, now_epoch=1300)
    assert code2 == 0
    assert state2["last_notify_epoch"] == 1000


def test_exit_2_renotifies_after_window() -> None:
    state = {"status": "degraded", "last_notify_epoch": 1000}
    code, new = decide_exit(state, critical_degraded=True, now_epoch=1000 + 7200)
    assert code == 2
    assert new["last_notify_epoch"] == 1000 + 7200


def test_exit_recovers_to_ok() -> None:
    state = {"status": "degraded", "last_notify_epoch": 1000}
    code, new = decide_exit(state, critical_degraded=False, now_epoch=9000)
    assert code == 0
    assert new["status"] == "ok"
