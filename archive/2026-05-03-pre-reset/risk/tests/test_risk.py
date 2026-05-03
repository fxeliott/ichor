"""End-to-end tests for the risk engine + kill switch."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ichor_risk import (
    KillSwitch,
    KillSwitchTripped,
    RiskConfig,
    RiskDecision,
    RiskEngine,
    RiskSnapshot,
)
from ichor_risk.engine import TradeIntent, _full_kelly


# ───────────────────────── kill switch ─────────────────────────


def test_kill_switch_clear_by_default(tmp_path: Path) -> None:
    ks = KillSwitch(flag_path=tmp_path / "MISSING")
    assert not ks.is_tripped()
    ks.assert_clear()


def test_kill_switch_trips_on_file_flag(tmp_path: Path) -> None:
    flag = tmp_path / "KILL_SWITCH"
    flag.write_text("tripped at 2026-05-03")
    ks = KillSwitch(flag_path=flag)
    assert ks.is_tripped()
    with pytest.raises(KillSwitchTripped):
        ks.assert_clear()


def test_kill_switch_trips_on_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ICHOR_KILL_SWITCH", "1")
    ks = KillSwitch(flag_path=tmp_path / "MISSING")
    assert ks.is_tripped()


def test_kill_switch_trip_locked_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once tripped, stays tripped even if env / file are cleared."""
    flag = tmp_path / "KILL_SWITCH"
    flag.write_text("trip")
    ks = KillSwitch(flag_path=flag)
    assert ks.is_tripped()
    flag.unlink()
    # Still tripped — operator must restart process
    assert ks.is_tripped()
    assert ks.trip_locked


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "Yes", "on"])
def test_kill_switch_truthy_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, val: str
) -> None:
    monkeypatch.setenv("ICHOR_KILL_SWITCH", val)
    ks = KillSwitch(flag_path=tmp_path / "MISSING")
    assert ks.is_tripped()


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_kill_switch_falsy_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, val: str
) -> None:
    monkeypatch.setenv("ICHOR_KILL_SWITCH", val)
    ks = KillSwitch(flag_path=tmp_path / "MISSING")
    assert not ks.is_tripped()


# ───────────────────────── kelly math ─────────────────────────


def test_full_kelly_no_edge_returns_zero() -> None:
    # 50/50 with symmetric payoff = no edge
    assert _full_kelly(0.5, 0.01, 0.01) == 0.0


def test_full_kelly_with_edge() -> None:
    # 60% probability, 1:1 payoff → Kelly = 0.20
    f = _full_kelly(0.6, 0.01, 0.01)
    assert abs(f - 0.20) < 1e-6


def test_full_kelly_zero_payoff_returns_zero() -> None:
    assert _full_kelly(0.7, 0.0, 0.01) == 0.0
    assert _full_kelly(0.7, 0.01, 0.0) == 0.0


# ───────────────────────── risk engine ─────────────────────────


def _ks(tmp_path: Path) -> KillSwitch:
    """Helper : a clean kill switch pointing at a file that doesn't exist."""
    return KillSwitch(flag_path=tmp_path / "NEVER_EXISTS")


def _snap(asset: str = "EUR_USD", equity: float = 10_000.0,
          high: float | None = None, trades: int = 0,
          ref: float = 1.10) -> RiskSnapshot:
    return RiskSnapshot(
        equity=equity,
        equity_high_today=high if high is not None else equity,
        trades_today=trades,
        asset=asset,
        reference_price=ref,
    )


def _intent(p: float = 0.6, asset: str = "EUR_USD",
            direction: str = "long") -> TradeIntent:
    return TradeIntent(
        asset=asset, direction=direction, probability=p,
        avg_win_pct=0.005, avg_loss_pct=0.005,
    )


def test_engine_refuses_without_kill_switch_when_required() -> None:
    cfg = RiskConfig()
    engine = RiskEngine(config=cfg, kill_switch=None)
    res = engine.evaluate(_intent(), _snap())
    assert not res.allowed
    assert "kill_switch_not_configured" in res.reason


