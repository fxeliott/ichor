"""S02 socle — run_session_card commit-retry guard.

The session-card commit (run_session_card.py) is the single moment a fully
computed card (safety gate + coherence reconcile + synthesis snapshots +
dimension votes) becomes durable. A bare ``await session.commit()`` lost the
whole card on a transient DB blip. The fix wraps it in a bounded inline
retry (``_commit_with_retry``) that rolls back between attempts, retries
TRANSIENT errors only, and re-raises on exhaustion.

Two layers : source-inspection invariants (mirror
test_invariants_r62_key_levels_persistence.py — fail the build if the guard
is reverted) + a behavioural unit test of the extracted helper.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ichor_api.cli.run_session_card import _commit_with_retry
from sqlalchemy import exc as sa_exc

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = (
    _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_session_card.py"
).read_text(encoding="utf-8")
_NORM = re.sub(r"\s+", " ", _SRC)


# ── source-inspection invariants ──────────────────────────────────────


def test_persist_goes_through_commit_retry_not_bare_commit() -> None:
    assert "_commit_with_retry(session, row)" in _NORM, (
        "the session-card persist must call _commit_with_retry(session, row) — "
        "a bare `await session.commit()` loses the card on a transient DB blip."
    )


def test_commit_retry_rolls_back_between_attempts() -> None:
    assert "await session.rollback()" in _NORM, (
        "an async session that errored mid-commit must be rolled back before "
        "re-commit (else InvalidRequestError)."
    )


def test_commit_retry_catches_transient_only_not_integrity() -> None:
    # The except clause catches exactly the two transient connection classes.
    assert "except (sa_exc.OperationalError, sa_exc.InterfaceError)" in _NORM, (
        "commit retry must catch ONLY the transient connection errors "
        "(OperationalError / InterfaceError)."
    )
    # IntegrityError / ProgrammingError are deterministic — retrying masks bugs.
    # Guard the actual catch target (the prose comment mentions the name on
    # purpose, so match the qualified `sa_exc.IntegrityError` a real except
    # would use, not the bare word).
    assert "sa_exc.IntegrityError" not in _NORM, (
        "commit retry must NOT catch sa_exc.IntegrityError (deterministic — masks a bug)."
    )
    assert "sa_exc.ProgrammingError" not in _NORM


def test_commit_retry_emits_structlog_event() -> None:
    assert "session_card.commit_retry" in _NORM, (
        "operators must see commit retries in structlog (session_card.commit_retry)."
    )


# ── behavioural unit test of the helper ───────────────────────────────


class _FakeSession:
    def __init__(self, commit_plan: list[Exception | None]) -> None:
        self._plan = commit_plan
        self.adds = 0
        self.commits = 0
        self.rollbacks = 0

    def add(self, _row: object) -> None:
        self.adds += 1

    async def commit(self) -> None:
        self.commits += 1
        exc = self._plan.pop(0)
        if exc is not None:
            raise exc

    async def rollback(self) -> None:
        self.rollbacks += 1


class _Row:
    id = "card-1"


def _op_err(msg: str) -> sa_exc.OperationalError:
    return sa_exc.OperationalError("UPDATE ...", {}, Exception(msg))


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    import ichor_api.cli.run_session_card as mod

    async def _fast(_delay: float) -> None:
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _fast)


@pytest.mark.asyncio
async def test_commit_succeeds_on_first_attempt() -> None:
    s = _FakeSession([None])
    await _commit_with_retry(s, _Row())
    assert s.commits == 1
    assert s.adds == 1
    assert s.rollbacks == 0


@pytest.mark.asyncio
async def test_commit_retries_transient_then_succeeds() -> None:
    s = _FakeSession([_op_err("conn reset"), _op_err("conn reset"), None])
    await _commit_with_retry(s, _Row())
    assert s.commits == 3  # 2 transient failures + 1 success
    assert s.rollbacks == 2  # rolled back between each failed attempt
    assert s.adds == 3  # row re-added each attempt (rollback expunged it)


@pytest.mark.asyncio
async def test_commit_reraises_after_exhausting_attempts() -> None:
    # (0.0,) + (0.5, 2.0, 5.0) = 4 attempts ; all fail → re-raise.
    s = _FakeSession([_op_err("db down")] * 4)
    with pytest.raises(sa_exc.OperationalError):
        await _commit_with_retry(s, _Row())
    assert s.commits == 4
    assert s.rollbacks == 4


@pytest.mark.asyncio
async def test_commit_does_not_retry_integrity_error() -> None:
    err = sa_exc.IntegrityError("INSERT ...", {}, Exception("duplicate key"))
    s = _FakeSession([err])
    with pytest.raises(sa_exc.IntegrityError):
        await _commit_with_retry(s, _Row())
    assert s.commits == 1  # NOT retried (deterministic)
    assert s.rollbacks == 0  # IntegrityError isn't caught by our handler
