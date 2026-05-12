"""Phase D W116 — pass3_addendum_injector unit tests.

Pure-Python score helper tests + signature-validation tests on the
record_new_addendum / select_active_addenda helpers. DB-side
selection logic is covered by integration tests separately.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from ichor_api.services.pass3_addendum_injector import (
    DEFAULT_DECAY_HALFLIFE_DAYS,
    DEFAULT_MAX_ACTIVE_PER_REGIME,
    DEFAULT_TTL_DAYS,
    _effective_score,
    record_new_addendum,
    select_active_addenda,
)

# ────────────────────────── _effective_score ──────────────────────────


def test_effective_score_zero_age_returns_importance() -> None:
    """`age = 0` → score = importance · 2^0 = importance."""
    now = datetime.now(UTC)
    score = _effective_score(importance=1.5, created_at=now, now=now, halflife_days=30.0)
    assert math.isclose(score, 1.5, abs_tol=1e-12)


def test_effective_score_halves_at_halflife() -> None:
    """`age = halflife` → score = importance / 2."""
    halflife = 30.0
    now = datetime.now(UTC)
    created = now - timedelta(days=halflife)
    score = _effective_score(importance=4.0, created_at=created, now=now, halflife_days=halflife)
    assert math.isclose(score, 2.0, abs_tol=1e-9)


def test_effective_score_one_quarter_at_two_halflives() -> None:
    """`age = 2·halflife` → score = importance / 4."""
    halflife = 15.0
    now = datetime.now(UTC)
    created = now - timedelta(days=30.0)
    score = _effective_score(importance=8.0, created_at=created, now=now, halflife_days=halflife)
    assert math.isclose(score, 2.0, abs_tol=1e-9)


def test_effective_score_zero_halflife_is_no_decay() -> None:
    """`halflife = 0` (degenerate) → score = importance, no decay."""
    now = datetime.now(UTC)
    created = now - timedelta(days=365)
    score = _effective_score(importance=3.0, created_at=created, now=now, halflife_days=0.0)
    assert math.isclose(score, 3.0, abs_tol=1e-12)


def test_effective_score_negative_age_clamps_to_zero() -> None:
    """Future `created_at` (clock skew edge case) → no future-amplification.
    Clamp age to 0 so score == importance."""
    now = datetime.now(UTC)
    created = now + timedelta(hours=1)  # 1h in the future
    score = _effective_score(importance=2.0, created_at=created, now=now, halflife_days=30.0)
    assert math.isclose(score, 2.0, abs_tol=1e-12)


# ────────────────────────── defaults ──────────────────────────


def test_default_max_active_per_regime_is_three() -> None:
    """Researcher SOTA brief : max 3 active addenda per regime."""
    assert DEFAULT_MAX_ACTIVE_PER_REGIME == 3


def test_default_decay_halflife_is_thirty_days() -> None:
    """Researcher SOTA brief : exp decay half-life 30 d."""
    assert DEFAULT_DECAY_HALFLIFE_DAYS == 30.0


def test_default_ttl_is_ninety_days() -> None:
    """Researcher SOTA brief : 90 d hard TTL."""
    assert DEFAULT_TTL_DAYS == 90.0


# ────────────────────────── select_active_addenda validation ──────────────────────────


@pytest.mark.asyncio
async def test_select_active_returns_empty_on_zero_max() -> None:
    """`max_active=0` short-circuits without touching the DB."""

    # Pass a sentinel that would crash on any session call.
    class _Boom:
        async def execute(self, *_a, **_k):  # type: ignore[no-untyped-def]
            raise AssertionError("DB must NOT be touched when max_active=0")

    result = await select_active_addenda(
        _Boom(),  # type: ignore[arg-type]
        regime="usd_complacency",
        max_active=0,
    )
    assert result == []


@pytest.mark.asyncio
async def test_select_active_rejects_negative_max() -> None:
    class _Stub:
        pass

    with pytest.raises(ValueError, match=r"max_active must be"):
        await select_active_addenda(_Stub(), regime="x", max_active=-1)  # type: ignore[arg-type]


# ────────────────────────── record_new_addendum validation ──────────────────────────


@pytest.mark.asyncio
async def test_record_rejects_zero_ttl() -> None:
    class _Stub:
        pass

    with pytest.raises(ValueError, match=r"ttl_days must be > 0"):
        await record_new_addendum(
            _Stub(),  # type: ignore[arg-type]
            regime="x",
            content="some valid content here",
            importance=0.5,
            ttl_days=0.0,
        )


@pytest.mark.asyncio
async def test_record_rejects_negative_importance() -> None:
    class _Stub:
        pass

    with pytest.raises(ValueError, match=r"importance must be"):
        await record_new_addendum(
            _Stub(),  # type: ignore[arg-type]
            regime="x",
            content="some valid content here",
            importance=-0.1,
        )


@pytest.mark.asyncio
async def test_record_rejects_content_too_short() -> None:
    """`char_length(content) >= 8` matches the DB CHECK constraint —
    we fail-fast in Python before round-trip."""

    class _Stub:
        pass

    with pytest.raises(ValueError, match=r"content length"):
        await record_new_addendum(
            _Stub(),  # type: ignore[arg-type]
            regime="x",
            content="short",  # 5 chars < 8
            importance=0.5,
        )


@pytest.mark.asyncio
async def test_record_rejects_content_too_long() -> None:
    """`char_length(content) <= 4096`."""

    class _Stub:
        pass

    with pytest.raises(ValueError, match=r"content length"):
        await record_new_addendum(
            _Stub(),  # type: ignore[arg-type]
            regime="x",
            content="x" * 4097,
            importance=0.5,
        )
