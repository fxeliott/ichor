# ADR-091: W117b GEPA prompt-optimization wiring (DSPy 3.2 Voie-D-bound)

**Status**: PROPOSED — awaiting Eliot ratify before code lands. Estimated 3 dev-days end-to-end ; design captured here so future round can ship without re-litigation.

**Date**: 2026-05-13

**Supersedes**: none

**Extends**: [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (no BUY/SELL boundary), [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md) (CI invariants), [ADR-087](ADR-087-phase-d-auto-improvement-loops.md) (Phase D loops + W117a DSPy foundation).

**Related**: ADR-088 (W115c pocket-skill-reader — provides the per-pocket skill signal that GEPA will use as fitness selection seed).

## Context

W117a (round 26, PR #101) shipped the foundation `services/dspy_claude_runner_lm.py` — a `dspy.BaseLM` subclass that routes `forward()` through `call_agent_task_async`, making every DSPy-using module Voie-D-bound by construction. The W117a sentinel namespace (`_ALLOWED_MODEL_TAGS = {"ichor-claude-runner-haiku", "-sonnet", "-opus"}`) blocks the obvious litellm-bait `dspy.LM(model="claude-3-5-haiku-latest")` regression.

W117b is the **consumer** : wire DSPy 3.2 GEPA (Genetic-Evolutionary Prompt Adaptation) on top of the foundation to evolve Ichor 4-pass system prompts and Pass-3 stress addenda templates against the realized-outcome corpus.

Anthropic-side risk : GEPA is a **mutation-and-selection loop**. Each generation, GEPA spawns N candidate prompts, evaluates each against a held-out validation set (LLM calls), scores them by a fitness function, keeps the top-K, and mutates them for the next generation. Naïvely : `N candidates × T generations × M validation examples` LLM calls = **many thousands of subprocess `claude -p` invocations per optimization run**. Without ban-risk discipline, this saturates Max 20x plan quota in minutes and trips Anthropic's misuse detectors.

Round 16 ban-risk minimization rule (`ce qui peut manquer` Eliot directive, codified as rule 16) makes this MANDATORY safe-by-default :

1. Sentinel namespace already in place (W117a).
2. GEPA budget **MUST** be hard-capped at 100 LLM calls per optimization run.
3. Fitness function **MUST** include an ADR-017 regex penalty to prevent the optimizer from discovering "more effective" prompts that emit trade signals.
4. All GEPA fires **MUST** be cron-scheduled with ≥ 60 min spacing from any other LLM-calling job (ADR-087 invariant 4 already requires this).
5. Feature-flag fail-closed gating (`phase_d_w117b_gepa_enabled`) — fail-closed default.

## Decision

### Invariant 1 — Hard budget cap per run

Every `cli/run_gepa_optimizer.py` invocation **MUST** declare its budget upfront and enforce it monotonically :

```python
_GEPA_BUDGET_HARD_CAP: Final[int] = 100  # max LLM calls per run

@dataclass
class GepaRunBudget:
    max_lm_calls: int
    calls_used: int = 0

    def consume(self, n: int = 1) -> None:
        if self.calls_used + n > self.max_lm_calls:
            raise BudgetExhausted(
                f"GEPA budget exhausted : {self.calls_used + n} > {self.max_lm_calls}. "
                f"Stop the run and inspect."
            )
        self.calls_used += n
```

The budget is **per invocation** and **non-resumable**. A killed cron mid-run does NOT carry the unused budget forward.

### Invariant 2 — ADR-017 fitness HARD-ZERO gate (amended round-32)

**Round-32 amendment** : the original ADR-091 §"Invariant 2" reading was a soft-lambda penalty `−λ × count_violations(output)`. The ichor-trader round-32 pre-implementation review correctly flagged that as a bypass landmine : a GEPA-evolved candidate prompt with high Brier-skill (e.g. +0.4) + one obfuscated trade signal (e.g. `ＢＵＹ` full-width, `ВUY` Cyrillic, `acheter EUR` FR imperative) could score net-positive fitness despite the boundary breach. Soft-lambda is **averageable** ; trade signals at scale are **unacceptable, ever**.

The amended doctrine is **hard-zero** :

```python
def compute_fitness(brier_skill: float, candidate_output: str) -> float:
    """Round-32 amended ADR-091 §Invariant 2 — HARD-ZERO gate.

    Any ADR-017 violation forces fitness = -inf, REGARDLESS of the
    candidate's Brier-skill. The GEPA optimizer cannot promote a
    candidate that emits trade signals. Period.
    """
    if count_violations(candidate_output) > 0:
        return float("-inf")  # boundary breach = uncompete
    return brier_skill
```

**Defense-in-depth at three layers** :

1. **Source-of-truth regex** : `services/adr017_filter.py` (round-31 sub-wave .a) is THE single module. No peer regex copies anywhere.
2. **Round-32 Unicode + multilingual hardening** : `is_adr017_clean` applies NFKC normalization + zero-width strip + Cyrillic/Greek confusable fold + multilingual lexicon (FR/ES/DE imperatives) BEFORE matching. Bypass vectors closed : `ＢＵＹ`, `ВUY`, `B​UY`, `acheter`, `vendez`, `comprar`, `kaufen`, etc.
3. **DB CHECK constraint** : migration 0047 ships `ck_gepa_candidate_adr017_hard_zero` = `adr017_violations = 0 OR status = 'rejected'`. Even if the optimizer or admin endpoint glitches, the DB refuses to land a tainted candidate as `'candidate'` or `'adopted'`.

The regex must be the **same** `_ADR017_FORBIDDEN_RE` superset that `services/addendum_generator.py` uses — extracted to `services/adr017_filter.py` round-31 sub-wave .a and hardened round-32. Future LLM-touching modules consuming the filter inherit the hard-zero contract automatically.

### Invariant 3 — Cron spacing + feature-flag

`ichor-gepa-optimizer.timer` is a **monthly** cron, NOT weekly or nightly. Schedule : 1st Saturday of the month at 12:00 Paris (clear from London/NY trading sessions + Sunday Pass-6 calibration). 60 min minimum spacing from any other LLM-calling cron (W116c Sunday 19:00 — already separated by days).

Feature flag `phase_d_w117b_gepa_enabled` (`feature_flags` table) is **OFF** by default. When flipped ON :

1. The flag enables the cron to fire (the systemd timer ARMS the service unit).
2. The service unit re-checks the flag at fire time (fail-closed pattern).
3. The flag is auto-disabled after each successful run (single-shot pattern) — Eliot must re-enable for each optimization round.

Single-shot auto-disable is unusual for feature flags but is the right pattern here : it prevents accidental back-to-back runs that would blow budget.

### Invariant 4 — Selection seed = W115c skill signal

GEPA needs a **selection seed** : which pockets should the optimizer focus on? Round-28 ADR-088 W115c provides `PocketSkill` records per `(asset, regime, session_type)` pocket with `confidence_band ∈ {high_skill, neutral, anti_skill}`. GEPA seed = the anti-skill pockets (the ones where current prompts demonstrably under-perform climatology).

This wiring closes the Phase D loop completely : `measure (Vovk) ✓ → read (W115c) ✓ → act (GEPA optimization on anti-skill pockets only)`. No wasted LLM calls on already-skilled pockets.

### Invariant 5 — Validation set isolation

The validation set used to score candidate prompts **MUST** be temporally isolated from the training set :

- Training set : `session_card_audit` rows older than 30 days.
- Validation set : rows 14-30 days old (held out from training).
- Production scoring : rows < 14 days old (NEVER touched by GEPA).

This prevents data leakage and follows ADR-086 RAG past-only-retrieval ethos.

### Invariant 6 — Persistence of generated prompts

GEPA outputs (best candidate per pocket per generation) **MUST** be persisted to a new table `gepa_candidate_prompts` (migration 0047 candidate) with :

- `id UUID PK`
- `generated_at TIMESTAMPTZ NOT NULL`
- `pocket_asset VARCHAR(16)` + `pocket_regime VARCHAR(32)` + `pocket_session_type VARCHAR(16)`
- `generation INT NOT NULL` (0 = seed, 1+ = mutations)
- `pass_kind VARCHAR(16) NOT NULL CHECK (pass_kind IN ('regime', 'asset', 'stress', 'invalidation'))`
- `prompt_text TEXT NOT NULL`
- `fitness_score NUMERIC(8, 5) NOT NULL`
- `adr017_violations INT NOT NULL DEFAULT 0`
- `status VARCHAR(16) NOT NULL CHECK (status IN ('candidate', 'adopted', 'rejected', 'archived')) DEFAULT 'candidate'`
- `notes TEXT`
- UNIQUE constraint on `(pocket_asset, pocket_regime, pocket_session_type, generation, pass_kind)`.

**Immutable on insert** (no UPDATE/DELETE except for `status` column via specific admin endpoint with audit-log row). Same pattern as `auto_improvement_log`.

### Invariant 7 — Adoption gate (Eliot ratify)

A candidate prompt is `status='candidate'` by default. To promote it to `status='adopted'` (replacing the current production prompt in `packages/ichor_brain/passes/*.py`), Eliot **MUST** manually flip the status via :

```sql
UPDATE gepa_candidate_prompts
   SET status = 'adopted', notes = 'Eliot-approved 2026-XX-XX after backtesting'
 WHERE id = '<uuid>';
```

The 4-pass orchestrator reads `status='adopted'` rows at startup. NO automatic adoption. Every prompt change touching the LLM input surface is a deliberate human-in-loop action.

## Implementation roadmap (W117b sub-waves)

| Sub-wave    | Title                                                                                                                                                                                  | Effort          | Status (round-32)                                                                                                             |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| W117b.a     | `services/adr017_filter.py` extracted from `addendum_generator.py` + shared with GEPA fitness                                                                                          | 0.25d           | ✅ SHIPPED PR #103                                                                                                            |
| W117b.a.r32 | `services/adr017_filter.py` HARDENED : NFKC + ZWSP strip + Cyrillic/Greek confusables + multilingual FR/ES/DE imperatives                                                              | 0.25d           | ✅ SHIPPED PR #104 commit 1                                                                                                   |
| W117b.b     | Migration 0047 `gepa_candidate_prompts` + ORM model + DB CHECK hard-zero + Cap5 FORBIDDEN_SET 7→8                                                                                      | 0.25d           | ✅ SHIPPED PR #104 commit 2                                                                                                   |
| W117b.c     | `services/gepa_optimizer.py` core (mutation operators + Pareto frontier selection + budget enforcement + HARD-ZERO fitness gate per amended §Invariant 2)                              | 1.0d            | ⏳ DEFERRED — needs validation set n ≥ 100 per pocket + dual `ClaudeRunnerLM` (student + reflection_lm) per DSPy 3.2 GEPA API |
| W117b.d     | `cli/run_gepa_optimizer.py` monthly cron + feature-flag fail-closed + budget exhaustion handler + single-shot auto-disable                                                             | 0.5d            | ⏳ blocked by .c                                                                                                              |
| W117b.e     | Hetzner systemd timer `ichor-gepa-optimizer.timer` + register-cron script                                                                                                              | 0.25d           | ⏳ blocked by .d                                                                                                              |
| W117b.f     | CI guard tests : (a) `_ADR017_FORBIDDEN_RE` superset single-source, (b) budget cap enforced, (c) sentinel namespace honored, (d) feature-flag fail-closed, (e) hard-zero gate enforced | 0.5d            | ⏳ blocked by .c + .d                                                                                                         |
| W117b.g     | Adoption admin endpoint `/v1/admin/gepa/adopt-candidate` + audit_log row + invariant test                                                                                              | 0.25d           | ⏳ orthogonal to .c–.f                                                                                                        |
| **Total**   |                                                                                                                                                                                        | **~3 dev-days** | **~0.75d shipped (.a + .a.r32 + .b), ~2.25d remaining**                                                                       |

## Reversibility (rule 19)

- Migration 0047 has a working down (drop table).
- `phase_d_w117b_gepa_enabled` flag OFF → cron is a no-op (fail-closed).
- Adopted prompts are version-controlled in git (`packages/ichor_brain/passes/*.py`) — rollback = git revert of the adoption commit + reset `status='adopted'` rows back to `'candidate'`.
- Budget cap rejects runaway runs without ops intervention.

## Consequences

### Positive

- **Closes the Phase D measure→act→improve loop** : Vovk weights surface anti-skill pockets (W115) → W115c reads them (round-28) → GEPA optimizes prompts targeting those pockets (W117b) → adopted prompts replace under-performing originals → Vovk re-scores in next cycle.
- **Voie D respected by construction** : GEPA uses the existing W117a `ClaudeRunnerLM`. Zero new Anthropic API surface.
- **Budget-bounded** : max 100 LLM calls per monthly run × 12 months = ~1200 calls/year. Trivial vs Max 20x quota.
- **ADR-017 fitness penalty mechanises the boundary** : the optimizer CANNOT discover a "more decisive" trade-signal-emitting prompt because the regex penalty zeros it out before selection.
- **Adoption gate** : every prompt change is human-reviewed before going live. No silent prompt drift.

### Negative

- **3 dev-days is substantial** : largest single Phase D wave. Splittable into W117b.a → .g sub-waves for incremental ship + review.
- **Validation set must accumulate** : Ichor only has ~6 months of production cards as of round-28. GEPA on n < 50 validation samples is noisy ; consider deferring W117b activation until n ≥ 100 per anti-skill pocket (`EUR_USD/usd_complacency` is at n=13 today).
- **Prompt-space exploration cost** : GEPA may take 3-6 generations to find a candidate that beats the production prompt. Each generation = budget consumed.

### Neutral

- **DSPy 3.2 GEPA API stability** : DSPy is fast-evolving (3.0 → 3.2 in 4 months). Pinning `dspy>=3.2,<4.0` in the `[phase-d-w117]` extras is the right discipline.
- **Anthropic 2026 ToS compatibility** : GEPA via subprocess `claude -p` is functionally equivalent to interactive use ; same usage class as Couche-2 agents. No new ToS surface vs current Phase D.

## Future work

- **W117c GEPA on Couche-2 agent prompts** (cb_nlp, news_nlp, sentiment, positioning, macro) — same optimizer, different prompt corpus. Defer until W117b validates the approach on 4-pass.
- **GEPA × confluence_engine** : optimize the deterministic confluence factor weights (currently hard-coded 5× contributions). Would require a separate fitness function (no LLM, just realized-outcome scoring). Tracked as future ADR-092.
- **A/B testing in production** : shadow-run adopted prompts against production for 14 days before promotion. Requires `gepa_candidate_prompts.status = 'shadow_testing'` value + scoreboard endpoint.

## Open questions for Eliot ratify

1. **Budget cap value** : 100 calls/run is conservative. 200? 500? Trade-off : more budget = better convergence per run, but more risk on quota.
2. **Monthly cadence** : 1st Saturday OK? Or quarterly? Higher cadence = faster iteration but more validation-set churn.
3. **Adoption gate strictness** : require A/B shadow test (14-day) OR allow direct adoption with audit_log row? Researcher recommendation = shadow test for first 3 adoptions, then relax.
4. **Sub-wave shipping order** : W117b.a (adr017_filter extract) is a prerequisite for everything else. Ship .a first, then .b+.c bundled, then .d+.e bundled? Or single big PR?