def test_engine_refuses_when_kill_switch_tripped(tmp_path: Path) -> None:
    flag = tmp_path / "KILL"
    flag.write_text("trip")
    engine = RiskEngine(config=RiskConfig(), kill_switch=KillSwitch(flag_path=flag))
    res = engine.evaluate(_intent(), _snap())
    assert not res.allowed
    assert "Kill switch tripped" in res.reason


def test_engine_refuses_on_asset_mismatch(tmp_path: Path) -> None:
    engine = RiskEngine(config=RiskConfig(), kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(asset="EUR_USD"), _snap(asset="XAU_USD"))
    assert not res.allowed
    assert "asset_mismatch" in res.reason


def test_engine_refuses_on_daily_dd_stop(tmp_path: Path) -> None:
    engine = RiskEngine(config=RiskConfig(), kill_switch=_ks(tmp_path))
    # Equity is 9_400 vs high 10_000 → 6% DD, above default 5% cap
    res = engine.evaluate(_intent(), _snap(equity=9_400, high=10_000))
    assert not res.allowed
    assert "daily_dd_stop" in res.reason


def test_engine_refuses_when_trade_cap_reached(tmp_path: Path) -> None:
    cfg = RiskConfig(max_trades_per_day=5)
    engine = RiskEngine(config=cfg, kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(), _snap(trades=5))
    assert not res.allowed
    assert "max_trades_per_day" in res.reason


def test_engine_refuses_no_edge(tmp_path: Path) -> None:
    engine = RiskEngine(config=RiskConfig(), kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(p=0.5), _snap())  # 50/50, no edge
    assert not res.allowed
    assert "no_edge" in res.reason


def test_engine_sizes_within_kelly_cap(tmp_path: Path) -> None:
    """Kelly with extreme edge should be capped at the configured cap."""
    cfg = RiskConfig(kelly_fraction_cap=0.10, full_kelly_multiplier=0.25)
    engine = RiskEngine(config=cfg, kill_switch=_ks(tmp_path))
    res = engine.evaluate(
        TradeIntent(asset="EUR_USD", direction="long",
                    probability=0.95, avg_win_pct=0.01, avg_loss_pct=0.005),
        _snap(equity=10_000, ref=1.10),
    )
    assert res.allowed
    # 10 % cap × 10000 / 1.10 = ~909 max
    assert 0 < res.sized_qty <= 10_000 * 0.10 / 1.10 + 1e-6
    assert res.sizing_fraction <= cfg.kelly_fraction_cap


def test_engine_short_returns_negative_qty(tmp_path: Path) -> None:
    engine = RiskEngine(config=RiskConfig(), kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(direction="short"), _snap())
    assert res.allowed
    assert res.sized_qty < 0


def test_engine_below_min_size_refused(tmp_path: Path) -> None:
    cfg = RiskConfig(min_position_size=1_000_000)  # absurdly large min
    engine = RiskEngine(config=cfg, kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(), _snap())
    assert not res.allowed
    assert "below_min_position_size" in res.reason


def test_engine_decision_carries_sizing_fraction(tmp_path: Path) -> None:
    engine = RiskEngine(config=RiskConfig(), kill_switch=_ks(tmp_path))
    res = engine.evaluate(_intent(p=0.6), _snap())
    if res.allowed:
        assert 0 < res.sizing_fraction <= RiskConfig().kelly_fraction_cap


def test_engine_kill_switch_trip_during_session_blocks_subsequent_calls(
    tmp_path: Path,
) -> None:
    """Trip mid-session must block all further evaluate() calls."""
    flag = tmp_path / "KILL"
    ks = KillSwitch(flag_path=flag)
    engine = RiskEngine(config=RiskConfig(), kill_switch=ks)

    # First call clean
    res1 = engine.evaluate(_intent(p=0.6), _snap())
    assert res1.allowed

    # Trip the switch
    flag.write_text("manual trip")

    res2 = engine.evaluate(_intent(p=0.6), _snap())
    assert not res2.allowed
    assert "Kill switch tripped" in res2.reason

    # Even after removing the file, in-process trip lock holds
    flag.unlink()
    res3 = engine.evaluate(_intent(p=0.6), _snap())
    assert not res3.allowed
