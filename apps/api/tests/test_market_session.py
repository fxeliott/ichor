"""ADR-099 Tier 1.3 — market session + US holiday engine tests.

Pins exact, independently-checkable 2026 dates (no self-referential
asserts) : Western Easter 2026 = Sun 5 Apr → Good Friday Fri 3 Apr ;
MLK = 3rd Mon Jan = 19 Jan ; Thanksgiving = 4th Thu Nov = 26 Nov ;
Christmas 25 Dec 2026 = Friday ; 2026-05-16 = Saturday.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from ichor_api.cli.run_session_cards_batch import _DEFAULT_ASSETS, _run_batch
from ichor_api.services.market_session import (
    _US_EQUITY_ASSETS,
    _easter,
    compute_session_status,
    market_closed_for_asset,
    us_market_holidays,
)

PARIS = ZoneInfo("Europe/Paris")


def test_easter_2026_is_april_5():
    assert _easter(2026) == date(2026, 4, 5)


def test_us_holidays_2026_known_dates():
    h = us_market_holidays(2026)
    assert h[date(2026, 1, 1)] == "New Year's Day"
    assert h[date(2026, 1, 19)] == "Martin Luther King Jr. Day"
    assert h[date(2026, 4, 3)] == "Good Friday"  # Easter 5 Apr − 2
    assert h[date(2026, 11, 26)] == "Thanksgiving"
    assert h[date(2026, 12, 25)] == "Christmas Day"
    # A plain Wednesday is NOT a holiday
    assert date(2026, 3, 4) not in h


def test_observed_shift_sat_to_fri_and_sun_to_mon():
    # 2027: Jul 4 = Sunday → observed Mon Jul 5 ; Dec 25 = Saturday →
    # observed Fri Dec 24 ; New Year Jan 1 2027 = Friday (no shift).
    h = us_market_holidays(2027)
    assert date(2027, 7, 5) in h and date(2027, 7, 4) not in h
    assert date(2027, 12, 24) in h and date(2027, 12, 25) not in h


def test_saturday_is_weekend_fx_closed():
    s = compute_session_status(datetime(2026, 5, 16, 12, 0, tzinfo=PARIS))  # Saturday
    assert s.state == "weekend"
    assert s.market_closed_fx is True
    assert s.market_closed_us_equity is True
    assert s.holiday_name is None
    assert s.minutes_until_next_open >= 0


def test_us_holiday_weekday_fx_open_equity_closed():
    # 2026-12-25 = Friday (a weekday) → US equities closed, FX open.
    s = compute_session_status(datetime(2026, 12, 25, 10, 0, tzinfo=PARIS))
    assert s.state == "us_holiday"
    assert s.market_closed_us_equity is True
    assert s.market_closed_fx is False
    assert s.holiday_name == "Christmas Day"


def test_normal_weekday_pre_londres_window():
    # 2026-05-13 = Wednesday, 07:00 Paris → pre-Londres.
    s = compute_session_status(datetime(2026, 5, 13, 7, 0, tzinfo=PARIS))
    assert s.state == "pre_londres"
    assert s.market_closed_fx is False


def test_normal_weekday_ny_active_afternoon():
    # 2026-05-13 Wed 17:00 Paris → NY session active (NY opens ~15:30).
    s = compute_session_status(datetime(2026, 5, 13, 17, 0, tzinfo=PARIS))
    assert s.state == "ny_active"


# ─── ADR-105 — market_closed_for_asset pure SSOT (gate decision) ─────────

_ALL6 = ("EUR_USD", "GBP_USD", "USD_CAD", "XAU_USD", "NAS100_USD", "SPX500_USD")


def test_us_equity_asset_set_is_exactly_spx_and_nas():
    # Pin the asset-class set so adding a US-equity asset is a conscious
    # change (the gate's correctness depends on this membership).
    assert _US_EQUITY_ASSETS == frozenset({"SPX500_USD", "NAS100_USD"})


def test_market_closed_for_asset_weekend_closes_every_asset():
    s = compute_session_status(datetime(2026, 5, 16, 12, 0, tzinfo=PARIS))  # Saturday
    assert s.state == "weekend"
    for a in _ALL6:
        assert market_closed_for_asset(a, s) is True, a


def test_market_closed_for_asset_us_holiday_closes_only_us_equities():
    # 2026-12-25 Christmas (Friday weekday) → US equities closed, FX/XAU open.
    s = compute_session_status(datetime(2026, 12, 25, 10, 0, tzinfo=PARIS))
    assert s.state == "us_holiday"
    assert market_closed_for_asset("SPX500_USD", s) is True
    assert market_closed_for_asset("NAS100_USD", s) is True
    for a in ("EUR_USD", "GBP_USD", "USD_CAD", "XAU_USD"):
        assert market_closed_for_asset(a, s) is False, a


def test_market_closed_for_asset_normal_weekday_closes_nothing():
    s = compute_session_status(datetime(2026, 5, 13, 7, 0, tzinfo=PARIS))  # Wed pre_londres
    assert s.state == "pre_londres"
    for a in _ALL6:
        assert market_closed_for_asset(a, s) is False, a


# ─── ADR-105 — the _run_batch gate (flag-OFF inert / skip / FAIL-OPEN) ───


def _async_ctx(session):
    """Build a fake `async with sm() as session:` context (repo idiom,
    mirrors test_run_bundesbank_bund_cli.py)."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _patch_session(monkeypatch):
    fake_sm = MagicMock(return_value=_async_ctx(AsyncMock()))
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.get_sessionmaker",
        lambda: fake_sm,
    )


