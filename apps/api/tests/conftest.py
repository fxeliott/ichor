"""pytest fixtures + environment setup for apps/api tests.

The app's `Settings` model defaults `environment="production"` and the
`@model_validator` raises if `ICHOR_API_CLAUDE_RUNNER_URL` is empty in
production (this is a security guard — Couche-2 routing must explicitly
target a known URL, not fall back silently).

For tests, we flip the environment to `development` BEFORE any module
imports the app, so the validator passes without forcing every test
file to set env vars itself.
"""

from __future__ import annotations

import os

# IMPORTANT : these must run AT IMPORT TIME, before any other module
# imports the FastAPI app or the Settings singleton. pytest collects
# this file before any test file in the same directory.
os.environ.setdefault("ICHOR_API_ENVIRONMENT", "development")
os.environ.setdefault("ICHOR_API_CLAUDE_RUNNER_URL", "http://localhost:9999")
# pydantic-settings parses list[str] as JSON when given via env var.
os.environ.setdefault(
    "ICHOR_API_CORS_ORIGINS",
    '["http://localhost:3000", "http://localhost:3001"]',
)
# DB + Redis URLs only need to be valid-looking ; tests don't actually
# connect (smoke tests use ASGITransport with the FastAPI app instance).
os.environ.setdefault(
    "ICHOR_API_DATABASE_URL",
    "postgresql+asyncpg://ichor:test@localhost:5432/ichor_test",
)
os.environ.setdefault("ICHOR_API_REDIS_URL", "redis://localhost:6379/0")
# CF Access headers — empty in test, validator should accept them
# because `environment=development` relaxes the check.
os.environ.setdefault("ICHOR_API_CF_ACCESS_CLIENT_ID", "test-client-id")
os.environ.setdefault("ICHOR_API_CF_ACCESS_CLIENT_SECRET", "test-client-secret")


# ── DB stub for smoke tests ─────────────────────────────────────────
# `test_routers_smoke.py` and `test_new_routers_smoke.py` instantiate
# the FastAPI app and hit each route via ASGITransport. Without a real
# Postgres+Redis, asyncpg.InvalidPasswordError escapes the route and
# bubbles to pytest. The fix : override `get_session` so every DB-bound
# route gets a session that raises HTTPException(503) on first execute().
# This lets the existing `(200, 503)` expected-status assertions pass
# cleanly in CI / local-without-DB.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _override_db_session_for_smoke_tests() -> None:
    """Override get_session in the FastAPI dependency graph so smoke
    tests don't actually try to open a Postgres connection.

    Lazy : only takes effect when the FastAPI app is imported (which
    most smoke tests do at module-load). Other tests that don't import
    the app are unaffected.
    """
    try:
        from fastapi import HTTPException
        from ichor_api.db import get_session
        from ichor_api.main import app
    except Exception:
        # apps/api may not be importable in some test contexts ;
        # let those tests fail naturally with their own error.
        return

    async def _stub_session():
        # Yield a session-like object whose every method raises 503.
        class _Stub:
            async def execute(self, *a, **kw):
                raise HTTPException(status_code=503, detail="DB not available in test")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def close(self) -> None:
                return None

            def add(self, _row) -> None:
                return None

            async def flush(self) -> None:
                return None

            async def commit(self) -> None:
                return None

            async def rollback(self) -> None:
                return None

            async def get(self, *a, **kw):
                return None

            def add_all(self, _rows) -> None:
                return None

        yield _Stub()

    app.dependency_overrides[get_session] = _stub_session
