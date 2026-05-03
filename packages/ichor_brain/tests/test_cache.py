"""Cache-key derivation tests."""

from __future__ import annotations

from ichor_brain.cache import (
    asset_data_cache_ttl,
    framework_cache_ttl,
    hash_pool,
)


def test_ttl_constants_match_doctrine() -> None:
    assert framework_cache_ttl() == 3600
    assert asset_data_cache_ttl() == 300


def test_hash_pool_is_deterministic() -> None:
    a = hash_pool("foo", "bar")
    b = hash_pool("foo", "bar")
    assert a == b


def test_hash_pool_separator_prevents_collision() -> None:
    """('foo', 'bar') must not hash the same as ('foob', 'ar')."""
    assert hash_pool("foo", "bar") != hash_pool("foob", "ar")


def test_hash_pool_handles_empty() -> None:
    assert hash_pool() != hash_pool("")
    assert len(hash_pool("anything")) == 64
