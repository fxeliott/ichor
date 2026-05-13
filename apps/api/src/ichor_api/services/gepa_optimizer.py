"""W117b.c — GEPA optimizer skeleton (ADR-091, Voie D-bound).

Skeleton ship round-36. Provides the structural building blocks for
the future DSPy 3.2.1 GEPA optimization wiring : budget enforcement,
hard-zero ADR-017 fitness gate, and the DSPy-compatible metric
callback shape — WITHOUT any actual LLM call yet.

This module exists to :
  1. Unlock sub-waves .d (CLI) / .e (systemd timer) / .f (CI guards)
     / .g (adoption admin endpoint) architecturally — they all
     depend on the structural API surface defined here.
  2. Make the ADR-091 §"Invariant 1" budget cap + §"Invariant 2"
     amended HARD-ZERO contract testable in isolation.
  3. Document the DSPy GEPA API integration shape (verified r35
     subagent #2) so that when n ≥ 100 per pocket is reached
     (~14 weeks per Vovk pocket accumulation rate), wiring is a
     mechanical replay of the documented contract.

DSPy GEPA API (verified r35) :
  - `from dspy import GEPA` (canonical)
  - `GEPA(metric, max_metric_calls=N, reflection_lm=LM, ...)`
  - `compile(student, *, trainset, teacher=None, valset=None) -> Module`
  - `metric(gold, pred, trace, pred_name, pred_trace) -> float | ScoreWithFeedback`

ADR-091 invariants enforced :
  1. §Invariant 1 — `_GEPA_BUDGET_HARD_CAP: Final[int] = 100` ; per-run
     `GepaRunBudget` raises `BudgetExhausted` when `consume()` would
     exceed the cap. Non-resumable across cron fires.
  2. §Invariant 2 (amended r32 HARD-ZERO) — `compute_fitness_with_hard_zero`
     returns `float("-inf")` if `count_violations(output) > 0`. The
     optimizer cannot promote a candidate emitting trade signals.
     Defense-in-depth at 3 layers : regex source (r31 + r32 Unicode
     hardening) + this fitness function + DB CHECK constraint
     `ck_gepa_candidate_adr017_hard_zero` (migration 0047).

ADR-009 Voie D : this module imports NO `anthropic` SDK. The future
W117b.d CLI will inject a `dspy.LM` instance (our W117a
`ClaudeRunnerLM` subclass) — model selection stays sentinel-namespaced
(`ichor-claude-runner-haiku`/`-sonnet`/`-opus`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, TypedDict

from .adr017_filter import count_violations

# --------------------------------------------------------------------
# §Invariant 1 — Budget enforcement (per-run hard cap)
# --------------------------------------------------------------------

# Per ADR-091 §"Invariant 1" : hard cap of 100 LLM calls per optimization
# run. Non-resumable across cron fires (a killed cron mid-run does NOT
# carry unused budget forward). Conservative ; can be revisited only
# via a successor ADR explicitly raising this number.
_GEPA_BUDGET_HARD_CAP: Final[int] = 100


class BudgetExhausted(Exception):
    """Raised when `GepaRunBudget.consume()` would exceed the per-run
    LLM call cap. The optimizer MUST catch this at the run level and
    stop the GEPA loop gracefully (audit_log row + cron exit 0)."""


@dataclass
class GepaRunBudget:
    """Per-run LLM call budget. Monotonically increasing.

    ADR-091 §"Invariant 1" : enforce hard cap of `_GEPA_BUDGET_HARD_CAP`
    calls per run. The optimizer reads `calls_used` to introspect ;
    `consume(n)` advances + raises `BudgetExhausted` past cap.

    Typical usage in W117b.d CLI :
        budget = GepaRunBudget(max_lm_calls=_GEPA_BUDGET_HARD_CAP)
        try:
            while not converged:
                budget.consume(1)  # before each LLM call
                result = await call_agent_task_async(...)
                ...
        except BudgetExhausted as exc:
            log.warning("gepa.budget_exhausted", ...)
            return 1
    """

    max_lm_calls: int
    calls_used: int = 0

    def __post_init__(self) -> None:
        if self.max_lm_calls > _GEPA_BUDGET_HARD_CAP:
            raise ValueError(
                f"max_lm_calls={self.max_lm_calls} exceeds the ADR-091 "
                f"§Invariant 1 hard cap of {_GEPA_BUDGET_HARD_CAP}. "
                "A successor ADR is required to raise this number."
            )
        if self.max_lm_calls < 1:
            raise ValueError(f"max_lm_calls must be >= 1 (got {self.max_lm_calls})")
        if self.calls_used < 0:
            raise ValueError(f"calls_used must be >= 0 (got {self.calls_used})")

    def consume(self, n: int = 1) -> None:
        """Increment `calls_used` by `n`. Raises `BudgetExhausted` if
        the new total would exceed `max_lm_calls`."""
        if n < 1:
            raise ValueError(f"consume(n) requires n >= 1 (got {n})")
        if self.calls_used + n > self.max_lm_calls:
            raise BudgetExhausted(
                f"GEPA budget exhausted : {self.calls_used + n} > "
                f"{self.max_lm_calls}. Stop the run and inspect."
            )
        self.calls_used += n

    @property
    def remaining(self) -> int:
        """Calls left in this run's budget."""
        return self.max_lm_calls - self.calls_used


