# ADR-040: BOE_TONE_SHIFT + BOJ_TONE_SHIFT alerts + cb_tone_check case-fix

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.d (BoE + BoJ tone)

## Context

Phase 0 (2026-05-06) shipped FOMC_TONE_SHIFT + ECB_TONE_SHIFT via
`services/cb_tone_check.py` using FOMC-Roberta (`gtfintechlab`) for
hawkish/dovish scoring. The architecture was deliberately built to
extend cleanly to BoE/BoJ : the FED-trained model transfers via
zero-shot to other G7 central banks (the underlying hawkish/dovish
lexicon is shared across CB rhetoric).

Two reasons to ship BoE + BoJ now :

1. **2026 BoE pivot is consequential.** Per Pepperstone March 2026
   review, BoE made a unanimous hawkish hold in March 2026 (first such
   in 4.5 years), the explicit easing bias was dropped from February,
   and ING base case is a June 2026 rate hike. Bailey's tone is
   centrist between hawks (Pill, Greene, Mann) and doves (Dhingra,
   Taylor). A tone-shift detector here drives GBP/USD + GBP/JPY
   repricing.

2. **2026 BoJ normalization is multi-year.** Post-2024 NIRP exit + YCC
   end, Ueda's pace of further hikes is the main USD/JPY driver.
   Intervention-risk territory at 158+ (per existing
   USDJPY_INTERVENTION_RISK alert) is a function of BoJ tone — they
   correlate. JPY carry trades unwind on BoJ hawkish surprise.

In addition, a **silent bug** was discovered while implementing this :
the `cb_speeches` table stores mixed-case central_bank values
(`'Fed'`, `'BoE'`, `'BoJ'`, `'ECB'` per the collector) but the
service queries using `cb.upper()` (e.g. `'FED'`). The case mismatch
caused FOMC_TONE_SHIFT to silently no-op for weeks (production logs
on 2026-05-06 showed `cb_tone · no FED speech in last 24 h` repeatedly
despite 16 'Fed' speeches in DB). This ADR includes the case-fix.

## Decision

### Two new catalog AlertDefs

```python
AlertDef("BOE_TONE_SHIFT", warning, "BoE ton shift {value:+.2f}",
         "boe_tone_z", 1.5, "above", ...)
AlertDef("BOJ_TONE_SHIFT", warning, "BoJ ton shift {value:+.2f}",
         "boj_tone_z", 1.5, "above", ...)
```

Same threshold (1.5σ) and direction (above |z|) as
FOMC_TONE_SHIFT / ECB_TONE_SHIFT — pattern uniformity.

### Service extension

`CB_TO_METRIC` extended :

```python
CB_TO_METRIC = {
    "FED": "fomc_tone_z",
    "ECB": "ecb_tone_z",
    "BOE": "boe_tone_z",
    "BOJ": "boj_tone_z",
}
```

The CLI auto-iterates over all keys when `--cb` not specified, so the
existing `register-cron-cb-tone.sh` (Mon..Fri 21:00 Paris) now scans
4 CBs per run instead of just FED.

### Case-insensitive query (silent bug fix)

`_read_recent_speeches` now uses :

```python
where(func.upper(CbSpeech.central_bank) == cb_upper, ...)
```

This is robust to whatever case the collector stores. FOMC_TONE_SHIFT
will start firing again after deploy ; baseline FRED history will
re-populate as runs accumulate.

### FOMC-Roberta as zero-shot transfer

We deliberately do NOT fine-tune a separate BoE-Roberta or BoJ-Roberta
in this v1. Per ICAIF 2024 small-vs-large CB benchmark research, the
hawkish/dovish lexicon is shared across G7 CBs (interest rate, hike,
cut, dovish, hawkish, accommodative, restrictive, tightening, easing,
pause, hold) — these terms are universal in CB rhetoric. FOMC-Roberta
fine-tuned on FOMC will misclassify some BoE/BoJ-specific terminology
("YCC", "shunto", "MPC dissent", "rate gilts") but the *direction* of
hawkish-vs-dovish remains correct.

A v2 could fine-tune per-CB if Eliot observes systematic miss on a
specific BoE/BoJ idiom. The cost is ~$0 (Hugging Face open-source
models) but adds maintenance burden of 4 model files. Defer to v2.

### Source-stamping (ADR-017)

Same as FOMC/ECB — `extra_payload` includes `net_hawkish`,
`n_speeches`, `n_history` for re-derivation. The series_id pattern
`{CB_UPPER}_TONE_NET` continues for fred_observations persistence.

## Consequences

### Pros

- **Closes ichor-trader follow-up #2 of wave 2** : Phase D.5.d shipped.
- **Closes silent bug** : FOMC_TONE_SHIFT will fire correctly post-deploy.
- **Catalog 41 → 43** alertes (Phase D.5 progression : 10/12).
- **Reuses existing infrastructure** : same FOMC-Roberta model, same
  cb_speeches collector (52 BoE + 50 BoJ rows already in DB),
  same register-cron-cb-tone.sh (just iterates more CBs now), same
  fred_observations persistence path.
- **G7-coverage parity** : Fed + ECB + BoE + BoJ = the four pillar CBs
  for FX/macro trading. PBoC remains explicitly excluded (Chinese
  CB rhetoric is opaque, FOMC-Roberta would systematically misclassify).

