# SESSION LOG — 2026-06-14 · S06 Chantier C · C-3 slice-0 (COT DimensionVote producer)

> Model: Opus 4.8 (interactive). Re-fire #10 of the Session 06 prompt
> ("focus session 6, traite tout, je t'autorise tout, decide seul").
> Doctrine applied (CLAUDE.md ">2x = build the named NEXT, don't re-deliberate"):
> took the documented NEXT (Chantier C-3) and shipped a pure-core slice; ZERO
> decision menu.

## What shipped (commit `dcda8bb`, branch `feat/s06-c3-cot-vote-producer`, NOT pushed)

The **first real `DimensionVote` producer**. `dimension_vote.py` (slice-0/ADR-120)
defined the contract; `fuse_conviction(votes=...)` (C-2a) opened the seam; neither
shipped a producer. This does.

- **NEW** `apps/api/src/ichor_api/services/cot_vote.py` — pure-core, I/O-free
  `build_cot_vote(...) -> DimensionVote`. Maps CFTC COT managed-money positioning
  primitives (the data `data_pool._section_cot` already collects) into one bounded,
  honest vote (`provenance="cot"`). stdlib + `dimension_vote` import only.
- **NEW** `apps/api/tests/test_cot_vote.py` — 33 tests (directional read, per-asset
  polarity, OI-normalised strength, 1-week-inflection dampening, freshness decay,
  every honest-absence gate, construction safety, fuser integration flag-ON).

**Strictly additive — zero edit to existing prod code** → the C-1 golden harness
(179 cases) is byte-identical by construction (re-ran: `test_fuser_reproduces_golden`

- `test_derive_seam_matches_golden` PASS). Full suite **3559 passed / 35 skip** (was
  3527 → +33 = my new tests, zero regression). ruff + mypy clean. pre-commit ADR-081
  doctrinal invariants + gitleaks Passed.

## Trading doctrine (web-verified 2026-06-14, fresh researcher subagent)

Sources: cftc.gov (data defs, % of OI report field, Tue→Fri release) ·
metalcharts.org · luna3.ai · wallstreetcourier.com · tradealgo.com · forexfundamentals.com.

- **Flow = momentum, not contrarian.** Direction = `sign(Δ4w managed_money_net)`
  (funds building a position), mapped to the asset. Contrarian only at extremes.
- **Per-asset polarity** (`_COT_ASSET_SIGN`): EUR/GBP/AUD/XAU/NAS100 = +1;
  **USD_JPY / USD_CAD = −1** (the COT contract is the foreign-currency future, so a
  managed-money long there = short USD = pair DOWN — matches the "reverse polarity"
  comments at `data_pool.py:196,198`). Decoupled from `_ASSET_USD_SIGN` on purpose.
- **1-week contradiction of the 4-week trend** → dampen strength ×0.5 (inflection,
  never a one-week flip).
- **3-year COT-Index extreme (≥90 / ≤10)** → abstain (momentum sign unreliable).
  Encoded as an OPTIONAL `cot_index_pct` param, **dormant** (None) until a 3-year
  history is carried — slice pulls only ~13 weekly rows today. Conservative strength
  cap (OI-normalised, full strength only at a 10% OI 4-week swing) bounds the damage
  of an undetected extreme.
- **OI normalisation**: `|Δ4w| / open_interest` ("% of OI" is an official CFTC field).

## Invariants

ADR-017 (vote tilts conviction MAGNITUDE via the agreement factor, never the
bucket-derived direction) · ADR-103 (honest_absence → contributes EXACTLY 0:
asset off-whitelist incl. SPX500, empty/stale table, no OI, short history,
sub-1%-OI noise floor, detected extreme) · ADR-022 (`strength` clamped [0,1]) ·
ADR-009 (pure, zero I/O / LLM / spend).

## Verification (3 fresh subagent waves, fresh context)

1. **Map** (workflow `wf_4b1e7c24`, 5 parallel `Explore`): fuser seam / DimensionVote
   contract / golden harness / available S04 dimensions / CI guards — all at file:line.
   Picked COT as the lowest-CI-risk first directional dimension.
2. **Doctrine** (`researcher`): COT interpretation fact-check (above).
3. **Adversarial verify** (`verifier`): 8 attack vectors (polarity bug, direction-flip
   ADR-017, ValueError on construction, zero-div/None, doctrine misencoding,
   byte-identity, test rigor, CI guards) — **0 blocker / 0 major, DECISION OK**.
   1 MINOR (defensive zero-flow guard against a future noise-floor lowering) →
   **applied** (`if asset_dir == 0: return _absent_vote()`) + test
   `test_zero_flow_guard_abstains_even_if_noise_floor_lowered`.

## Honest framing (zero hallucination)

This does NOT create directional edge — the prod witness (S06 benchmark, this month)
showed the apex verdict has no proven edge over naive persistence. C-3 makes the
conviction **more grounded / motivated** (a 4th independent dimension can corroborate
or contradict, with provenance), which is the "verdict plus intelligent" vision — it
does not, by itself, make Ichor predictive. Earned conviction, not manufactured.

## NEXT (gated owner / fresh session)

- **C-3b** (gated): wire `build_cot_vote` live — extract the COT primitives from
  `CotPosition` rows inside `build_session_verdict` (async/DB path) behind a
  `feature_flags` gate; add the `_FR_LAYER_NAMES["cot"]` French label; full-card
  golden guard; deploy + witness. Needs owner merge of the C-1/C-2a/#244 stack first.
- **C-3 next dimensions** (same pattern, one at a time, golden-diff each): rates
  (non-directional context), volume/RVOL (magnitude), geopolitics/GPR (complex,
  percentile-gated — see `ichor-chantier-c-slice1-blueprint`).
- **3-year COT history** to activate the extreme-abstain branch (`cot_index_pct`).
