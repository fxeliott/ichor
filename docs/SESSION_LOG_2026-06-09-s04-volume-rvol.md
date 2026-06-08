# Session log — 2026-06-09 — S04 TIER-2 #2: real RVOL / volume-spike depth layer

> Closes the highest-leverage **mechanical** gap from `docs/S04_FINALIZATION_PROGRAM.md`
> (TIER-2 #2, [high]). One atomic gap, dedicated branch, CI→merge→deploy→witness.

## Context

S04 (multidimensional analysis engine) was 9/9 dimensions WIRED + 50/50 killed,
but 0/9 « maxed » against the spec bar « chaque dimension poussée au maximum, sans
zone d'ombre ». The Volume dimension was the weakest: volume was consumed only as a
**weight** (Amihud / Kyle / VWAP / value-area) and a sign (Lee-Ready OFI) — the brain
had no read of participation **magnitude** (« is today's volume light, normal, a spike
vs its own history? »).

## What shipped (PR #204, `4f3fa94`)

A daily relative-volume / participation layer:

- **`microstructure.py`** — pure-stdlib, no I/O:
  - `RelativeVolumeReading` (frozen): `volume_available`, `latest_date`,
    `current_volume`, `avg_volume`, `rvol_ratio`, `volume_zscore`, `n_history`, `bucket`.
  - `classify_relative_volume(daily_volumes, *, asset, latest_date, volume_available)`
    — RVOL ratio (current / trailing 20d avg) + 60d volume z-score (byte-faithful
    mirror of `dollar_smile_check._zscore`: ≥60 history floor + zero-std guard) +
    non-directional participation bucket (`very light` → `below-average` → `average`
    → `elevated` → `volume spike`). Degenerate inputs (empty / non-positive current /
    insufficient history) return None metrics + an honest bucket, never raise.
  - `assess_relative_volume(session, asset)` — queries `market_data` daily bars,
    dedups `(asset, bar_date)` across sources (keeps max positive volume), drops
    None/≤0.
  - `render_relative_volume_block(reading)` — descriptive markdown + sources.
- **`data_pool.py`** — `_section_volume_rvol` (3-tuple `(md, sources, degraded)`,
  liveness-gated like `_section_cot`), wired into `build_data_pool` (sibling of
  `_section_microstructure`) + `build_asset_data_only`. `_VOLUME_ASSETS =
{SPX500_USD, NAS100_USD, XAU_USD}`, `_VOLUME_RVOL_MAX_AGE_DAYS = 5`.

## Scope decision (empirically witnessed prod 2026-06-08 via SSH)

`market_data` (source=yfinance) volume>0 coverage: SPX500 2539/2540, NAS100 2540/2540,
XAU 2502/2539 (GC=F gold-futures volume) → **RVOL feasible**. EUR/GBP/JPY/AUD/CAD = 0
→ FX no consolidated venue volume → **honest N/A by data property, zero DB I/O**
(not a degraded source). `polygon_intraday` rejected as the baseline source: NAS100→
I:NDX reports **0** intraday volume, and the table has too-shallow history for a
rolling daily average. Empirical witness **expanded** scope vs the audit's
"SPY/NDX-only" assumption — gold is in.

## Invariants held

- **ADR-017**: descriptive only — participation magnitude, never a direction (a spike
  has no sign). `is_adr017_clean(md)` asserted on every render variant.
- **Liveness / « sans zone d'ombre »**: every asset gets an explicit answer — a value,
  an honest FX N/A, or an ABSENT/STALE band + degraded trace. No silent n/a.
- **Voie-D**: zero Anthropic API spend.

## Verification

- pytest: 30 new (`test_relative_volume.py`) + regression green (microstructure,
  data_liveness, tff_cot coverage, ADR-081 invariants, data_pool\*).
- ruff check + format clean; mypy 0 new (16 pre-existing `data_pool.py` baseline,
  proven via stash); pre-commit (gitleaks/ruff/ADR-081) green; CI 100% green.
- Independent `code-reviewer` subagent verdict: READY TO MERGE (no blocking, no
  important) — one defensive nit (non-positive `current` guard) closed in `9ead744`.
- **Runtime witness (criterion ⑥)** — `_section_volume_rvol` on the LIVE prod DB
  post-deploy: SPX500 RVOL 0.88× (z −1.3), NAS100 0.96× (z −1.2), XAU 1.03× (z +1.2),
  all « average participation », `degraded=[]`; EUR_USD honest N/A. Real values.

## Remaining (S04, for Eliot / next sessions)

- **Decision (Eliot, semantic)**: UST (TFF 2/5/10/30Y) → SPX/NAS rate-sensitivity
  mapping (TIER-2 #4). Mechanical guard `consumer ⊆ collector` only freezes the
  current invariant.
- **Decision (Eliot, architecture)**: Couche-1 ZERO model fallback (SPOF Win11
  runner) — premium-only fail-loud vs degraded Cerebras/Groq path.
- TIER-2 depth, lower-leverage: per-region EZ/UK/JP surprise; per-asset
  manipulation-magnet synthesis; sentiment/volume orphans (CRYPTO_FNG, FinraShortVolume);
  COT headerless parser (nice-to-have, TFF already covers positioning).
- TIER-3: async-DB integration test for the verdict fusion seam.
