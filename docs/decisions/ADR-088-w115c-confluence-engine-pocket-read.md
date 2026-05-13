# ADR-088: W115c pocket-skill reader (close Phase D measure→act loop)

**Status**: Accepted (round-32b ratify, 2026-05-13) — code shipped round-29 commit `e9ddcd6` (`services/pocket_skill_reader.py` 200 LOC + 22 tests + orchestrator `confluence_section` threading + 3 stress-pass threading tests, zero-diff backward-compat). Round-28 amendments applied (`confluence_engine` → `pocket_skill_reader` rename to avoid collision ; hysteresis 2-pp dead-band on band transitions).

**Round-28 amendment (2026-05-13)** — the original ADR-088 draft proposed naming the new service `services/confluence_engine.py`. Audit revealed that file **already exists** at `apps/api/src/ichor_api/services/confluence_engine.py` with a DIFFERENT purpose (multi-factor "5+ confluences" deterministic score over 10 data-pool signals — rate diff, COT, microstructure OFI, daily levels, Polymarket, narrative, regime, surprise, funding, CB intervention). The two services are orthogonal :

- **Existing `confluence_engine.py`** : factor-aggregation score (long/short/neutral, 0-100). Consumed by trader-grade synthesis.
- **W115c new service** : Vovk-weight pocket skill diagnostic (high_skill / neutral / anti_skill band). Consumed by Pass-3 stress as calibration hint.

To avoid collision, this ADR renames the new W115c service to **`services/pocket_skill_reader.py`** with `PocketSkillReader` class and `PocketSkill` dataclass. The W115c CI guard test asserts `brier_aggregator_weights NOT in Cap5 ALLOWED_TABLES` (ADR-078 forbidden set extension).

**Round-28 hysteresis amendment** — trader-review YELLOW LOW flagged anti-flicker concern at the `skill_delta = ±0.05` boundary : a pocket fluctuating around -0.049 / -0.051 would toggle `anti_skill ↔ neutral` between sessions, triggering on/off addendum injection. **Resolution** : add a hysteresis dead-band : enter `anti_skill` at `skill_delta <= -0.05`, exit `anti_skill` only at `skill_delta >= -0.03` (and symmetrically for `high_skill` at `>= +0.05` / `<= +0.03`). The 2-percentage-point dead-band stabilises the band classification across nightly Vovk fires.

**Date**: 2026-05-13

**Supersedes**: none

**Extends**: [ADR-087](ADR-087-phase-d-auto-improvement-loops.md) (Phase D loops), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary), [ADR-085](ADR-085-pass-6-scenario-decompose-taxonomy.md) (Pass-6 7-bucket).

## Context

ADR-087 shipped four Phase D auto-improvement loops. The Vovk-Zhdanov aggregator (W115) has been **autonomously firing** since 2026-05-13 03:32:39 CEST — 24 pocket-weight rows are stored in `brier_aggregator_weights` reflecting realized skill of three experts (`prod_predictor` / `climatology` / `equal_weight`) per `(asset, regime, session_type)` pocket.

**But these weights are dead-letter.** The 4-pass orchestrator does NOT consume them. The Phase D loop is open :

```
measure (Vovk weights) ✓     →     act (4-pass uses weights) ✗
```

Without W115c, the system knows EUR_USD/usd_complacency is anti-skill (n=13 stat-significant) but cannot adjust its next emission. The same overconfident wrong call will produce the same Vovk weight delta, indefinitely.

The natural close is a **confluence engine** : a service that reads pocket-specific skill diagnostics from `brier_aggregator_weights` and surfaces them as an _optional_ data-pool section consumed by Pass-3 stress reasoning.

## Decision

### Invariant 1 — Read-only side, NO Pass-2 reasoning override

W115c MUST NOT modify Pass-2 asset reasoning. The Vovk weight delta is a **diagnostic** (skill signal), not a **directive** (override the 4-pass P(target*up)). Pass-2 continues to emit its own probability ; W115c only surfaces \_how confident we should be in that probability* via a Pass-3 stress addendum.

Rule 3 (ADR avant code) + rule 4 (frontend gel) compliance : the orchestrator change is additive — one optional kwarg on `Orchestrator.run_4pass(..., confluence_section: dict | None = None)` — and zero impact on existing call paths when `confluence_section is None` (zero-diff baseline test required).

### Invariant 2 — Feature-flag fail-closed (rule 16 ban-risk)

A new feature flag `phase_d_w115c_confluence_enabled` is the gate. When `feature_flags.enabled = false` OR row is absent, `confluence_engine.read_pocket(...)` returns `None` (which the orchestrator threads through as `confluence_section=None`). NO behaviour change in production until the flag is explicitly flipped by Eliot.

### Invariant 3 — Cap5 `query_db` allowlist EXCLUDES `brier_aggregator_weights`

This is the structural analog of ADR-086 invariant 3 : Couche-2 agents MUST NOT directly read Vovk weights via `mcp__ichor__query_db`. The W115c engine encapsulates the read logic, applies any small-sample shrinkage (future work), and emits a sanitised JSON blob. Past-only enforcement, small-sample sanity, and forbidden-token filtering are properties of the service layer, not raw SQL grants.

