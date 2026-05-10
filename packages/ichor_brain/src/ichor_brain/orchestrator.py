"""4-pass orchestrator.

Sequence :
  régime → asset specialization → bull-case stress-test
        → invalidation conditions → Critic Agent gate → SessionCard

The Critic gate may flag the card with `verdict='blocked'`. The
orchestrator returns the card regardless; the persistence layer is
responsible for refusing to publish blocked cards externally (the row
is still written to `session_card_audit` for observability).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog

from .cache import hash_pool
from .observability import observe
from .passes import (
    AssetPass,
    InvalidationPass,
    Pass,
    RegimePass,
    StressPass,
)
from .runner_client import RunnerCall, RunnerClient, ToolConfig
from .types import (
    AssetSpecialization,
    CriticDecision,
    InvalidationConditions,
    RegimeReading,
    SessionCard,
    SessionType,
    StressTest,
)


class _CriticVerdictLike(Protocol):
    """Duck-typed shape returned by `ichor_agents.critic.reviewer.review_briefing`.

    Declared here so the orchestrator doesn't import `ichor_agents` at
    module level — the brain package stays installable and testable in
    environments where the agents package isn't present.
    """

    verdict: str
    confidence: float
    findings: list[Any]
    suggested_footer: str


CriticFn = Callable[..., _CriticVerdictLike]


def _default_critic_fn(
    *, briefing_markdown: str, source_pool: str, asset_whitelist: list[str]
) -> _CriticVerdictLike:
    """Lazy-import wrapper around the real Critic Agent."""
    from ichor_agents.critic.reviewer import review_briefing  # local import

    return review_briefing(
        briefing_markdown=briefing_markdown,
        source_pool=source_pool,
        asset_whitelist=asset_whitelist,
    )


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OrchestratorResult:
    """What the orchestrator returns to its caller."""

    card: SessionCard
    runner_calls: list[RunnerCall]


class Orchestrator:
    """Drives the 4 passes for a single (session_type, asset) tuple.

    Stateless across runs — instantiate once and call `run()` per
    session card you want to produce. Concurrency : the orchestrator
    serializes its own 4 calls, but multiple orchestrators may run in
    parallel for different assets (the runner client must be safe).
    """

    def __init__(
        self,
        runner: RunnerClient,
        *,
        regime_pass: Pass[RegimeReading] | None = None,
        asset_pass: Pass[AssetSpecialization] | None = None,
        stress_pass: Pass[StressTest] | None = None,
        invalidation_pass: Pass[InvalidationConditions] | None = None,
        critic_fn: CriticFn | None = None,
        model_id: str = "claude-opus-4-7",
        tool_config: ToolConfig | None = None,
    ):
        self._runner = runner
        self._regime = regime_pass or RegimePass()
        self._asset = asset_pass or AssetPass()
        self._stress = stress_pass or StressPass()
        self._invalidation = invalidation_pass or InvalidationPass()
        self._critic_fn = critic_fn or _default_critic_fn
        self._model_id = model_id
        self._tool_config = tool_config

    def _tool_fields_for(self, pass_kind: str) -> dict[str, Any]:
        """W87 STEP-5 — emit Capability 5 tool fields for a RunnerCall
        when the pass is in `tool_config.enabled_for_passes`. Returns
        `{}` (no fields, pre-W87 behaviour) otherwise.

        Pass kind strings : "regime", "asset", "stress", "invalidation".
        """
        if self._tool_config is None or pass_kind not in self._tool_config.enabled_for_passes:
            return {}
        return {
            "mcp_config": self._tool_config.mcp_config,
            "allowed_tools": self._tool_config.allowed_tools,
            "max_turns": self._tool_config.max_turns,
        }

    @observe(name="session_card_4pass")
    async def run(
        self,
        *,
        session_type: SessionType,
        asset: str,
        data_pool: str,
        asset_data: str,
        now: datetime | None = None,
    ) -> OrchestratorResult:
        generated_at = now or datetime.now(UTC)
        runner_calls: list[RunnerCall] = []
        total_ms = 0

        # Pass 1 — régime
        call1 = RunnerCall(
            prompt=self._regime.build_prompt(data_pool=data_pool),
            system=self._regime.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._regime.name}",
            **self._tool_fields_for("regime"),
        )
        runner_calls.append(call1)
        resp1 = await self._runner.run(call1)
        regime = self._regime.parse(resp1.text)
        total_ms += resp1.duration_ms
        log.info("brain.pass1.done", quadrant=regime.quadrant, conf=regime.confidence_pct)

        regime_block = (
            f"Quadrant: **{regime.quadrant}** "
            f"(confidence {regime.confidence_pct:.0f}%)\n\n"
            f"Rationale: {regime.rationale}\n"
        )

        # Pass 2 — asset specialization
        call2 = RunnerCall(
            prompt=self._asset.build_prompt(
                asset=asset, regime_block=regime_block, asset_data=asset_data
            ),
            system=self._asset.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._asset.name}::{asset.upper()}",
            **self._tool_fields_for("asset"),
        )
        runner_calls.append(call2)
        resp2 = await self._runner.run(call2)
        spec = self._asset.parse(resp2.text)
        total_ms += resp2.duration_ms
        log.info(
            "brain.pass2.done",
            asset=spec.asset,
            bias=spec.bias_direction,
            conv=spec.conviction_pct,
        )

        # Pass 3 — bull-case stress-test
        call3 = RunnerCall(
            prompt=self._stress.build_prompt(specialization=spec, asset_data=asset_data),
            system=self._stress.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._stress.name}",
            **self._tool_fields_for("stress"),
        )
        runner_calls.append(call3)
        resp3 = await self._runner.run(call3)
        stress = self._stress.parse(resp3.text)
        total_ms += resp3.duration_ms
        log.info(
            "brain.pass3.done",
            n_counter=len(stress.counter_claims),
            revised=stress.revised_conviction_pct,
        )

        # Pass 4 — invalidation conditions
        call4 = RunnerCall(
            prompt=self._invalidation.build_prompt(specialization=spec, stress=stress),
            system=self._invalidation.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._invalidation.name}",
            **self._tool_fields_for("invalidation"),
        )
        runner_calls.append(call4)
        resp4 = await self._runner.run(call4)
        invalidation = self._invalidation.parse(resp4.text)
        total_ms += resp4.duration_ms
        log.info("brain.pass4.done", n_conditions=len(invalidation.conditions))

        # Critic Agent gate — runs the rule-based reviewer over the
        # concatenated narrative against the data pool. Pass 4 is the
        # one that gets persisted to `session_card_audit.critic_*`.
        narrative = _assemble_narrative(regime, spec, stress, invalidation)
        verdict = self._critic_fn(
            briefing_markdown=narrative,
            source_pool=data_pool + "\n" + asset_data,
            asset_whitelist=[asset],
        )
        critic = CriticDecision(
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            n_findings=len(verdict.findings),
            findings=[
                {
                    "sentence": f.sentence,
                    "reason": f.reason,
                    "severity": f.severity,
                }
                for f in verdict.findings
            ],
            suggested_footer=verdict.suggested_footer,
        )
        log.info(
            "brain.critic.done",
            verdict=critic.verdict,
            conf=critic.confidence,
            n_findings=critic.n_findings,
        )

        card = SessionCard(
            session_type=session_type,
            asset=asset,
            model_id=self._model_id,
            generated_at=generated_at,
            regime=regime,
            specialization=spec,
            stress=stress,
            invalidation=invalidation,
            critic=critic,
            source_pool_hash=hash_pool(data_pool, asset_data),
            claude_duration_ms=total_ms,
        )

        return OrchestratorResult(card=card, runner_calls=runner_calls)


def _assemble_narrative(
    regime: RegimeReading,
    spec: AssetSpecialization,
    stress: StressTest,
    invalidation: InvalidationConditions,
) -> str:
    """Plain-text aggregation used by the Critic for sentence-level scan."""
    parts: list[str] = []
    parts.append(f"Régime quadrant: {regime.quadrant}. {regime.rationale}")
    parts.append(
        f"Asset {spec.asset}: bias {spec.bias_direction} at {spec.conviction_pct:.0f}% conviction."
    )
    for m in spec.mechanisms:
        claim = m.get("claim")
        if claim:
            parts.append(str(claim))
    for c in stress.counter_claims:
        claim = c.get("claim")
        if claim:
            parts.append(f"Counter-claim: {claim}")
    for cond in invalidation.conditions:
        condition = cond.get("condition")
        if condition:
            parts.append(f"Invalidation: {condition}")
    return " ".join(parts)