### Cons

- **Zero-shot transfer accuracy is unmeasured for BoE/BoJ** at v1 ship.
  The FOMC-Roberta model has 80%+ accuracy on FOMC corpus per
  gtfintechlab benchmarks but no published BoE/BoJ benchmark exists.
  Mitigation : the alert fires on z-score against a 90d trailing
  baseline of the model's *own* output. As long as the model's bias
  is *consistent* (systematically over- or under-hawkish), the relative
  z-score remains informative even with absolute miscalibration.
- **Speech volume sparseness** : BoJ publishes ~2 speeches/week,
  BoE ~3-4/week. The 24h lookback means many days have 0 speeches.
  Not a bug — the alert silently no-ops on those days (CbToneResult
  with `n_speeches=0` and structured note).
- **Vocabulary drift** : YCC, shunto-wages, "Outlook for Economic
  Activity and Prices" — BoJ-specific. Roberta-FOMC was trained on
  pre-2023 FOMC minutes which don't include these terms. Initial
  z-scores may be biased high or low for ~30-90d as the trailing
  baseline absorbs the BoJ-specific tone register.

### Neutral

- BoE / BoJ tone alerts join the same daily 21h Paris cron as FOMC/ECB.
  No new register-cron needed. No new infrastructure.

## Alternatives considered

### A — Fine-tune separate BoE-Roberta / BoJ-Roberta models per CB

Tabled (not rejected) for v2 : technically defensible (better accuracy),
operationally costly (4 model files in `packages/ml`, training
pipeline, CI artifacts). Zero-shot transfer is the practical v1 choice
per ICAIF 2024 benchmark.

### B — Use VADER lexicon instead of FinBERT

Rejected : per ACM ICAIF 2024 small-vs-large CB benchmark, VADER
underperforms FinBERT-FOMC and Llama-3-70B significantly on CB
communication classification. FOMC-Roberta is the right floor.

### C — Use Llama-3-70B / GPT-4 for tone scoring

Rejected for v1 : violates ADR-009 Voie D (no paid API in production)
+ adds Couche-2 dependency to alert path. FOMC-Roberta is fully
local + free. v2 could route via local llama.cpp if Eliot wants
better accuracy.

### D — Hardcode BoE / BoJ MPC vote splits as features

Rejected : MPC vote tally requires structured parsing of post-meeting
minutes, not yet wired. Deferred to v2 as a complementary signal.

### E — Skip the case-fix and live with the silent bug

Rejected : the bug had been silent for ~2 weeks. Fixing it as part of
this PR is the simplest path. The blast-radius is low (FOMC starts
firing alerts again, which is the correct behavior).

### F — Defer BoE / BoJ until corpus-specific fine-tuned models are built

Rejected : zero-shot transfer is enough to ship v1 and gather signal.
Holding back v1 for v2-quality is "perfect is enemy of good". 2026
BoE pivot is happening NOW (March hawkish hold, June expected hike) ;
not having a BoE alert during the most consequential window in 4.5y
is the bigger cost.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/cb_tone_check.py` (extend
  CB_TO_METRIC + case-insensitive query)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with 2 AlertDefs +
  bump assert 41 → 43)
- `apps/api/tests/test_cb_tone_check.py` (4 new tests : BOE wired,
  BOJ wired, threshold constants for all 4 CBs, unmapped CB still
  PBoC after BOJ became wired)
- `docs/decisions/ADR-040-boe-boj-tone-shift-alerts.md` (this file)

No new register-cron : the existing `register-cron-cb-tone.sh` already
iterates over `CB_TO_METRIC` keys, so adding BOE/BOJ to the dict
auto-extends the cron coverage.

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-009 — Voie D (no paid API consumption — FOMC-Roberta is free).
- ADR-024 — 5-bug session-cards fix (event-loop hot pattern reused
  in cb_tone_check CLI).
- ADR-033 — DATA_SURPRISE_Z (sister Phase D.5 alert).
- ADR-036 — GEOPOL_FLASH (sister Phase D.5.b alert).
- ICAIF 2023 FinBERT-FOMC Sentiment Focus method (Cao et al.).
- ICAIF 2024 small-vs-large CB benchmark (FinBERT-FOMC vs Llama-3 vs
  GPT-4 comparative accuracy).
- gtfintechlab/FOMC-Roberta-Hansen-McMahon (Hugging Face model card).

## Followups

- v2 : per-CB fine-tune (BoE-Roberta on BoE corpus, BoJ-Roberta on
  BoJ corpus). Measurable accuracy gain ; maintenance cost ~4 model
  files.
- v2 : MPC vote-tally feature engineering (BoE specifically — vote
  splits are a strong leading indicator).
- v2 : BoJ shunto wage-negotiation calendar flag (March each year).
- v2 : weight aggregation by speaker importance (Bailey > external
  members for BoE, Ueda > external members for BoJ).
- v2 : differentiate scheduled MPC press conference from ad-hoc
  speech for proper signal weight.
- Capability 5 ADR-017 followup : Claude tools runtime can fetch the
  exact MPC vote split at alert time and produce a 1-paragraph
  hawkish/dovish narrative grounded in named members.
