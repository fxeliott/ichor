"""Langfuse `@observe` shim for the Couche-2 agents package.

Mirror of `ichor_brain.observability` — same fail-soft contract, but
duplicated here so `packages/agents` stays installable without a hard
dependency on `packages/ichor_brain` (the Critic gate is the only
cross-package import today, and it is lazy).

When `langfuse>=4.0.0` is present, decorated functions emit real
spans/generations to the self-hosted Langfuse instance. Otherwise, the
decorator is a no-op.

Three usage patterns transparently supported (SDK v4 API parity):
    @observe                  -> bare decorator
    @observe()                -> factory call
    @observe(name="x", ...)   -> factory with kwargs (name, as_type)

See ADR-032 (Langfuse @observe wiring) for the global rationale.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


try:
    from langfuse import observe  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — exercised only when langfuse absent

    def observe(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def _decorator(fn: F) -> F:
            return fn

        return _decorator


__all__ = ["observe"]
