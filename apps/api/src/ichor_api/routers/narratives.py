"""GET /v1/narratives — top keywords from cb_speeches + news.

Powers the `/narratives` Next.js page. The data underlying the
narrative tracker is the same pool the brain Pass 1 régime call sees,
so this route is also useful as a debug aid : "what is Claude looking
at right now?"

VISION_2026 delta J — narrative tracker frontend.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.narrative_tracker import track_narratives

router = APIRouter(prefix="/v1/narratives", tags=["narratives"])


class TopicOut(BaseModel):
    keyword: str
    count: int
    share: float
    sample_title: str | None = None


class NarrativeOut(BaseModel):
    window_hours: int
    n_documents: int
    n_tokens: int
    topics: list[TopicOut]


@router.get("", response_model=NarrativeOut)
async def get_narratives(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(48, ge=1, le=336),
    top_k: int = Query(20, ge=1, le=100),
) -> NarrativeOut:
    report = await track_narratives(session, window_hours=hours, top_k=top_k)
    return NarrativeOut(
        window_hours=report.window_hours,
        n_documents=report.n_documents,
        n_tokens=report.n_tokens,
        topics=[
            TopicOut(
                keyword=t.keyword,
                count=t.count,
                share=t.share,
                sample_title=t.sample_titles[0] if t.sample_titles else None,
            )
            for t in report.topics
        ],
    )
