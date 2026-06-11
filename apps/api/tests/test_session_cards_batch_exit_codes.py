"""Exit-code contract of `run_session_cards_batch` (ADR-110).

rc=0 — every card ok · rc=1 — PARTIAL failure (≥1 ok, ≥1 failed) ·
rc=2 — TOTAL failure (0 ok). rc=2 is deliberately NOT whitelisted by the
systemd unit (`SuccessExitStatus=0 1`), so a dead-runner / exhausted-quota
batch flips the unit to Result=failed and fires OnFailure=ichor-notify@
instead of masquerading as success — the 2026-06-10 P0 class (runner down
all day, 0/6 cards, unit green) can no longer pass silent.
"""

from __future__ import annotations

import pytest
from ichor_api.cli import run_session_cards_batch as batch_mod

_ASSETS = ("EUR_USD", "GBP_USD")


def _fake_card_factory(rc_by_asset: dict[str, int | Exception]):
    async def _fake(asset: str, session_type: str, **kwargs: object) -> int:
        outcome = rc_by_asset[asset]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return _fake


async def _run(monkeypatch: pytest.MonkeyPatch, rc_by_asset: dict[str, int | Exception]) -> int:
    monkeypatch.setattr(batch_mod, "run_one_card", _fake_card_factory(rc_by_asset))
    return await batch_mod._run_batch(
        session_type="pre_londres",
        assets=_ASSETS,
        live=False,
        inter_card_sleep_s=0.0,
    )


class TestBatchExitCodeContract:
    @pytest.mark.asyncio
    async def test_all_ok_returns_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rc = await _run(monkeypatch, {"EUR_USD": 0, "GBP_USD": 0})
        assert rc == 0

    @pytest.mark.asyncio
    async def test_partial_failure_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """≥1 card shipped — warning class, whitelisted by SuccessExitStatus=0 1."""
        rc = await _run(monkeypatch, {"EUR_USD": 0, "GBP_USD": 1})
        assert rc == 1

    @pytest.mark.asyncio
    async def test_total_failure_returns_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """0 cards — the dead-runner class. MUST be rc=2 (systemd failure)."""
        rc = await _run(monkeypatch, {"EUR_USD": 1, "GBP_USD": 1})
        assert rc == 2

    @pytest.mark.asyncio
    async def test_total_failure_via_exceptions_returns_2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raised exceptions (runner unreachable) count as failures too."""
        rc = await _run(
            monkeypatch,
            {"EUR_USD": RuntimeError("tunnel 530"), "GBP_USD": RuntimeError("tunnel 530")},
        )
        assert rc == 2

    @pytest.mark.asyncio
    async def test_market_closed_all_skipped_returns_0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-105 gate suppressing every asset is a clean no-op, not a
        failure — completes the docstring contract (verifier finding F9)."""

        class _FakeFlagSession:
            async def __aenter__(self) -> _FakeFlagSession:
                return self

            async def __aexit__(self, *args: object) -> bool:
                return False

        class _ClosedStatus:
            market_closed_fx = True
            market_closed_us_equity = True
            state = "weekend"
            holiday_name = None

        async def _flag_on(session: object, flag: str) -> bool:
            return True

        monkeypatch.setattr(batch_mod, "get_sessionmaker", lambda: _FakeFlagSession)
        monkeypatch.setattr(batch_mod, "is_enabled", _flag_on)
        monkeypatch.setattr(batch_mod, "compute_session_status", lambda: _ClosedStatus())
        monkeypatch.setattr(batch_mod, "market_closed_for_asset", lambda a, s: True)
        monkeypatch.setattr(batch_mod, "run_one_card", _fake_card_factory({}))

        rc = await batch_mod._run_batch(
            session_type="pre_londres",
            assets=_ASSETS,
            live=False,
            inter_card_sleep_s=0.0,
        )
        assert rc == 0

    @pytest.mark.asyncio
    async def test_unknown_session_type_returns_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bad invocation shares the hard-failure code (pre-existing contract)."""
        monkeypatch.setattr(batch_mod, "run_one_card", _fake_card_factory({}))
        rc = await batch_mod._run_batch(
            session_type="definitely_not_a_session",
            assets=_ASSETS,
            live=False,
            inter_card_sleep_s=0.0,
        )
        assert rc == 2
