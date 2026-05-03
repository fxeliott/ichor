"""Pydantic API schemas — request/response shapes (separate from ORM models)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BriefingOut(BaseModel):
    id: UUID
    briefing_type: str
    triggered_at: datetime
    assets: list[str]
    status: str
    briefing_markdown: str | None
    claude_duration_ms: int | None
    audio_mp3_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BriefingListOut(BaseModel):
    total: int
    items: list[BriefingOut]


class AlertOut(BaseModel):
    id: UUID
    alert_code: str
    severity: Literal["info", "warning", "critical"]
    asset: str | None
    triggered_at: datetime
    metric_name: str
    metric_value: float
    threshold: float
    direction: Literal["above", "below", "cross_up", "cross_down"]
    title: str
    description: str | None
    acknowledged_at: datetime | None

    model_config = {"from_attributes": True}


class BiasSignalOut(BaseModel):
    id: UUID
    asset: str
    horizon_hours: int
    direction: Literal["long", "short", "neutral"]
    probability: float = Field(ge=0.0, le=1.0)
    credible_interval_low: float
    credible_interval_high: float
    contributing_predictions: list[UUID]
    weights_snapshot: dict[str, float]
    generated_at: datetime

    model_config = {"from_attributes": True}


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    db_connected: bool
    redis_connected: bool
    claude_runner_reachable: bool | None = None  # tested only when explicitly asked


class CollectorLag(BaseModel):
    source: str
    last_fetched_at: datetime | None
    minutes_stale: float | None


class HealthDetailedOut(HealthOut):
    """Extended /healthz/detailed — used by Grafana + RUNBOOK-011."""

    last_briefing_at: datetime | None
    minutes_since_last_briefing: float | None
    unack_alerts_critical: int
    unack_alerts_warning: int
    collectors: list[CollectorLag]