@pytest.mark.asyncio
async def test_gate_flag_off_is_inert_all_assets_run(monkeypatch):
    """No flag row ⇒ is_enabled→False ⇒ gate inert ⇒ every asset runs
    (zero behaviour change — the ship-OFF contract)."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.is_enabled",
        AsyncMock(return_value=False),
    )
    one = AsyncMock(return_value=0)
    monkeypatch.setattr("ichor_api.cli.run_session_cards_batch.run_one_card", one)

    rc = await _run_batch(
        session_type="pre_ny",
        assets=_DEFAULT_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
        push_on_complete=False,
    )
    assert rc == 0
    assert one.call_count == len(_DEFAULT_ASSETS)  # all 6 ran — gate inert


@pytest.mark.asyncio
async def test_gate_on_weekend_skips_all_no_cards(monkeypatch, capsys):
    """Flag ON + weekend ⇒ every asset skipped, run_one_card NEVER
    called, batch returns 0 (no failed state)."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.is_enabled",
        AsyncMock(return_value=True),
    )
    weekend = compute_session_status(datetime(2026, 5, 16, 12, 0, tzinfo=PARIS))
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.compute_session_status",
        lambda *a, **k: weekend,
    )
    one = AsyncMock(return_value=0)
    monkeypatch.setattr("ichor_api.cli.run_session_cards_batch.run_one_card", one)

    rc = await _run_batch(
        session_type="pre_ny",
        assets=_DEFAULT_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
        push_on_complete=False,
    )
    assert rc == 0
    one.assert_not_called()  # weekend → zero card-gen, zero claude-runner
    assert "no cards this tick" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_gate_on_us_holiday_skips_only_us_equities(monkeypatch):
    """Flag ON + US holiday ⇒ SPX500/NAS100 skipped, FX/XAU still run
    (they trade through US holidays — no over-suppression)."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.is_enabled",
        AsyncMock(return_value=True),
    )
    holiday = compute_session_status(datetime(2026, 12, 25, 10, 0, tzinfo=PARIS))
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.compute_session_status",
        lambda *a, **k: holiday,
    )
    seen: list[str] = []

    async def _one(asset, _st, **_kw):
        seen.append(asset)
        return 0

    monkeypatch.setattr("ichor_api.cli.run_session_cards_batch.run_one_card", _one)

    rc = await _run_batch(
        session_type="pre_ny",
        assets=_DEFAULT_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
        push_on_complete=False,
    )
    assert rc == 0
    assert "SPX500_USD" not in seen and "NAS100_USD" not in seen
    assert set(seen) == {"EUR_USD", "GBP_USD", "USD_CAD", "XAU_USD"}


@pytest.mark.asyncio
async def test_gate_FAILS_OPEN_when_flag_check_raises(monkeypatch, capsys):
    """SAFETY-CRITICAL : if the gate errors (flag-DB read raises), the
    batch MUST proceed and generate — a missed real pre-session is
    unrecoverable (the timer does not re-fire). The gate never converts
    an error into a skip (ADR-105 §3 fail-open invariant)."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.is_enabled",
        AsyncMock(side_effect=RuntimeError("feature_flags DB unreachable")),
    )
    one = AsyncMock(return_value=0)
    monkeypatch.setattr("ichor_api.cli.run_session_cards_batch.run_one_card", one)

    rc = await _run_batch(
        session_type="pre_ny",
        assets=_DEFAULT_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
        push_on_complete=False,
    )
    assert rc == 0
    assert one.call_count == len(_DEFAULT_ASSETS)  # FAIL-OPEN: all ran
    assert "fail-open" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_gate_anomaly_empty_keepset_on_open_market_fails_open(monkeypatch, capsys):
    """SAFETY-CRITICAL (ichor-trader R28 YELLOW-1) : a future SSOT
    regression that empties the keep-set while the market is NOT
    positively closed MUST NOT silently suppress a real session. The
    early `return 0` is structurally gated on a positive closed-state ;
    an empty keep-set on an OPEN market ⇒ log loud + generate the FULL
    set (fail-open made structural, not emergent)."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.is_enabled",
        AsyncMock(return_value=True),
    )
    # Open market (normal weekday pre-Londres : both closed-booleans False).
    open_status = compute_session_status(datetime(2026, 5, 13, 7, 0, tzinfo=PARIS))
    assert open_status.market_closed_fx is False
    assert open_status.market_closed_us_equity is False
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.compute_session_status",
        lambda *a, **k: open_status,
    )
    # Simulate a future SSOT regression : every asset reports "closed"
    # even though the market is open → empty keep-set on an OPEN market.
    monkeypatch.setattr(
        "ichor_api.cli.run_session_cards_batch.market_closed_for_asset",
        lambda *a, **k: True,
    )
    one = AsyncMock(return_value=0)
    monkeypatch.setattr("ichor_api.cli.run_session_cards_batch.run_one_card", one)

    rc = await _run_batch(
        session_type="pre_ny",
        assets=_DEFAULT_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
        push_on_complete=False,
    )
    assert rc == 0
    # The real session is NOT suppressed — all 6 generated despite the
    # inconsistent gate SSOT.
    assert one.call_count == len(_DEFAULT_ASSETS)
    err = capsys.readouterr()
    assert "anomaly" in err.err and "fail-open" in err.err
    assert "no cards this tick" not in err.out
