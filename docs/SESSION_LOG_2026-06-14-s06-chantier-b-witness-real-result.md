# Session 2026-06-14 — S06 Chantier-B: REAL read-only witness result (Opus 4.8)

> Re-fire #7. Lesson applied (CLAUDE.md ">2x re-fire = step back, don't pile
> more"): instead of a 5th calibration slice, I ran the slice-4 witness on REAL
> production data, READ-ONLY, to produce the runtime proof (prompt ⑥).

## What was run (READ-ONLY, zero mutation)

`ssh ichor-hetzner` (root, prod) → `sudo -u postgres psql -d ichor` SELECT of
`session_card_audit(asset, session_type, bias_direction, conviction_pct,
brier_contribution)` WHERE `brier_contribution IS NOT NULL` ORDER BY
`generated_at`. **No write, no scp, no deploy.** Local dump processed then
deleted. Rebuilt `(p_up, y)` via canonical `conviction_to_p_up` +
`derive_realized_outcome` (neutral cards → skipped), fed `run_calibration_witness`.

- **634 reconciled cards** (2026-05-04 → 2026-06-12); **368 directional**
  (neutral excluded). 86 directional for `pre_ny` (the S06 NY focus).

## Result — a calibration CONCLUSIVELY beats the raw conviction OOS, robustly

POOLED, ALL sessions (368), chronological train/test:

| train_frac | n_test | raw Brier | selected     | sel Brier | beats | conclusive |
| ---------: | -----: | --------: | ------------ | --------: | :---: | :--------: |
|        0.5 |    184 |    0.3079 | isotonic_k=0 |    0.2630 |  yes  |    yes     |
|        0.6 |    148 |    0.3051 | platt        |    0.2520 |  yes  |    yes     |
|        0.7 |    111 |    0.3142 | platt        |    0.2491 |  yes  |    yes     |

Expanding walk-forward (POOLED ALL, 2 folds): fold1 train122/test122 raw 0.2873 →
isotonic 0.2694 (beats); fold2 train244/test122 raw 0.3137 → platt 0.2511 (beats).
`pre_ny` POOLED also beats raw at every split (0.296/0.256/0.239), thinner N.

## Honest interpretation (NO over-claim — this is NOT an edge)

The raw conviction is **over-confident**: mean p_up 0.527 vs mean realised y
0.451; raw Brier 0.283 > 0.25 (no-skill). Reliability diagram:

| p_up bin          |   n | predicted | realised |    gap |
| ----------------- | --: | --------: | -------: | -----: |
| 0.2–0.4 (bearish) | 122 |     0.358 |    0.516 | −0.159 |
| 0.6–0.8 (bullish) | 195 |     0.634 |    0.405 | +0.229 |

On this one month the directional convictions are over-confident and mildly
**anti-predictive** (high-conviction longs realise ~40% up). The calibration's
gain comes from **shrinking the over-confidence toward 0.5** — it pulls the Brier
to ≈ 0.25 (the no-skill line), it does **not** push below it. So:

- **TRUE:** re-calibrating makes the displayed conviction HONEST (kills the
  "long 85 %" that is really ~50 %), and this is a real, conclusive, robust OOS
  Brier improvement (~0.30 → ~0.25) on 368 real cards.
- **NOT TRUE / would be a lie:** that this gives Ichor directional skill. It does
  not. A calibrated ~50 % beats a confidently-wrong 85 %, but it is not a crystal
  ball. The honest read remains: no proven intraday directional edge on this
  window (consistent with the ADR-116 benchmark).

## Decision — informed, but still GATED (owner + deploy)

Wiring `select_calibrator_oos`'s winner into `_derive_direction_and_conviction`
is now **justified as an HONESTY fix** (not an edge), and the data conclusively
supports it. But it stays gated because it is a behaviour change to the live
verdict and a **product call**: a calibrated verdict will honestly say "no strong
directional edge today" most days (convictions collapse toward ~50 %). That is
the truth given the data — but whether to surface it that way is the owner's
decision. NEXT: owner `go` → wire behind a flag + deploy + sustained re-witness;
add walk-forward/k-fold to the witness CLI as hardening (ADR-118/119 Risk).

Branch `feat/s06-chantier-b-conviction-calibration` (PR #243), HEAD at the
slice-4 commit. ssh ichor-hetzner = root@prod, DB read-only via
`sudo -u postgres psql -d ichor`.
