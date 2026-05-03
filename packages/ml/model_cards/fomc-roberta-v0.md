# Model card — `fomc-roberta-v0`

## Model details

- **ID**: `fomc-roberta-v0`
- **Family**: RoBERTa-large fine-tuned for FOMC stance classification
- **Upstream model**: `gtfintechlab/fomc-roberta-large` (HuggingFace)
- **Owner**: Ichor central-bank NLP agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/nlp/fomc_roberta.py`

## Intended use

Classify any FOMC statement / minutes / press-conference text segment as
HAWKISH / DOVISH / NEUTRAL with calibrated softmax. Aggregated across long
documents via `aggregate_fomc_chunks()` to produce a `net_hawkish ∈ [-1, +1]`
score that drives:

- Post-FOMC briefings (hawkish-vs-priced delta)
- `CB_HAWKISH_SHIFT` alert when delta vs prior meeting > 0.3

### Out-of-scope

- Trained on 1996-2022 FOMC corpus — does not generalize to ECB, BoE, BoJ
  out of the box. Per-CB models needed (Phase 2+).
- Single-segment classifier; long-doc aggregation is naive averaging — use
  hierarchical attention in Phase 2.

## Inputs / Outputs

- **Input**: text snippet (≤ 512 RoBERTa tokens).
- **Output**: 3-class label + softmax distribution.

## Training data (upstream)

- 1996-2022 FOMC statements + minutes + press conferences, ~14k labeled
  paragraphs by domain experts (per upstream paper).

## Evaluation (upstream-reported)

- Macro-F1 ~ 0.88 on hold-out FOMC 2023.

## Caveats & failure modes

- Concept drift after 2022 — retrain or fine-tune on 2023+ minutes once
  budget allows.
- "Risks weighted to the downside" type language can fool the classifier;
  inspect uncertainty (max softmax < 0.6).
- First call lazy-loads ~1.4 GB of weights — pre-warm before FOMC release
  windows (Wed 2pm ET).

## Aggregator weight

Currently 0 (FOMC events are episodic, no rolling integration yet). Used as
event-driven *signal* not steady-state probability contributor.
