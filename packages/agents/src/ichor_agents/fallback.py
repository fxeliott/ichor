"""Failover chain: try providers in order, log + continue on transient errors,
short-circuit on auth errors (which won't recover by retry).

Used by the 5 Couche-2 agents (Macro, Sentiment, Positioning, CB-NLP, News-NLP).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UserError

from .providers import ProviderConfig, build_model, MissingCredentials

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
    """Order matters: first = primary, last = last resort."""

    system_prompt: str
    output_type: type | None = None  # Pydantic AI structured output type if any

    async def run(
        self,
        user_prompt: str,
        *,
        run_kwargs: dict | None = None,
    ) -> str | T:
        """Try each provider in order until one returns successfully.

        Returns the agent output (str or structured Pydantic model).
        Raises AllProvidersFailed if every provider errors.
        """
        attempts: list[tuple[str, Exception]] = []

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
