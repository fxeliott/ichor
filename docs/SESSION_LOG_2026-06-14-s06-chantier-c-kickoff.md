# Session 2026-06-14 — S06 Chantier C kickoff + execution plan (Opus 4.8)

> Owner decision (re-fire #9): "je veux le plus honnête affiché → go pousser
> Chantier C pour un 85 % honnête". The ADR-116/118 witness proved the conviction
> has no edge (over-confident → calibration shrinks it to ~50 %). The ONLY path
> to a _legitimate_ high conviction is a smarter verdict: fuse ≥ 9 dimensions.
>
> Context was 9 prompt-re-fires deep, so per prompt §② (context-budget → fresh
> window) only the safe FOUNDATION shipped this turn; the delicate slices are
> sequenced below for a fresh-context execution to keep the 0-bug bar.

## Shipped this turn (slice-0) — branch `feat/s06-chantier-c-dimension-votes`

`services/dimension_vote.py` (ADR-120): the canonical `DimensionVote` contract +
pure aggregation helpers. Stdlib-only (fuser-importable), enforces ADR-017 (no
tilt for non-directional), ADR-103 (absent → 0), ADR-022 (signed ∈ [-1,+1]). 20
tests, ruff + mypy clean, fresh-verified, NOT wired. PR to open.

## Current verdict-fusion seam (verified at source, main = 12d7623)

- `conviction_fusion.fuse_conviction` (`conviction_fusion.py:221`) — pure,
  stdlib-only, takes the 3 current layers (confluence directional ±1×weight,
  dollar consensus×`_ASSET_USD_SIGN`×strength, theme non-directional +0.5),
  nets a vote → agreement factor ∈ [0.60, 1.25] → conviction clamped [0, 95].
  Constants are principled priors (`DEAD_ZONE_HARD/SOFT`, `VOTE_GAIN_K`, …).
- Read seam: `session_verdict_builder.py` `_extract_synthesis_primitives`
  (4-tuple POSITIONAL) → `_derive_direction_and_conviction` → `fuse_conviction`.
- Write seam: `run_session_card.py` `_capture_synthesis_snapshots` freezes the 3
  JSONB snapshots on `session_card_audit` (migration 0055).

## Execution plan (sequenced — fresh session, one slice = one PR)

**C-1 · Golden-card diff harness (PREREQUISITE, does NOT exist).** Before
touching the fuser, build the equivalence guard so the migration is provably
byte-identical when the flag is OFF. Two options (blueprint): (a) a full
deterministic stub-session that runs `build_data_pool` (~58 async calls to stub)
— big; (b) a lockstep old-vs-new equivalence test on the same stubs at each
extraction (pattern `FRENCH_COACH_DIRECTIVE`, 4 lockstep brain tests). Prefer (b)
to start. Gate: same inputs → byte-identical `card_verdict`.

**C-2 · Fuser accepts `Sequence[DimensionVote]` (ADDITIVE, flag-OFF byte-id).**
Add a `votes: Sequence[DimensionVote] = ()` param to `fuse_conviction`; when
empty (flag OFF) behaviour is byte-identical (the 3 legacy kwargs still drive
it). When populated, `net_dimension_vote` + `total_uncertainty_credit` feed the
SAME agreement-factor math (`VOTE_GAIN_K`, `AGREEMENT_FLOOR/CEIL`). Gate via the
existing DB `feature_flags` (`services/feature_flags.py`, `is_enabled` async) in
`build_session_verdict`/`_run`, NEVER in the pure helpers.

**C-3 · Wire the real dimensions (ONE at a time, golden-diff each).** Map the
S04 layers already captured (confluence/theme/dollar) onto `DimensionVote`, then
add: rates/curve, positioning (COT/TFF), geopolitics (GPR — see blueprint's
web-verified doctrine: threats≠acts, percentile non-linearity, conditional USD),
volume/RVOL, breadth/correlation, volatility regime, calendar/event proximity.
Target ≥ 9. Each: write-side capture beside `_capture_synthesis_snapshots`, one
JSONB column `dimension_votes` (ONE migration, DB backup first).

**C-4 · Risk agent + Bull/Bear adversarial synthesis** (the other half of §4bis):
a risk-veto layer and a structured bull-case/bear-case that the fuser reconciles.

**C-5 · Honest-display wiring (owner-greenlit).** Once dimensions earn real edge,
wire the OOS-selected calibrator (`select_calibrator_oos`, ADR-118) into
`_derive_direction_and_conviction` behind a flag → the displayed conviction is
honest AND can legitimately be high. Deploy + re-witness.

## 7 CI pitfalls (verified — MUST respect)

1. `test_architecture_invariants.py:51-55,113-130` pins the strings
   `conviction_fusion`/`fuse_conviction`/`_extract_synthesis_primitives` inside
   `session_verdict_builder.py` (substring on file text).
2. `:133-148` forbids `read_pocket`/`confluence_section` tokens in
   `run_session_card.py` EVEN IN COMMENTS.
3. ADR-081 pre-commit: BUY/SELL tokens forbidden + `le=95.0` pinned.
4. Pinned values: `test_conviction_fusion.py:60,70,79,128,177` +
   `test_session_verdict_fusion_seam.py:107` → C-2 must be strictly additive,
   NO reweighting (flag-OFF byte-identical).
5. 4-tuple `_extract_synthesis_primitives` consumed POSITIONALLY — EXTEND, never
   reorder.
6. coach_explanation 800-char cap (seam test :186).
7. Prettier drift: pre-commit prettier = v4.0.0-alpha.8, CI = 3.8.3 — run
   `npx prettier --write` (3.8.3) on new `.md` before push or the Node CI goes
   red (cost us a turn; ideally fix `.pre-commit-config.yaml` to a local 3.8.3
   hook).

## Pickup (fresh session)

`/clear` → `/pickup-ichor` (or "go Chantier C C-1: golden-card diff harness").
main = 12d7623 (S06 Chantier A+B merged + deployed, healthz ok). slice-0 on
branch `feat/s06-chantier-c-dimension-votes`. ssh ichor-hetzner = root@prod, DB
read-only `sudo -u postgres psql -d ichor`.
