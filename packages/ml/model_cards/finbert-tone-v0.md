# Model card — `finbert-tone-news-v0`

## Model details

- **ID**: `finbert-tone-news-v0`
- **Family**: BERT fine-tuned for financial sentiment
- **Upstream model**: `yiyanghkust/finbert-tone` (HuggingFace, Apache-2.0)
- **Owner**: Ichor news agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/nlp/finbert_tone.py`

## Intended use

Per-headline tone classification (positive / neutral / negative) on news
items collected by `ichor_api.collectors.rss`. Aggregated to a per-source +
per-asset rolling tone index that drives:

- Briefing context ("tone of central-bank news has shifted dovish over 24h")
- `NEWS_REGIME_SHIFT` alert (tone z-score > 2)

### Out-of-scope

- English-only — French / German news lose accuracy. Phase 2: per-language
  ensemble (CamemBERT-finance for FR).
- Not a forecaster of price moves; only of textual tone.

## Inputs / Outputs

- **Input**: text snippet (≤ 512 tokens — chunk longer texts).
- **Output**: 3-class label + softmax distribution.

## Training data (upstream)

- Yang & UIC team trained on Reuters TRC2 + 25k human-labeled financial
  headlines; F1 ~ 0.86 on internal hold-out (per upstream model card).

## Caveats & failure modes

- "Strong dollar" might be tagged positive by the model when our portfolio
  is short USD — separate market-side polarity.
- Performance degrades on macro-economic-data prints (CPI, NFP) where neutral
  factual text dominates.
- First call lazy-loads ~440 MB of weights — pre-warm on service start.

## Aggregator weight

Currently 0 (no real news ingestion yet). Target weight ~0.05 once 30d of
calibration data exists.
