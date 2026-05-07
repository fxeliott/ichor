"""GET + POST /v1/journal — Eliot's private trader journal (Phase B.5d v2).

Backed by the `trader_notes` table (migration 0029). Out of ADR-017
boundary surface — pure trader notebook, never fed to ML/Brier.

Why this lives in a router rather than a localStorage-only feature:
  - Cross-device access (the laptop + the box at home + a future
    mobile dashboard would all need to see the same entries).
  - Server-side ordering by `ts` is authoritative (clocks drift on
    devices).
  - Future: cross-link to session_card_audit by asset+session for
    automatic linking (deferred to Phase B.5d v3).

Auth model: single-user, no auth header — if/when Ichor opens to a
small inner circle, this router will gate behind a service-token
header (same pattern as ichor_runner). Until then the boundary is
the Cloudflare Tunnel + IP allowlist.

`asset` is optional. When supplied it must match `^[A-Z0-9_]{3,16}$`.

`body` cap: 10 000 chars. Anything longer is almost certainly a
copy-paste accident; cap loudly via 422 rather than silently truncate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.trader_note import TraderNote

router = APIRouter(prefix="/v1/journal", tags=["journal"])

ASSET_PATTERN = r"^[A-Z0-9_]{3,16}$"


class JournalEntryCreate(BaseModel):
    """Inbound entry. `ts` defaults to now() server-side if absent."""

    body: str = Field(min_length=1, max_length=10_000)
    asset: str | None = Field(default=None, pattern=ASSET_PATTERN)
    ts: datetime | None = None


class JournalEntryOut(BaseModel):
    id: UUID
    ts: datetime
    asset: str | None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JournalListOut(BaseModel):
    total: int
    entries: list[JournalEntryOut]


@router.get("", response_model=JournalListOut)
async def list_entries(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: Annotated[str | None, Query(pattern=ASSET_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> JournalListOut:
    """List the most recent journal entries, optionally filtered by asset.

    Ordered by `ts DESC` (most recent first). Default cap 30, max 100.
    """
    stmt = select(TraderNote).order_by(desc(TraderNote.ts)).limit(limit)
    if asset is not None:
        stmt = stmt.where(TraderNote.asset == asset)

    rows = (await session.execute(stmt)).scalars().all()
    return JournalListOut(
        total=len(rows),
        entries=[JournalEntryOut.model_validate(r) for r in rows],
    )


@router.post("", response_model=JournalEntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: JournalEntryCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JournalEntryOut:
    """Append a new journal entry.

    Insertion is unconditional (no idempotency key) — duplicate posts
    will produce duplicate entries. The web client is responsible for
    debouncing the save button.
    """
    now = datetime.now(UTC)
    note = TraderNote(
        ts=payload.ts or now,
        asset=payload.asset,
        body=payload.body,
        created_at=now,
    )
    session.add(note)
    try:
        await session.commit()
    except Exception as exc:  # pragma: no cover — DB-level failure
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"trader_notes insert failed: {exc}",
        )
    await session.refresh(note)
    return JournalEntryOut.model_validate(note)


@router.delete(
    "/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=None
)
async def delete_entry(
    entry_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete one journal entry.

    Trader-controlled — unlike `audit_log` (immutable, append-only via
    migration 0028 trigger), `trader_notes` is editable since it's
    Eliot's personal space, not a compliance artifact.
    """
    obj = await session.get(TraderNote, entry_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entry {entry_id} not found",
        )
    await session.delete(obj)
    await session.commit()
