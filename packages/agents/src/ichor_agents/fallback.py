"""Failover chain: try providers in order, log + continue on transient errors,
short-circuit on auth errors (which won't recover by retry).

Used by the 5 Couche-2 agents (Macro, Sentiment, Positioning, CB-NLP, News-NLP).

Per ADR-021, when `claude` is set on the chain, Claude (via the local
runner) is tried FIRST and Cerebras/Groq only fire as fallback. The
Claude path is a self-contained adapter (`claude_runner.call_agent_task`)
that bypasses Pydantic AI Agent because the runner shells out to
`claude -p` (Voie D) rather than speaking an OpenAI-compatible API.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeVar

import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UserError

from .claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunnerError,
    call_agent_task,
    call_agent_task_async,
)
from .observability import observe
from .providers import MissingCredentials, ProviderConfig, build_model

log = structlog.get_logger(__name__)

T = TypeVar("T")


class AllProvidersFailed(RuntimeError):
    """Every provider in the chain raised. last_error has the most recent."""

    def __init__(self, attempts: list[tuple[str, Exception]]) -> None:
        self.attempts = attempts
        super().__init__(
            "All providers failed: " + ", ".join(f"{p}={type(e).__name__}" for p, e in attempts)
        )


@dataclass
class FallbackChain:
    providers: Sequence[ProviderConfig]
    """Order matters: first = primary, last = last resort.
    When `claude` is set, Claude is tried before this list."""

    system_prompt: str
    output_type: type | None = None  # Pydantic AI structured output type if any

    claude: ClaudeRunnerConfig | None = None
    """ADR-021 primary brain. None = skip Claude path entirely (test
    mode, or runner not configured in this env)."""

    use_async_endpoint: bool = True
    """Wave 67 — when True, use /v1/agent-task/async + polling pattern
    (mirror ADR-053). Bypasses Cloudflare Tunnel 100s edge cap that
    intermittently 524s on cb_nlp/news_nlp big-prompt runs. Set False
    only for tests / legacy scenarios."""

    last_success: str | None = field(default=None, init=False, repr=False)
    """Provider:model string of whichever path returned successfully on
    the most recent run() call. Read this AFTER run() to log/persist
    accurate provenance. None when the chain has not yet succeeded."""

    @observe(name="couche2_chain")
    async def run(
        self,
        user_prompt: str,
        *,
        run_kwargs: dict | None = None,
    ) -> str | T:
        """Try Claude first (if configured), then each fallback provider
        in order until one returns successfully.

        Returns the agent output (str or structured Pydantic model).
        Raises AllProvidersFailed if every provider errors.
        """
        attempts: list[tuple[str, Exception]] = []
        self.last_success = None

        if self.claude is not None:
            try:
                # Wave 67 — async polling pattern by default (CF 100s fix)
                if self.use_async_endpoint:
                    result = await call_agent_task_async(
                        self.claude,
                        system=self.system_prompt,
                        prompt=user_prompt,
                        output_type=self.output_type,
                    )
                else:
                    result = await call_agent_task(
                        self.claude,
                        system=self.system_prompt,
                        prompt=user_prompt,
                        output_type=self.output_type,
                    )
                self.last_success = f"claude:{self.claude.model}"
                return result
            except ClaudeRunnerError as e:
                log.warning(
                    "agents.fallback.claude_failed",
                    error=str(e)[:300],
                    error_type=type(e).__name__,
                )
                attempts.append(("claude", e))

        for cfg in self.providers:
            try:
                model = build_model(cfg)
            except MissingCredentials as e:
                log.warning(
                    "agents.fallback.skip_no_creds",
                    provider=cfg.name,
                    model=cfg.default_model,
                )
                attempts.append((cfg.name, e))
                continue

            agent = Agent(
                model,
                output_type=self.output_type or str,
                system_prompt=self.system_prompt,
            )

            try:
                log.info(
                    "agents.fallback.try",
                    provider=cfg.name,
                    model=cfg.default_model,
                    prompt_len=len(user_prompt),
                )
                result = await agent.run(user_prompt, **(run_kwargs or {}))
                log.info(
                    "agents.fallback.ok",
                    provider=cfg.name,
                    model=cfg.default_model,
                    usage=result.usage().__dict__ if result.usage() else None,
                )
                self.last_success = f"{cfg.name}:{cfg.default_model}"
                return result.output

            except (ModelHTTPError, UserError) as e:
                # 5xx, rate limit, model error — try next provider
                log.warning(
                    "agents.fallback.error",
                    provider=cfg.name,
                    error=str(e)[:200],
                    error_type=type(e).__name__,
                )
                attempts.append((cfg.name, e))
                continue

        raise AllProvidersFailed(attempts)
