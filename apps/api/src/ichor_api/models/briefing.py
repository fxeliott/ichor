"""briefings table — one row per cron-triggered briefing run."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Briefing(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "briefings"

    # Cron metadata
    briefing_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """One of: pre_londres, pre_ny, ny_mid, ny_close, weekly, crisis"""

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    """When the cron fired (Europe/Paris timezone preserved)."""

    # Scope
    assets: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False)

    # Pipeline state
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    """pending → context_assembled → claude_running → completed | failed"""

    # Inputs
    context_markdown: Mapped[str | None] = mapped_column(Text)
    context_token_estimate: Mapped[int | None] = mapped_column(Integer)

    # Claude subprocess output
    claude_runner_task_id: Mapped[UUID | None] = mapped_column()
    briefing_markdown: Mapped[str | None] = mapped_column(Text)
    claude_raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    claude_duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Audio (Phase 0 W4)
    audio_mp3_url: Mapped[str | None] = mapped_column(String(512))
    """R2 URL of the synthesized briefing audio (when available)."""

    # Failure
    error_message: Mapped[str | None] = mapped_column(Text)
