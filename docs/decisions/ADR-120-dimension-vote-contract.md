# ADR-120 — DimensionVote contract (Chantier C slice-0)

- **Status:** Accepted (pure-core contract, NOT wired) — 2026-06-14
- **Deciders:** owner (explicit "go pousser Chantier C pour un 85% honnête"), engine (Opus 4.8)
- **Related:** ADR-017 (direction from buckets only) · ADR-103 (honest absence) ·
  ADR-022 (cap-95) · ADR-009 (Voie D) · `services/conviction_fusion.py` ·
  PLAN_DIRECTEUR §4bis (≥9 dimension votes) · ADR-116/118 (calibration witness)

## Context

The ADR-116/118 witness proved the verdict conviction has no directional edge on
the realised data — it is over-confident, and honest calibration shrinks it to
~50 %. The owner's chosen path to a _legitimate_ high conviction ("un 85 %
honnête") is therefore **Chantier C: a smarter verdict** — fuse ≥ 9 analysis
dimensions (vs the current 3: confluence / dollar / theme) so a high conviction
is _earned_, not manufactured.

Chantier C is a delicate multi-slice migration (golden-card diff equivalence + 7
pinned-CI pitfalls per the slice-1 blueprint). Its FOUNDATION — the canonical
vote contract every dimension emits — is a small, pure, additive, zero-risk
piece that can land first and frame the rest. That is this slice (slice-0).

## Decision

Add `services/dimension_vote.py` — a stdlib-only `DimensionVote` frozen dataclass

- pure aggregation helpers. Stdlib-only because the fuser refuses pydantic /
  `ichor_brain` imports (`conviction_fusion.py` imports only `collections.abc` /
  `dataclasses` / `typing`); the contract must be importable there without
  breaking that purity.

Contract (PLAN §4bis): `provenance`, `direction_hint` (up/down/neutral),
`strength` [0,1], `freshness` [0,1], `honest_absence`, `directional`.

- `signed_contribution() ∈ [-1, +1]` = `sign(dir) · strength · freshness`; `0`
  for neutral / non-directional / absent / stale. Mirrors the existing
  confluence/dollar signed-vote shape so fuser integration is purely additive.
- `uncertainty_credit() ∈ [0, 1]` — the non-directional anti-uncertainty term
  (mirrors `THEME_PRESENCE_VOTE`); a present neutral/non-directional layer
  attests "a real driver exists" without tilting direction (ADR-017).
- `net_dimension_vote` / `total_uncertainty_credit` / `effective_provenances`
  aggregate across dimensions.

**Invariants enforced:** ADR-017 (`__post_init__` rejects a non-directional vote
with a non-neutral hint; signed contribution is 0 for non-directional/neutral),
ADR-103 (absent → exactly 0, both terms), ADR-022 (signed ∈ [-1,+1] by
construction), fail-closed bounds on strength/freshness.

**Scope: contract only. NOT wired.** Extending `fuse_conviction` to accept
`Sequence[DimensionVote]` is the next GATED slice (flag-off byte-identical,
behind a golden-card diff harness). See the Chantier C plan in
`docs/SESSION_LOG_2026-06-14-s06-chantier-c-kickoff.md`.

## Consequences

- **+** The ≥9-dimension fusion has a clean, tested, doctrine-safe foundation;
  every future dimension emits the same shape with explicit provenance + honest
  absence.
- **+** Pure-core (20 tests), zero CI-pitfall surface (new file, touches no
  pinned seam), zero behaviour change (imported by nothing live), Voie-D.
- **−** No effect until the fuser integration slice lands (gated).
- **Risk:** the contract may need a field as real dimensions are wired; kept
  minimal + additive to limit churn.

## Gate (pass/fail)

slice-0: `DimensionVote` enforces ADR-017/103/022, `signed_contribution` ∈
[-1,+1], absent → 0, aggregation helpers correct; ruff + mypy + 20 tests green.
**(Met.)** Fuser integration: a later flag-gated slice behind golden-card
diff-equivalence.
