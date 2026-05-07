"""Tests for the Couche-2 Langfuse @observe shim (ADR-032).

Mirror of `ichor_brain.tests.test_observability` — verifies the
fail-soft no-op path so the agents package stays installable without
the optional `[observability]` extra.
"""

from __future__ import annotations

import asyncio

import pytest

from ichor_agents.observability import observe


def test_bare_decorator_returns_function() -> None:
    @observe
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_factory_decorator_returns_function() -> None:
    @observe()
    def double(x: int) -> int:
        return x * 2

    assert double(7) == 14


def test_factory_with_kwargs_returns_function() -> None:
    @observe(name="couche2_test", as_type="generation")
    def sub(a: int, b: int) -> int:
        return a - b

    assert sub(10, 4) == 6


@pytest.mark.asyncio
async def test_async_function_decoration_preserves_coroutine() -> None:
    @observe(name="async_couche2_test")
    async def fetch(value: str) -> str:
        await asyncio.sleep(0)
        return f"got:{value}"

    assert await fetch("eur_usd") == "got:eur_usd"


def test_decorator_does_not_swallow_exceptions() -> None:
    @observe(name="raises")
    def boom() -> None:
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        boom()
