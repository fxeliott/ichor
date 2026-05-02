"""Pydantic schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ichor_claude_runner.models import BriefingTaskRequest


def test_briefing_request_accepts_typical_payload() -> None:
    req = BriefingTaskRequest(
        briefing_type="pre_londres",
        assets=["EUR_USD", "XAU_USD"],
        context_markdown="# Context\n...",
    )
    assert req.model == "opus"
    assert req.max_tokens_out == 4_000


def test_briefing_request_rejects_empty_assets() -> None:
    with pytest.raises(ValidationError):
        BriefingTaskRequest(
            briefing_type="pre_ny",
            assets=[],
            context_markdown="x",
        )


def test_briefing_request_rejects_too_many_assets() -> None:
    with pytest.raises(ValidationError):
        BriefingTaskRequest(
            briefing_type="ny_close",
            assets=["A"] * 9,
            context_markdown="x",
        )


def test_briefing_request_clamps_max_tokens_range() -> None:
    with pytest.raises(ValidationError):
        BriefingTaskRequest(
            briefing_type="ny_mid",
            assets=["EUR_USD"],
            context_markdown="x",
            max_tokens_out=99,  # below min 100
        )


def test_briefing_request_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        BriefingTaskRequest(
            briefing_type="weekly",
            assets=["EUR_USD"],
            context_markdown="x",
            temperature=1.5,
        )
