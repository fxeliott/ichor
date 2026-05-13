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
    ScenariosPass,
    StressPass,
)
from .passes.base import PassError
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

# Forward-declared type for Pass-6 output — resolved lazily inside
# `run()` so the brain package stays importable without `ichor_api`
# on the path (mirrors `_default_critic_fn` lazy-import pattern).
if False:  # pragma: no cover — type-checking only
    from ichor_api.services.scenarios import ScenarioDecomposition  # noqa: F401


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
        scenarios_pass: Pass[Any] | None = None,
        critic_fn: CriticFn | None = None,
        model_id: str = "claude-opus-4-7",
        scenarios_model: str = "sonnet",
        scenarios_effort: str = "medium",
        enable_scenarios: bool = False,
        tool_config: ToolConfig | None = None,
    ):
        self._runner = runner
        self._regime = regime_pass or RegimePass()
        self._asset = asset_pass or AssetPass()
        self._stress = stress_pass or StressPass()
        self._invalidation = invalidation_pass or InvalidationPass()
        # W105c — Pass-6 scenario_decompose. Default disabled to keep
        # pre-W105 behaviour byte-exact ; flip `enable_scenarios=True`
        # to emit the 7-bucket decomposition per (asset, session). The
        # callable interface is `Pass[ScenarioDecomposition]` — Any
        # used here because the schema lives in ichor_api and the
        # brain package stays importable without it.
        self._scenarios = scenarios_pass or ScenariosPass()
        self._enable_scenarios = enable_scenarios
        # Pass-6 LLM knobs per W105 research 2026-05-12 (researcher
        # subagent) : Sonnet 4.6 materially better than Haiku on
        # structured probability emissions with cap-95 awareness.
        # `effort=medium` keeps wall-time bounded (~30-60s) — `high`
        # only if the calibration block is unusually rich.
        self._scenarios_model = scenarios_model
        self._scenarios_effort = scenarios_effort
        self._critic_fn = critic_fn or _default_critic_fn
        self._model_id = model_id
        self._tool_config = tool_config

    async def _run_pass_with_retry(
        self,
        call: RunnerCall,
        parser,
        *,
        step_name: str,
        max_retries: int = 1,
    ):
        """Run a pass call with 1 retry on transient runner / parse error.

        Phase A reliability improvement (round 9, 2026-05-12) : the
        pre-existing orchestrator gave up after the first failed Pass —
        a card died if e.g. the Claude CLI returned empty stdout
        transiently (observed today during Claude auth expiry).
        Now retries once with exponential backoff (30s) on :
          * `PassError` — JSON parse failure / Pydantic validation
          * `httpx`/runner transient errors (bubbled from RunnerClient)
        Does NOT retry on `asyncio.CancelledError` (operator abort).

        Returns the parser output + `(elapsed_ms, attempt_count)` so
        the orchestrator can sum durations correctly.
        """
        import asyncio

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = await self._runner.run(call)
                parsed = parser(resp.text)
                if attempt > 0:
                    log.info(
                        "brain.pass.retry_recovered",
                        step_name=step_name,
                        attempt=attempt + 1,
                    )
                return parsed, resp.duration_ms
            except PassError as e:
                last_error = e
                if attempt < max_retries:
                    log.warning(
                        "brain.pass.retry_after_parse_error",
                        step_name=step_name,
                        attempt=attempt + 1,
                        error=str(e)[:200],
                    )
                    await asyncio.sleep(30.0)
                    continue
                raise
            except Exception as e:  # noqa: BLE001 — runner transient errors
                last_error = e
                if attempt < max_retries:
                    log.warning(
                        "brain.pass.retry_after_runner_error",
                        step_name=step_name,
                        attempt=attempt + 1,
                        error=str(e)[:200],
                    )
                    await asyncio.sleep(30.0)
                    continue
                raise
        # Unreachable but satisfies type-checker.
        raise last_error or RuntimeError("retry loop exhausted")

    def _tool_fields_for(self, pass_kind: str) -> dict[str, Any]:
        """W87 STEP-5 — emit Capability 5 tool fields for a RunnerCall
        when the pass is in `tool_config.enabled_for_passes`. Returns
        `{}` (no fields, pre-W87 behaviour) otherwise.

        Pass kind strings : "regime", "asset", "stress", "invalidation",
        "scenarios" (W105d — defaults excluded ; opt in via
        `ToolConfig(enabled_for_passes=frozenset({..., "scenarios"}))`).
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
        calibration_block: str | None = None,
        analogues_section: str = "",
        pass3_addenda_section: str = "",
        confluence_section: str = "",
    ) -> OrchestratorResult:
        """Run the 4 (+optional 6) passes for one (session_type, asset).

        `analogues_section` (W110d ADR-086) is an optional pre-rendered
        RAG block of past-only historical analogues. When non-empty,
        forwarded to `RegimePass.build_prompt` ; the model treats it
        as sanity-check context, never as prescriptive evidence
        (ADR-017 boundary, ADR-086 Invariant 1 embargo). The caller
        is responsible for retrieval (see
        `services.rag_embeddings.retrieve_analogues`) so the
        orchestrator stays DB-session-free + pure on its 4-pass loop.
        Empty string = pre-W110d byte-identical behaviour.

        `pass3_addenda_section` (W116c, ADR-087 Phase D) is an optional
        pre-rendered block of operator addenda derived from the W116b
        post-mortem PBS evaluator. Forwarded to `StressPass.build_prompt`
        ; the model takes them as adversarial context. Same purity
        contract as `analogues_section` : caller (apps/api) queries
        `services.pass3_addendum_injector.select_active_addenda` and
        renders, gated behind a feature flag. Empty string = pre-W116c
        byte-identical behaviour.

        `confluence_section` (W115c, ADR-088 round-28) is an optional
        pre-rendered Vovk-skill calibration hint from
        `services.pocket_skill_reader.render_pass3_addendum`. When
        non-empty, forwarded to `StressPass.build_prompt` ; the model
        uses it as a confidence-band hint (high_skill / neutral /
        anti_skill) to weight invalidation risks in its counter-claim
        selection. NEVER a directional override of Pass-2 bias /
        conviction (ADR-017 boundary intact). Same purity contract :
        caller (apps/api) queries
        `services.pocket_skill_reader.read_pocket` + `.render_pass3_addendum`,
        gated by `phase_d_w115c_confluence_enabled` feature flag.
        Empty string = pre-W115c byte-identical behaviour.
        """
        generated_at = now or datetime.now(UTC)
        runner_calls: list[RunnerCall] = []
        total_ms = 0

        # Pass 1 — régime
        call1 = RunnerCall(
            prompt=self._regime.build_prompt(
                data_pool=data_pool, analogues_section=analogues_section
            ),
            system=self._regime.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._regime.name}",
            **self._tool_fields_for("regime"),
        )
        runner_calls.append(call1)
        regime, dur_ms = await self._run_pass_with_retry(
            call1, self._regime.parse, step_name="pass1_regime"
        )
        total_ms += dur_ms
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
        spec, dur_ms = await self._run_pass_with_retry(
            call2, self._asset.parse, step_name="pass2_asset"
        )
        total_ms += dur_ms
        log.info(
            "brain.pass2.done",
            asset=spec.asset,
            bias=spec.bias_direction,
            conv=spec.conviction_pct,
        )

        # Pass 3 — bull-case stress-test
        call3 = RunnerCall(
            prompt=self._stress.build_prompt(
                specialization=spec,
                asset_data=asset_data,
                addenda_section=pass3_addenda_section,
                confluence_section=confluence_section,
            ),
            system=self._stress.system_prompt,
            model="opus",
            effort="high",
            cache_key=f"framework::{self._stress.name}",
            **self._tool_fields_for("stress"),
        )
        runner_calls.append(call3)
        stress, dur_ms = await self._run_pass_with_retry(
            call3, self._stress.parse, step_name="pass3_stress"
        )
        total_ms += dur_ms
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
        invalidation, dur_ms = await self._run_pass_with_retry(
            call4, self._invalidation.parse, step_name="pass4_invalidation"
        )
        total_ms += dur_ms
        log.info("brain.pass4.done", n_conditions=len(invalidation.conditions))

        # Pass 6 — scenario_decompose 7-bucket (ADR-085, W105c).
        # Optional, gated on `enable_scenarios`. Output is a
        # `ScenarioDecomposition` (lazy-imported inside the pass).
        # Routed through claude-runner with `model=sonnet,
        # effort=medium` per W105 researcher 2026-05-12 review.
        scenarios_payload: list[dict[str, Any]] | None = None
        if self._enable_scenarios:
            cal_block = calibration_block or (
                "(no calibration bins available — use your judgement "
                "on per-asset typical magnitude ranges)"
            )
            call6 = RunnerCall(
                prompt=self._scenarios.build_prompt(
                    asset=asset,
                    session_type=session_type,
                    specialization=spec,
                    stress=stress,
                    invalidation=invalidation,
                    calibration_block=cal_block,
                ),
                system=self._scenarios.system_prompt,
                model=self._scenarios_model,
                effort=self._scenarios_effort,
                cache_key=f"framework::{self._scenarios.name}::{asset.upper()}",
                **self._tool_fields_for("scenarios"),
            )
            runner_calls.append(call6)
            decomposition, dur_ms = await self._run_pass_with_retry(
                call6, self._scenarios.parse, step_name="pass6_scenarios"
            )
            total_ms += dur_ms
            # `decomposition` is `ScenarioDecomposition` — serialize
            # to plain dict list to attach to SessionCard without
            # cross-package type coupling.
            scenarios_payload = [s.model_dump() for s in decomposition.scenarios]
            log.info(
                "brain.pass6.done",
                n_buckets=len(scenarios_payload),
                p_max=max((s["p"] for s in scenarios_payload), default=0.0),
                p_sum=sum(s["p"] for s in scenarios_payload),
            )

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
            scenarios=scenarios_payload,
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