CI guard test `test_brier_aggregator_weights_excluded_from_cap5_allowlist` (extends `test_tool_query_db_allowlist_guard.py`) asserts the table is NOT in `ALLOWED_TABLES`.

### Implementation shape

```python
# apps/api/src/ichor_api/services/confluence_engine.py
from dataclasses import dataclass

@dataclass(frozen=True)
class PocketConfluence:
    asset: str
    regime: str
    session_type: str
    prod_weight: float
    climatology_weight: float
    equal_weight_weight: float
    skill_delta: float            # prod_weight - equal_weight_weight
    n_observations: int
    confidence_band: str           # "high_skill" / "neutral" / "anti_skill"


async def read_pocket(
    session: AsyncSession,
    *,
    asset: str,
    regime: str,
    session_type: str,
    min_n_observations: int = 5,    # require minimum samples
) -> PocketConfluence | None:
    """Read Vovk weights for the requested pocket.

    Returns None if (a) feature flag disabled, (b) pocket has no row,
    (c) n_observations < min_n_observations (small-sample shielding).

    The caller (orchestrator Pass-3 stress) receives a sanitised
    diagnostic, NEVER a raw weight blob. confidence_band classification :
    - skill_delta >= +0.05 AND n >= 8     → "high_skill"
    - skill_delta <= -0.05 AND n >= 8     → "anti_skill"
    - otherwise                            → "neutral"
    """
    if not await _is_feature_flag_enabled(session):
        return None
    # ... SQL SELECT + Dirichlet shrinkage (optional future)
```

Pass-3 stress narrative receives the `confidence_band` and ONE explicit instruction in the prompt :

```text
[Round-27 Phase D W115c confluence signal]
Pocket (EUR_USD, usd_complacency, london) : anti_skill (n=13, skill_delta=-0.05).
The 4-pass output for this pocket has historically been *less reliable
than equal-weight* on realized outcomes. When evaluating Pass-2's bias
and conviction, weight invalidation risks higher than your default.
```

NO instruction to flip the bias. NO instruction to override conviction. Only a calibration hint.

## Acceptance criteria

1. `services/confluence_engine.py` ships with `read_pocket()` + 8+ unit tests (happy path / flag-off / pocket-missing / n-below-threshold / band classification edges).
2. `orchestrator.run_4pass(..., confluence_section=None)` byte-compatible with current callers (zero-diff baseline test).
3. CI guard `test_brier_aggregator_weights_excluded_from_cap5_allowlist` PASS.
4. Feature flag row insert documented in `docs/runbooks/RUNBOOK-019-phase-d-flags.md` (NEW).
5. `/v1/phase-d/pocket-summary` endpoint extended to surface `confidence_band` per pocket (read-side, no auth change).

## Reversibility

W115c is fully reversible :

- Set `phase_d_w115c_confluence_enabled.enabled = false` → engine returns None, orchestrator zero-diff.
- Delete feature flag row → fail-closed (same effect).
- Revert PR → loses the engine file but Vovk weights persist (no schema change).

## Consequences

### Positive

- **Phase D loop closed** : measure ✓ act ✓ (with calibration hint, not override).
- **EUR_USD anti-skill becomes actionable** : Pass-3 stress can flag low-confidence pockets to Eliot via the addendum injection (round-22 W116c wire).
- **No Pass-2 reasoning override** : keeps the 4-pass primary signal intact, satisfies rule 3 (no architecture creep).
- **Feature-flag-gated rollout** : safe to ship, observe in pre_londres / new_york sessions before flipping.

### Negative

- **Adds one more Sunday cron-adjacent observability surface** : the engine reads at Pass-3 invocation time, which is mid-session (intraday). Performance budget : <5ms per pocket read. SQL is a single PK lookup on `brier_aggregator_weights` (asset, regime, session_type) UNIQUE index.
- **Small-sample shielding `min_n_observations=5` is conservative** : EUR_USD has n=13, GBP_USD n=3. With threshold=5, GBP/usd_complacency is silenced (correct given low evidence). But this means new pockets take time to surface.
- **Future Bayesian shrinkage not in v1** : Dirichlet prior is deferred. Tracked as audit gap.

### Neutral

- **Cap5 allowlist exclusion** is a no-op today (Cap5 STEP-6 prod e2e still pending PRE-1) but locks the invariant for future agentic-loop wiring.

## Next session shipping plan

If Eliot ratifies :

1. Create branch `claude/round-27-w115c-confluence`.
2. Implement `services/confluence_engine.py` (~120 LOC).
3. Add 8 unit tests.
4. Add CI guard test.
5. Thread `confluence_section` kwarg through `orchestrator.py` + `passes/stress.py`.
6. Extend `/v1/phase-d/pocket-summary` endpoint.
7. Author RUNBOOK-019.
8. PR + Eliot review.

Estimated 0.5 dev-days end-to-end.
