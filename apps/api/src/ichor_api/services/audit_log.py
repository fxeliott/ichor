"""Audit log — append-only trail for sensitive actions.

Per HARDENING §1 + §7. Backed by table `audit_log` (migration 0017).
The middleware logs every state-changing HTTP request (POST/PUT/PATCH/DELETE)
with actor + action + resource + request_id + ip + meta.

Retention: 365 days, purged nightly by `scripts/hetzner/audit_log_purge.sh`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AuditEntry:
    actor: str
    action: str
    resource: str | None = None
    request_id: uuid.UUID | None = None
    ip: str | None = None
    meta: dict[str, Any] | None = None


async def write_entry(session: AsyncSession, entry: AuditEntry) -> int:
    """Insert one audit row. Returns the new id."""
    row = (
        await session.execute(
            text(
                """
            INSERT INTO audit_log
                (ts, actor, action, resource, request_id, ip, meta)
            VALUES
                (:ts, :actor, :action, :resource, :rid, CAST(:ip AS inet), CAST(:meta AS jsonb))
            RETURNING id
            """
            ),
            {
                "ts": datetime.now(UTC),
                "actor": entry.actor,
                "action": entry.action,
                "resource": entry.resource,
                "rid": str(entry.request_id) if entry.request_id else None,
                "ip": entry.ip,
                "meta": json.dumps(entry.meta) if entry.meta else None,
            },
        )
    ).scalar_one()
    return int(row)


async def recent(
    session: AsyncSession, *, limit: int = 100, actor: str | None = None
) -> list[dict[str, Any]]:
    """Read recent entries, optionally filtered by actor."""
    where = "WHERE actor = :actor" if actor else ""
    params: dict[str, Any] = {"limit": min(max(1, limit), 1000)}
    if actor:
        params["actor"] = actor
    rows = (
        (
            await session.execute(
                text(
                    f"""
            SELECT id, ts, actor, action, resource, request_id, ip, meta
            FROM audit_log
            {where}
            ORDER BY ts DESC
            LIMIT :limit
            """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def purge_older_than(session: AsyncSession, *, days: int = 365) -> int:
    """Hard-delete rows older than `days`. Cron-friendly. Returns deleted count."""
    res = await session.execute(
        text("DELETE FROM audit_log WHERE ts < (now() - make_interval(days => :d))"),
        {"d": int(days)},
    )
    return int(res.rowcount or 0)


# ─── Optional FastAPI middleware ──────────────────────────────────────
# Plug into apps/api/src/ichor_api/main.py via:
#   from .services.audit_log import AuditLogMiddleware
#   app.add_middleware(AuditLogMiddleware, get_session=get_session)
#
# We log at "best-effort" granularity — missing entries don't block the
# response (DB unavailable shouldn't kill the API).


class AuditLogMiddleware:
    """ASGI middleware that records POST/PUT/PATCH/DELETE on /v1/* paths.

    Skips: GET, HEAD, OPTIONS, /healthz*, /metrics, static assets.
    """

    SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}
    SKIP_PATHS = ("/healthz", "/livez", "/readyz", "/startupz", "/metrics", "/openapi.json")

    def __init__(self, app, get_session=None) -> None:
        self.app = app
        self._get_session = get_session

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        path = scope.get("path", "") or ""
        if method in self.SKIP_METHODS or any(path.startswith(p) for p in self.SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4()
        client = scope.get("client") or (None, None)
        ip = client[0] if client else None
        # Actor: read X-Actor or X-User from headers (auth not yet wired).
        headers = {
            (k.decode() if isinstance(k, bytes) else k).lower(): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in scope.get("headers") or []
        }
        actor = headers.get("x-actor") or headers.get("x-user") or "anonymous"

        # Inject request_id header into the response so callers can correlate.
        # Per ASGI 3.0 spec, do not mutate the message dict in place — emit
        # a new dict so upstream stacks that recycle messages are not affected.
        async def _send_wrap(message):
            if message.get("type") == "http.response.start":
                new_message = dict(message)
                new_message["headers"] = [
                    *list(message.get("headers", [])),
                    (b"x-request-id", str(request_id).encode("utf-8")),
                ]
                await send(new_message)
                return
            await send(message)

        await self.app(scope, receive, _send_wrap)

        # Best-effort write. If get_session is None (test mode) or DB
        # unavailable, swallow + log at debug level.
        if self._get_session is None:
            return
        try:
            async for sess in self._get_session():
                await write_entry(
                    sess,
                    AuditEntry(
                        actor=actor,
                        action=f"{method} {path}",
                        resource=path,
                        request_id=request_id,
                        ip=ip,
                        meta=None,
                    ),
                )
                await sess.commit()
                break
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug(
                "audit_log.write_failed actor=%s action=%s err=%s",
                actor,
                f"{method} {path}",
                exc,
            )
