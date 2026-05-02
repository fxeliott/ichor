"""Unit tests for the in-memory rate limiter."""

from __future__ import annotations

from ichor_claude_runner.rate_limiter import HourlyRateLimiter


def test_accepts_up_to_max() -> None:
    rl = HourlyRateLimiter(max_per_hour=3)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is False  # 4th in same hour rejected


def test_remaining_decreases() -> None:
    rl = HourlyRateLimiter(max_per_hour=5)
    assert rl.remaining() == 5
    rl.try_acquire()
    rl.try_acquire()
    assert rl.remaining() == 3
    assert rl.current_count() == 2


def test_zero_max_rejects_all() -> None:
    rl = HourlyRateLimiter(max_per_hour=0)
    assert rl.try_acquire() is False
    assert rl.remaining() == 0
