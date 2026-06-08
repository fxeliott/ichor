# Session log — 2026-06-09 — S04 TIER-2 #3: per-asset geopolitics (data-pool section)

> 2nd atomic gap of the day (after the RVOL volume layer). Same discipline: one
> gap, dedicated branch, CI→merge→deploy→witness.

## Context

`_section_geopolitics(session)` took no `asset` param → the 4-pass brain read an
**identical geopolitics block for all 5 assets**. The `/v1/geopolitics/briefing`
router already filtered GDELT per-asset (r138, `filter_rows_by_asset_affinity`),
so the brain (the consumer that matters for the verdict) lagged the panel.

## What shipped (PR #206, `b738ab9`)

`_section_geopolitics(session, asset=None)`:

- **AI-GPR** stays the GLOBAL geopolitical-risk index (single-index doctrine,
  unchanged per asset).
- **GDELT** negative-event cluster narrowed to the asset's conversation via
  `filter_rows_by_asset_affinity` (key = title + query_label + domain + url,
  `min_required=3`, scarce→global fallback) — byte-faithful to the router's
  `_gd_key`. Candidate pool aligned to the router (`top×8 = 40`) for brain↔panel
  parity (closed an adversarial-review nit, commit `5abcbf9`).
- `asset` wired through from `build_data_pool`; `asset=None` keeps global back-compat.
- 7 tests (`test_geopolitics_per_asset.py`): EUR vs XAU produce different blocks,
  applied-header, scarce fallback, GPR global-invariant, no-asset back-compat,
  GPR-absent degraded. ruff clean, mypy 0 new, independent review = CLEAN.

## Runtime witness (criterion ⑥) — HONEST result

Ran `_section_geopolitics` on the LIVE prod DB for EUR_USD / XAU_USD / NAS100_USD:

- The section runs **per-asset** (matched counts differ: EUR=1, XAU=0, NAS=1) — the
  plumbing is live and correct, AI-GPR identical (113.9) across all.
- BUT on the current 24h GDELT window **every asset fell back to global** (matched
  0–1 < min_required 3) → the rendered clusters are currently IDENTICAL.

**Honest conclusion**: the code gap is closed (per-asset + router parity, deployed),
but the _observable_ differentiation is **DATA-GATED** — it activates only when GDELT
carries ≥3 asset-matching events in 24h. The current window is sparse (generic macro
events, tone≈0). The fallback is correct by design (better than a noisy 1-event list).

## The real lever (next, separate gap)

Routine per-asset geopolitical differentiation needs **richer per-asset GDELT queries**
at the collector level (Session-03 concern) — e.g. asset-tagged geopolitical query
labels (iran-conflict→XAU, ecb→EUR, tariffs→indices). This section will differentiate
automatically once that density exists. Not a defect in this section.

## Invariants held

ADR-017 (keywords content-neutral, CI-guarded; `is_adr017_clean` asserted) · Voie-D
(0 Anthropic spend) · brain↔panel parity (same key/threshold/fallback as the router).
