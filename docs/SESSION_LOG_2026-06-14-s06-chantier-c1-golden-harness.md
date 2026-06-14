# Session 2026-06-14 — S06 Chantier C · C-1 golden-fuser diff harness (Opus 4.8)

> Pickup: `go Chantier C C-1` (per the kickoff doc
> `SESSION_LOG_2026-06-14-s06-chantier-c-kickoff.md` and `auto_session_resume.md` NEXT #3).
> Owner re-fire "focus session 6, je t'autorise tout". Model = Opus 4.8 MAX EFFORT (the
> engine model is locked to Opus 4.8 since the 06-11 owner decision; Fable 5 migration
> cancelled — `PLAN_DIRECTEUR.md:78-81`). The session prompts still say "Fable 5"; adapted
> to Opus 4.8 as instructed.

## What shipped (slice C-1) — additive, test-only, ZERO live behaviour change

C-1 is the **prerequisite** for slice C-2 (which adds `votes: Sequence[DimensionVote] = ()`
to `conviction_fusion.fuse_conviction` and threads it through
`session_verdict_builder._derive_direction_and_conviction`). C-2 must be **strictly
additive**: flag OFF (no votes) ⇒ byte-identical output. Until now there was no guard
proving that — exhaustive `golden` greps hit only an academic citation. C-1 is that guard.

Two new files (both untracked / additive; no production code touched):

- `apps/api/tests/test_fuser_golden_harness.py` — the harness:
  - `build_input_matrix()` — 179 deterministic cases: a **behaviour** sub-matrix
    (`EUR_USD` × 11 scenario regimes × 13 evidence combos) + an **asset_sign** sub-matrix
    (9 assets × {usd_up, usd_down} × {full_edge_up, full_edge_down}) pinning every branch
    of `_ASSET_USD_SIGN` (sign −1 / +1 / 0).
  - `serialize_grounding()` — canonical, float-rounded (9 dp) snapshot of all 8
    `ConvictionGrounding` fields.
  - `assert_fuser_golden()` / `assert_derive_golden()` — **reusable equivalence guards
    consumed by C-2** to prove the flag-OFF path is byte-identical to today.
  - `regenerate_golden()` — opt-in (`ICHOR_REGEN_GOLDEN=1`) so CI can never silently
    rewrite the frozen reference.
- `apps/api/tests/golden/fuser_conviction_golden.json` — committed frozen snapshot
  (179 cases, ~80 KB < the 500 KB `check-added-large-files` cap; prettier 3.8.3-clean).

## Branch coverage (exhaustive over the reachable 3-layer fuser)

Hard dead-zone (`≤0.05` + exact `0.05` boundary) → neutral/0 · graded soft-zone
**anchored at 3 points** (spread 0.08→scale 0.30, 0.10→0.50, 0.12→0.70) · full edge ·
cap-95 clamp (reached on 6 cases, e.g. `near_cap_up/all_aligned` 90×1.25→95) · confluence
long/short/neutral/None · theme on/off · dollar usd_up/usd_down/mixed/neutral/None ×
strengths · per-asset sign mapping · lowest reachable `agreement_factor` 0.80 (net_vote −2).

**Documented unreachable with 3 layers** (frozen in C-2 when `votes` extends net_vote):
`AGREEMENT_FLOOR` (0.60, needs net_vote ≤ −4) and the `fused` 0.0-floor. C-2 MUST add the
cases that exercise + freeze them.

## Scope boundary (do not over-rely)

The harness freezes the **fuser surface** (`fuse_conviction` full grounding + the seam's
3-tuple projection), NOT the fully-assembled `SessionVerdict` card (nature, Paris windows,
800-char coach). That is correct for C-1 (the fuser is the surface C-2 edits), but a
C-2/C-3 change OUTSIDE the fuser would slip past — a complementary full-card guard belongs
to C-2/C-3.

## Verification (real runtime, not syntax)

- `pytest tests/test_fuser_golden_harness.py` → **7 passed, 1 skipped** (regen skipped).
- Targeted regression set (harness, `test_invariants_ichor`, `test_architecture_invariants`,
  `test_conviction_fusion`, `test_session_verdict_fusion_seam`) → **90 passed, 1 skipped**.
- Full api suite (pre-edit baseline) → **3512 passed, 35 skipped** (648 s); C-1 edits are
  test-only + additive, so the suite result stands.
- `ruff check` clean · `ruff format --check` clean · `mypy` = only the pre-existing
  `import-untyped` on `ichor_api.services.*` (identical to sibling `test_conviction_fusion.py`;
  `[[tool.mypy.overrides]] module=["tests.*"]` relaxes tests; mypy gate targets `src/` only).
- Determinism proven: re-gen + `diff` byte-identical; SHA stable across
  `PYTHONHASHSEED ∈ {0,1,42,12345}`.
- Two **fresh-context adversarial verifiers** (determinism/coverage + ADR/CI conformity):
  0 blockers. Their majors (soft-zone single anchor; full-card scope) were **fixed** (3
  slope anchors + max-disagreement combo) and **documented** (scope boundary + floor
  unreachability). 7 CI pitfalls all respected (no pinned file touched; ADR-081 trade-token
  guard skips `tests/` + string literals; golden prettier-clean).

## CI pitfalls status (from the kickoff doc)

#1/#2 (pinned strings in builder / `run_session_card`) — untouched. #3 (ADR-081 BUY/SELL)
— the anti-token regex is a string literal in a `tests/` file, exempt by the guard's own
rules (`test_invariants_ichor.py:70,88-105`). #4 (strictly additive) — two new files only.
#5/#6 — N/A (no 4-tuple reorder; no coach text generated). #7 (prettier) — golden run
through prettier 3.8.3, `--check` clean.

## NEXT (C-2, fresh session)

`go Chantier C C-2`: add `votes: Sequence[DimensionVote] = ()` to `fuse_conviction`
(flag-OFF byte-identical — gated by `assert_fuser_golden`), thread it through
`_derive_direction_and_conviction` (gated by `assert_derive_golden`), gate live via DB
`feature_flags` in `build_session_verdict` (NEVER in the pure helpers). Add the cases that
exercise `AGREEMENT_FLOOR` + a complementary full-card guard. Owner gate: merge/deploy.
