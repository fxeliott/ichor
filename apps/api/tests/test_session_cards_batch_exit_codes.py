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
from ichor_api.cli._exit import ExitCode, cron_main

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


class TestBatchOuterEntrypointSilentDeathGuard:
    """S02 socle residual audit 2026-06-19 — the per-card loop already maps
    0/1/2 correctly, but the OUTER entrypoint used a bare
    `sys.exit(asyncio.run(_main(...)))`. An exception escaping OUTSIDE the loop
    (argparse/setup, an unexpected `_run_batch` error, or the engine-dispose
    `finally`) exited 1 and was MASKED by `SuccessExitStatus=0 1` → silent
    batch death — exactly the class `_exit.cron_main` was built to close for the
    `_check` CLIs. The entrypoint now delegates to `cron_main`."""

    def test_entrypoint_wires_cron_main(self) -> None:
        # Wiring guard : the bare asyncio.run path is what masked exit-1.
        assert batch_mod.cron_main is cron_main

    def test_uncaught_exception_maps_to_transient_3_not_masked_1(self) -> None:
        async def _boom() -> int:
            raise RuntimeError("engine dispose blew up (transient asyncpg)")

        rc = cron_main(lambda: _boom())
        # 3 is NOT whitelisted by SuccessExitStatus=0 1 → OnFailure fires.
        assert rc == ExitCode.TRANSIENT == 3

    def test_int_contract_propagated_unchanged(self) -> None:
        # The 0/1/2 batch return must pass through cron_main untouched so the
        # existing per-card contract (and rc=2 "page" semantics) is preserved.
        for code in (0, 1, 2):

            async def _ret(c: int = code) -> int:
                return c

            assert cron_main(lambda: _ret()) == code
