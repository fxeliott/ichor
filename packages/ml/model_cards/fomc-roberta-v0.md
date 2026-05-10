# Model card — `cb-stance-multi-cb-v1` (formerly `fomc-roberta-v0`)

## ⚠️ Migration note (2026-05-07, PR #34, ADR-040)

This card was originally written for `fomc-roberta-v0` based on the
upstream `gtfintechlab/fomc-roberta-large` model. That upstream was
**deprecated and removed from HuggingFace Hub** in 2025 when the
gtfintechlab team published their **2025 multi-CB series** — per-CB
fine-tuned RoBERTa-base models, ~0.4B params each, with a 4-class label
including IRRELEVANT.

Per ICAIF 2024 small-vs-large CB benchmark, **per-CB fine-tuned models
outperform single-CB zero-shot transfer by ~5-10pp on out-of-domain
corpus**. So this migration is a **strict capability upgrade**, not just
a model rename.

## Model details (current)

- **Active ID**: `cb-stance-multi-cb-v1`
- **Family**: 4 per-CB RoBERTa-base classifiers (one per supported CB)
- **Upstream models** (CB_MODEL_REGISTRY):
  - `FED` → `gtfintechlab/model_federal_reserve_system_stance_label`
  - `ECB` → `gtfintechlab/model_european_central_bank_stance_label`
  - `BOE` → `gtfintechlab/model_bank_of_england_stance_label`
  - `BOJ` → `gtfintechlab/model_bank_of_japan_stance_label`
- **License**: CC-BY-NC-SA 4.0
- **Owner**: Ichor central-bank NLP agent
- **Status**: shipped (PR #34, ADR-040, 2026-05-07)
- **Implementation**: `packages/ml/src/ichor_ml/nlp/fomc_roberta.py`
  (path kept for backward-compat ; multi-CB internally)

## Intended use

Per-CB stance classification with a 4-class label : NEUTRAL / HAWKISH /
DOVISH / IRRELEVANT. The IRRELEVANT class is the key v1 improvement
over the legacy 3-class FOMC-only model — sentences that aren't about
monetary policy (boilerplate, biographical, procedural) are filtered
out of `aggregate_fomc_chunks` net_hawkish aggregate rather than
diluted into NEUTRAL.

Drives:

- `FOMC_TONE_SHIFT` alert (FED model)
- `ECB_TONE_SHIFT` alert (ECB model)
- `BOE_TONE_SHIFT` alert (BOE model, NEW Phase D.5.d)
- `BOJ_TONE_SHIFT` alert (BOJ model, NEW Phase D.5.d)

### API entry points

- `score_text_for_cb(text, cb='FED')` — classify a single short paragraph
- `score_long_text_for_cb(text, cb='FED')` — chunk + score long CB text
- `aggregate_fomc_chunks(scores)` — produce `net_hawkish ∈ [-1, +1]`
  excluding IRRELEVANT chunks
- Backward-compat shims preserved : `score_fomc_tone()`, `score_long_fomc_text()`
  default to FED model

### Out-of-scope

- Other CBs (PBOC, SNB, RBA, RBI, MAS) — `gtfintechlab` publishes models
  for these too ; can be added to `CB_MODEL_REGISTRY` in v2 if Eliot
  trades those rate paths.
- Numeric reasoning (rate-projection deltas) — same as legacy model,
  the classifier captures _direction_ not magnitude.

## Inputs / Outputs

- **Input**: text snippet (≤ 480 RoBERTa-base tokens after chunking).
- **Output**: 4-class label (NEUTRAL/HAWKISH/DOVISH/IRRELEVANT) + softmax.
- **Aggregate output (long texts)**: `net_hawkish ∈ [-1, +1]` computed
  on RELEVANT-only chunks (IRRELEVANT excluded).

## Training data (upstream gtfintechlab)

- Per-CB labeled corpora (each CB has its own dataset on HuggingFace
  Hub : `gtfintechlab/federal_reserve_system`, `gtfintechlab/european_central_bank`,
  `gtfintechlab/bank_of_england`, `gtfintechlab/bank_of_japan`).
- Each corpus = manually-labeled paragraphs from the respective CB's
  speeches/statements/minutes.

## Evaluation (upstream)

- Per-CB models : not yet benchmarked against a unified test set in
  the open literature. ICAIF 2024 benchmark establishes per-CB
  fine-tuning > zero-shot at family level. Per-model accuracy specifics
  see HuggingFace model cards.

## Caveats & failure modes

- **Per-CB vocabulary drift** : BoJ-specific terminology (YCC,
  shunto, JGB) is in BoJ corpus ; BoE-specific (MPC dissent, gilts,
  Bailey) in BoE corpus. Cross-CB leakage minimal because we route
  per-CB.
- "Risks weighted to the downside" type ambiguous language can still
  confuse classifiers — inspect max-softmax confidence < 0.6.
- First call per CB lazy-loads ~0.4 GB of weights (lru_cache(maxsize=4)
  keeps all 4 in RAM after first run). Pre-warm before CB release
  windows.
- **2026-05-07 silent prod bug discovered + fixed** : the
  `cb_speeches.central_bank` column stores mixed-case values
  (`'Fed'`, `'BoE'`, `'BoJ'`, `'ECB'`) but `cb_tone_check.py` was
  querying with `cb.upper() == 'FED'` etc. Case mismatch → silent
  zero-row return → FOMC_TONE_SHIFT no-firing for ~2 weeks. Fixed
  in PR #32 with `func.upper(...)` case-insensitive query.

## Aggregator weight

`net_hawkish` is wired into `cb_tone_check.py:_aggregate_fomc_chunks` →
`fred_observations.{CB}_TONE_NET` daily series → `{CB}_TONE_SHIFT`
alerts via 90d rolling z-score.

## Migration history

- **2025-Q3** : `fomc-roberta-v0` scaffold added (upstream
  `gtfintechlab/fomc-roberta-large`) — Phase 0 W2 step 13.
- **2025-Q4** : gtfintechlab deprecated `fomc-roberta-large` in favor
  of per-CB 2025 series. Ichor unaware until live deploy 2026-05-07.
- **2026-05-07** : PR #34 migration to `cb-stance-multi-cb-v1`.
  Backward-compat shims preserved. ADR-040 + ADR-017 boundary
  documented.
