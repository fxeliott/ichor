"""Tests for Phase 7 streaming-cadence verdict refresh (ADR-109).

Pins the three behaviours Eliot asked for explicitly :
  • detection — a NEW strong event since the asset's last card yields a
    candidate; an event BEFORE the card does not.
  • cooldown — a fresh card (younger than the cooldown) defers the regen
    even when a new event fired (logged drop, not silent).
  • flag-off = zero-diff — when ``streaming_refresh_enabled`` is OFF the
    CLI returns 1 and NEVER calls the regen or the push.
Plus per-fire cap (logged drops), regen-failure isolation, dry-run, and
the ADR-017 push guard.

Mirrors the mocking style of ``test_session_verdict_live_triggers.py``
(MagicMock + AsyncMock side_effect for ``session.execute``) so the unit
tests need no live DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services import streaming_refresh as sr

_NOW = datetime(2026, 6, 2, 18, 0, 0, tzinfo=UTC)


# ── mock builders ──────────────────────────────────────────────────────


def _result_scalars(rows: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _result_one(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _card(*, gen_minutes_ago: int, session_type: str = "pre_ny", asset: str = "EUR_USD"):
    return SimpleNamespace(
        id="card-uuid",
        asset=asset,
        generated_at=_NOW - timedelta(minutes=gen_minutes_ago),
        session_type=session_type,
    )


def _econ(title: str = "CPI m/m", *, mins_ago: int = 60):
    return SimpleNamespace(
        title=title,
        actual="0.4%",
        forecast="0.3%",
        currency="USD",
        scheduled_at=_NOW - timedelta(minutes=mins_ago),
    )


def _session(side_effects: list) -> MagicMock:
    s = MagicMock()
    s.execute = AsyncMock(side_effect=side_effects)
    return s


class _FakeCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _fake_sm(session=None):
    sess = session if session is not None else MagicMock()
    return lambda: _FakeCM(sess)


def _ns_trigger(
    *, mins_ago: int = 30, ttype: str = "economic_release", desc: str = "CPI m/m — résultat 0.4%"
):
    return SimpleNamespace(
        fired_at_utc=_NOW - timedelta(minutes=mins_ago),
        trigger_type=ttype,
        description=desc,
    )


def _candidate(asset: str, *, mins_ago: int = 30, session_type: str = "pre_ny"):
    return sr.RefreshCandidate(
        asset=asset,
        session_type=session_type,
        last_generated_at=_NOW - timedelta(hours=2),
        newest_trigger=_ns_trigger(mins_ago=mins_ago),
        new_trigger_count=1,
    )


# ── detection ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_new_event_after_card_is_candidate():
    # card 2h ago, economic release 1h ago (= after the card) → candidate.
    session = _session(
        [
            _result_one(_card(gen_minutes_ago=120)),
            _result_scalars([_econ(mins_ago=60)]),  # economic
            _result_scalars([]),  # cb speeches
            _result_scalars([]),  # news
        ]
    )
    candidates, outcomes = await sr.detect_refresh_candidates(
        session, assets=["EUR_USD"], now_utc=_NOW, cooldown_minutes=45
    )
    assert len(candidates) == 1
    assert candidates[0].asset == "EUR_USD"
    assert candidates[0].session_type == "pre_ny"
    assert candidates[0].newest_trigger.trigger_type == "economic_release"
    assert outcomes == []


@pytest.mark.asyncio
async def test_detect_event_before_card_is_no_event():
    # card 30min ago, release 60min ago (= BEFORE the card) → not new.
    session = _session(
        [
            _result_one(_card(gen_minutes_ago=30)),
            _result_scalars([_econ(mins_ago=60)]),
            _result_scalars([]),
            _result_scalars([]),
        ]
    )
    candidates, outcomes = await sr.detect_refresh_candidates(
        session, assets=["EUR_USD"], now_utc=_NOW, cooldown_minutes=45
    )
    assert candidates == []
    assert [o.reason for o in outcomes] == ["no_event"]


@pytest.mark.asyncio
async def test_detect_cooldown_drops_fresh_card():
    # card 10min ago (< 45 cooldown), release 5min ago (= new) → cooldown drop.
    session = _session(
        [
            _result_one(_card(gen_minutes_ago=10)),
            _result_scalars([_econ(mins_ago=5)]),
            _result_scalars([]),
            _result_scalars([]),
        ]
    )
    candidates, outcomes = await sr.detect_refresh_candidates(
        session, assets=["EUR_USD"], now_utc=_NOW, cooldown_minutes=45
    )
    assert candidates == []
    assert len(outcomes) == 1
    assert outcomes[0].action == "dropped"
    assert outcomes[0].reason == "cooldown"
    assert outcomes[0].detail  # explicit, never silent


@pytest.mark.asyncio
async def test_detect_no_card_today_is_skip():
    session = _session([_result_one(None)])  # no card → returns before assembling triggers
    candidates, outcomes = await sr.detect_refresh_candidates(
        session, assets=["EUR_USD"], now_utc=_NOW, cooldown_minutes=45
    )
    assert candidates == []
    assert [o.reason for o in outcomes] == ["no_card"]


@pytest.mark.asyncio
async def test_detect_failure_is_isolated():
    # session.execute raises on the card query → detect_error, never aborts.
    s = MagicMock()
    s.execute = AsyncMock(side_effect=RuntimeError("db blip"))
    candidates, outcomes = await sr.detect_refresh_candidates(
        s, assets=["EUR_USD"], now_utc=_NOW, cooldown_minutes=45
    )
    assert candidates == []
    assert [o.reason for o in outcomes] == ["detect_error"]


# ── orchestration : cap / regen / push / dry-run ───────────────────────


@pytest.mark.asyncio
async def test_per_fire_cap_logs_overflow_as_drops(monkeypatch):
    cands = [
        _candidate(a, mins_ago=10 + i)
        for i, a in enumerate(["EUR_USD", "GBP_USD", "XAU_USD", "SPX500_USD"])
    ]
    monkeypatch.setattr(sr, "detect_refresh_candidates", AsyncMock(return_value=(cands, [])))
    regen = AsyncMock(return_value=0)
    push = AsyncMock(return_value=1)
    result = await sr.run_streaming_refresh(
        session_factory=_fake_sm(),
        now_utc=_NOW,
        max_regens_per_fire=2,
        regen_fn=regen,
        push_fn=push,
    )
    assert result.regenerated == 2
    assert regen.await_count == 2
    assert result.dropped == 2
    assert all(o.reason == "per_fire_cap" for o in result.outcomes if o.action == "dropped")


@pytest.mark.asyncio
async def test_regen_success_pushes(monkeypatch):
    monkeypatch.setattr(
        sr, "detect_refresh_candidates", AsyncMock(return_value=([_candidate("EUR_USD")], []))
    )
    regen = AsyncMock(return_value=0)
    push = AsyncMock(return_value=3)
    result = await sr.run_streaming_refresh(
        session_factory=_fake_sm(), now_utc=_NOW, regen_fn=regen, push_fn=push
    )
    assert result.regenerated == 1
    assert result.pushed == 1
    regen.assert_awaited_once()
    # regen called with the latest card's session window + live + matched flags
    _, kwargs = regen.await_args
    assert kwargs["live"] is True
    push.assert_awaited_once()
    _, push_kwargs = push.await_args
    assert push_kwargs["url"] == "/briefing/EUR_USD"


@pytest.mark.asyncio
async def test_regen_failure_is_isolated_no_push(monkeypatch):
    monkeypatch.setattr(
        sr, "detect_refresh_candidates", AsyncMock(return_value=([_candidate("EUR_USD")], []))
    )
    regen = AsyncMock(return_value=4)  # safety-gate reject exit code
    push = AsyncMock(return_value=0)
    result = await sr.run_streaming_refresh(
        session_factory=_fake_sm(), now_utc=_NOW, regen_fn=regen, push_fn=push
    )
    assert result.failed == 1
    assert result.regenerated == 0
    push.assert_not_awaited()  # no push when regen failed


@pytest.mark.asyncio
async def test_dry_run_never_regenerates(monkeypatch):
    monkeypatch.setattr(
        sr, "detect_refresh_candidates", AsyncMock(return_value=([_candidate("EUR_USD")], []))
    )
    regen = AsyncMock(return_value=0)
    push = AsyncMock(return_value=0)
    result = await sr.run_streaming_refresh(
        session_factory=_fake_sm(), now_utc=_NOW, dry_run=True, regen_fn=regen, push_fn=push
    )
    regen.assert_not_awaited()
    push.assert_not_awaited()
    assert result.regenerated == 0
    assert [o.action for o in result.outcomes] == ["dry_run"]


# ── ADR-017 push guard ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_refresh_skips_adr017_token():
    push = AsyncMock(return_value=1)
    # Defensive guard: a description that trips ADR-017 must NOT be pushed.
    trigger = _ns_trigger(ttype="news_headline", desc="BUY everything now aggressively")
    pushed = await sr._notify_refresh("EUR_USD", trigger, push_fn=push)
    assert pushed is False
    push.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_refresh_sends_clean_event():
    push = AsyncMock(return_value=2)
    trigger = _ns_trigger(desc="CPI m/m — résultat 0.4% (consensus 0.3%)")
    pushed = await sr._notify_refresh("XAU_USD", trigger, push_fn=push)
    assert pushed is True
    push.assert_awaited_once()
    args, kwargs = push.await_args
    assert kwargs["url"] == "/briefing/XAU_USD"


# ── CLI : flag-off = zero-diff ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cli_flag_off_is_zero_diff(monkeypatch):
    from ichor_api.cli import run_streaming_refresh as cli

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _fake_sm())
    monkeypatch.setattr(cli, "is_enabled", AsyncMock(return_value=False))
    spy = AsyncMock()
    monkeypatch.setattr(cli, "run_streaming_refresh", spy)

    rc = await cli._run(
        dry_run=False,
        cooldown_minutes=45,
        max_per_fire=3,
        only_asset=None,
        enable_rag=True,
        enable_tools=False,
    )
    assert rc == 1  # flag OFF = clean skip
    spy.assert_not_called()  # zero-diff : never touches the regen pipeline


@pytest.mark.asyncio
async def test_cli_flag_on_runs_refresh(monkeypatch):
    from ichor_api.cli import run_streaming_refresh as cli

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _fake_sm())
    monkeypatch.setattr(cli, "is_enabled", AsyncMock(return_value=True))
    spy = AsyncMock(return_value=sr.StreamingRefreshResult(outcomes=[]))
    monkeypatch.setattr(cli, "run_streaming_refresh", spy)

    rc = await cli._run(
        dry_run=True,
        cooldown_minutes=45,
        max_per_fire=3,
        only_asset="EUR_USD",
        enable_rag=True,
        enable_tools=False,
    )
    assert rc == 0
    spy.assert_awaited_once()
