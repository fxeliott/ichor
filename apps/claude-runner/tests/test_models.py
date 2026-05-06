"""Pydantic schema validation."""

from __future__ import annotations

import pytest
from ichor_claude_runner.models import AgentTaskRequest, BriefingTaskRequest
from pydantic import ValidationError


def test_briefing_request_accepts_typical_payload() -> None:
    req = BriefingTaskRequest(
        briefing_type="pre_londres",
        assets=["EUR_USD", "XAU_USD"],
        context_markdown="# Context\n...",
    )
    assert req.model == "opus"
    assert req.effort == "medium"


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


def test_briefing_request_rejects_invalid_effort() -> None:
    with pytest.raises(ValidationError):
        BriefingTaskRequest(
            briefing_type="ny_mid",
            assets=["EUR_USD"],
            context_markdown="x",
            effort="ultra",  # not in Literal set
        )


def test_briefing_request_accepts_all_effort_levels() -> None:
    for effort in ["low", "medium", "high", "xhigh", "max"]:
        req = BriefingTaskRequest(
            briefing_type="weekly",
            assets=["EUR_USD"],
            context_markdown="x",
            effort=effort,
        )
        assert req.effort == effort


# ── AgentTaskRequest (ADR-021) ─────────────────────────────────────


def test_agent_task_request_defaults() -> None:
    req = AgentTaskRequest(system="some system prompt", prompt="some user prompt")
    assert req.model == "sonnet"
    assert req.effort == "medium"
    assert req.task_id is not None


def test_agent_task_request_rejects_empty_system() -> None:
    with pytest.raises(ValidationError):
        AgentTaskRequest(system="", prompt="x")


def test_agent_task_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        AgentTaskRequest(system="x", prompt="")


def test_agent_task_request_rejects_bad_model() -> None:
    with pytest.raises(ValidationError):
        AgentTaskRequest(system="s", prompt="p", model="gpt-5")  # type: ignore[arg-type]


def test_agent_task_request_accepts_all_models() -> None:
    for m in ["opus", "sonnet", "haiku"]:
        req = AgentTaskRequest(system="s", prompt="p", model=m)  # type: ignore[arg-type]
        assert req.model == m