# --------------------------------------------------------------------
# §Invariant 2 (amended r32 HARD-ZERO) — Fitness gate
# --------------------------------------------------------------------


def compute_fitness_with_hard_zero(
    brier_skill: float,
    candidate_output: str,
) -> float:
    """ADR-091 §"Invariant 2" amended r32 — HARD-ZERO fitness gate.

    Returns the Brier skill score for the candidate output IFF the
    output contains ZERO ADR-017 forbidden tokens (per the r32-hardened
    `services.adr017_filter.count_violations`). Otherwise returns
    `float("-inf")` to permanently disqualify the candidate.

    The optimizer's Pareto frontier selection cannot promote a
    `-inf`-scored candidate — the boundary breach is absolute, not
    averageable. The soft-lambda penalty form (`brier_skill - lambda *
    count`) was the original ADR-091 reading but the ichor-trader r32
    pre-implementation review flagged it as a bypass landmine : a
    candidate with high Brier skill + 1 obfuscated trade signal could
    score net-positive fitness. Hard-zero closes that landmine.

    Defense-in-depth at 3 layers :
      1. Regex source (r31 sub-wave .a + r32 Unicode hardening)
      2. THIS fitness function (round-36 W117b.c)
      3. DB CHECK constraint `ck_gepa_candidate_adr017_hard_zero` on
         migration 0047 — even if this function were bypassed in
         Python, the DB would refuse the INSERT.
    """
    if count_violations(candidate_output) > 0:
        return float("-inf")
    return brier_skill


# --------------------------------------------------------------------
# DSPy GEPA metric callback shape
# --------------------------------------------------------------------


class ScoreWithFeedback(TypedDict):
    """DSPy GEPA's optional structured metric return type.

    When the metric returns this dict (instead of a bare `float`),
    DSPy can pass the `feedback` text back to the candidate prompt
    proposer to guide the next mutation. Per DSPy 3.2.1 docs verified
    r35 subagent #2.
    """

    score: float
    feedback: str


def ichor_gepa_metric(
    gold: Any,
    pred: Any,
    trace: Any | None = None,
    pred_name: str | None = None,
    pred_trace: Any | None = None,
) -> ScoreWithFeedback:
    """DSPy GEPA metric callback for Ichor 4-pass prompt optimization.

    Signature matches DSPy 3.2.1 GEPA contract :
      `metric(gold, pred, trace, pred_name, pred_trace) -> float | ScoreWithFeedback`

    `gold` : the realized outcome (e.g. `realized_scenario_bucket` from
        a historical `session_card_audit` row).
    `pred` : the candidate prompt's prediction (must expose
        `.bucket_probabilities` or similar — Pass-6 schema).
    `trace` : DSPy execution trace.
    `pred_name`/`pred_trace` : per-predictor sub-feedback.

    Returns `ScoreWithFeedback`. The skeleton implementation here is
    structural ONLY : it returns `{score: 0.0, feedback: "skeleton — wire in W117b.d"}`
    to validate the callback shape without computing actual Brier skill.
    The full implementation will land in sub-wave .d (CLI), consuming
    `services.penalized_brier.ahmadian_pbs` for the skill term and this
    module's `compute_fitness_with_hard_zero` for the ADR-017 gate.
    """
    # Skeleton placeholder — wire actual Brier scoring + ADR-017 gate
    # in W117b.d. This function exists now to pin the callback shape
    # for DSPy GEPA's static type-checking (and to test the dataclass
    # contract in isolation).
    if pred is None:
        return {"score": 0.0, "feedback": "no prediction"}
    return {
        "score": 0.0,
        "feedback": (
            "skeleton (W117b.c) — wire ahmadian_pbs + compute_fitness_with_hard_zero in W117b.d"
        ),
    }


# --------------------------------------------------------------------
# Run-level state (skeleton — actual orchestration in W117b.d)
# --------------------------------------------------------------------


@dataclass
class GepaRunContext:
    """Per-run state for a GEPA optimization invocation.

    Skeleton container — the W117b.d CLI will populate this from the
    feature-flag check + the W115c pocket selection seed + the
    temporal-isolation validation set query (ADR-091 §Invariant 5).
    """

    gepa_run_id: str  # UUID
    budget: GepaRunBudget
    pocket_asset: str | None = None
    pocket_regime: str | None = None
    pocket_session_type: str | None = None
    pass_kind: str = "regime"  # noqa: S105 — 4-pass label, not a password
    candidates_emitted: int = 0
    candidates_rejected_adr017: int = 0
    candidates_promoted: int = 0
    notes: list[str] = field(default_factory=list)


__all__ = [
    "_GEPA_BUDGET_HARD_CAP",
    "BudgetExhausted",
    "GepaRunBudget",
    "GepaRunContext",
    "ScoreWithFeedback",
    "compute_fitness_with_hard_zero",
    "ichor_gepa_metric",
]
