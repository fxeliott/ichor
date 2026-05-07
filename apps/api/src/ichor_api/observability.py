"""Langfuse client lifecycle for the FastAPI app (Phase A.4.c, ADR-032).

Owns three concerns:

1. **Init at startup** — read `langfuse_public_key` / `langfuse_secret_key`
   / `langfuse_host` from settings (cf `config.py:115-117`), construct
   the singleton `Langfuse` client, expose it via `get_langfuse_client()`.

2. **Flush at shutdown** — best-practice for short-lived FastAPI processes:
   `langfuse.flush()` blocks until the worker thread drains its queue. Without
   this, the last few traces may be lost if the API receives SIGTERM
   right after a 4-pass run finishes (the worker thread is daemonic).

3. **Fail-soft** — if `langfuse` is not installed (uv extras not selected,
   or local dev shell), or if the public/secret keys are blank
   (default), the helpers no-op. The API still boots, the `@observe`
   decorators still no-op via the package-local shims
   (`ichor_brain.observability` + `ichor_agents.observability`).

Wire contract on Hetzner:
    /etc/ichor/api.env should contain
        ICHOR_API_LANGFUSE_PUBLIC_KEY=pk-lf-...
        ICHOR_API_LANGFUSE_SECRET_KEY=sk-lf-...
        ICHOR_API_LANGFUSE_HOST=http://127.0.0.1:3000
    These already exist as settings fields (`config.py:115-117`),
    populated when the langfuse Ansible role provisions the docker stack.
"""

from __future__ import annotations

from typing import Any

import structlog

from .config import get_settings

log = structlog.get_logger(__name__)

_langfuse_client: Any = None
"""Module-level singleton. None means: not initialised, OR langfuse not
installed, OR keys not configured. Callers MUST treat None as the
'tracing disabled' state and not raise."""


def init_langfuse() -> Any:
    """Construct the Langfuse client if config + lib are present.

    Idempotent: subsequent calls return the same singleton. Returns None
    if langfuse is not installed or the public/secret keys are blank.
    Boot-safe: any exception path is logged and swallowed — the API
    must keep starting even if observability misconfigures.
    """
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    settings = get_settings()
    pk = (settings.langfuse_public_key or "").strip()
    sk = (settings.langfuse_secret_key or "").strip()
    host = (settings.langfuse_host or "").strip()

    if not pk or not sk:
        log.info("api.langfuse_disabled_no_keys")
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
    except ImportError:
        log.info("api.langfuse_disabled_lib_missing")
        return None

    try:
        _langfuse_client = Langfuse(
            public_key=pk,
            secret_key=sk,
            host=host or "http://127.0.0.1:3000",
        )
        log.info("api.langfuse_enabled", host=host)
        return _langfuse_client
    except Exception as exc:  # pragma: no cover — fail-soft observability
        log.warning("api.langfuse_init_failed", error=str(exc)[:200])
        _langfuse_client = None
        return None


def flush_langfuse() -> None:
    """Drain the worker queue. Called at FastAPI shutdown.

    No-op when the client was never initialised. Exceptions are
    swallowed — shutdown must not block on observability flakes.
    """
    global _langfuse_client
    if _langfuse_client is None:
        return
    try:
        _langfuse_client.flush()
        log.info("api.langfuse_flushed")
    except Exception as exc:  # pragma: no cover — fail-soft observability
        log.warning("api.langfuse_flush_failed", error=str(exc)[:200])


def get_langfuse_client() -> Any:
    """Accessor for code that wants to score traces / add custom spans.

    Returns the singleton if init succeeded, None otherwise. Callers
    must check for None before calling client methods.
    """
    return _langfuse_client


__all__ = ["flush_langfuse", "get_langfuse_client", "init_langfuse"]
