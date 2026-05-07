"""Langfuse `@observe` shim — fail-soft.

When `langfuse>=4.0.0` is installed in the runtime environment (Hetzner
prod), `observe` is the real Langfuse decorator and traces are sent to
the self-hosted Langfuse v3 instance (cf `infra/ansible/roles/langfuse/`).

When langfuse is NOT installed (CI, unit tests, dev shells without the
optional dep), `observe` is a no-op decorator so the module stays
importable and decorated functions stay equivalent to their bare form.

This pattern keeps `packages/ichor_brain` framework-light: the package
ships without a hard dep on langfuse, and tracing is opted in at deploy
time via `pip install ichor-brain[observability]` or by installing
langfuse alongside.

Why a shim rather than a try/except at every import site:
- DRY — one fail-soft contract for the whole package.
- Static-type-checker-friendly: callers always see a `Callable`-like
  decorator regardless of langfuse install state.
- Three usage patterns transparently supported (matches the SDK v4 API):
    @observe                  -> bare decorator, args[0] is the function
    @observe()                -> factory call returning a decorator
    @observe(name="x", ...)   -> factory with kwargs (name, as_type, ...)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


try:
    from langfuse import observe  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — exercised only when langfuse absent

    def observe(*args: Any, **kwargs: Any) -> Any:
        # Bare-decorator form: @observe (no parens) → args[0] is the fn.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        # Factory form: @observe(...) returns a decorator.
        def _decorator(fn: F) -> F:
            return fn

        return _decorator


__all__ = ["observe"]
