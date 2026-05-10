"""Tests for the Langfuse @observe shim (ADR-032, Phase A.4.c).

These tests verify the **fail-soft no-op** path — i.e. the package
must remain functional when `langfuse` is not installed. The CI env
typically does not install the optional `[observability]` extra, so
these tests exercise the production-relevant fallback.

When `langfuse` IS installed in the env, the import in
`ichor_brain.observability` succeeds and `observe` is the real
decorator; the test still passes because real `@observe` also
preserves function semantics (with the side effect of emitting a
trace, which is fine to drop on the floor in a unit test).
"""

from __future__ import annotations

import asyncio

import pytest
from ichor_brain.observability import observe


def test_bare_decorator_returns_function() -> None:
    """`@observe` without parens — args[0] is the function."""

    @observe
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_factory_decorator_returns_function() -> None:
    """`@observe()` — factory call returning a no-op decorator."""

    @observe()
    def double(x: int) -> int:
        return x * 2

    assert double(7) == 14


def test_factory_with_kwargs_returns_function() -> None:
    """`@observe(name="x", as_type="generation")` — common production form."""

    @observe(name="test_trace", as_type="generation")
    def sub(a: int, b: int) -> int:
        return a - b

    assert sub(10, 4) == 6


@pytest.mark.asyncio
async def test_async_function_decoration_preserves_coroutine() -> None:
    """Coroutines must survive decoration intact (4-pass passes are async)."""

    @observe(name="async_test")
    async def fetch(value: str) -> str:
        await asyncio.sleep(0)
        return f"got:{value}"

    result = await fetch("eur_usd")
    assert result == "got:eur_usd"


def test_decorator_does_not_swallow_exceptions() -> None:
    """A decorated function that raises must still raise — failures must
    not be silently observed away."""

    @observe(name="raises")
    def boom() -> None:
        raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        boom()
