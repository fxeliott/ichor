# `packages/ml` — Local ML stack (Hetzner, no LLM)

Implements **Couche 3** of the Ichor architecture (`docs/ARCHITECTURE_FINALE.md`):

- **Bias Aggregator tournament** — LightGBM + XGBoost + Random Forest +
  Logistic + Bayesian NumPyro + MLP PyTorch, Brier-weighted ensemble,
  isotonic calibration over 90-day rolling window.
- **HMM regime detection** — `hmmlearn` 3-state.
- **Concept drift** — `river` ADWIN + Page-Hinkley.
- **DTW analogues** — `dtaidistance`, indexing 22 historical tail events.
- **Vol surface SABR/SVI** — `vollib` (renamed from `py_vollib`, see AUDIT_V3 §2).
- **VPIN flow toxicity** — homemade implementation of Easley-LdP-O'Hara 2012
  ("Flow Toxicity and Liquidity", RFS 25(5):1457-1493).
- **HAR-RV** — `arch` (Sheppard's Corsi 2009 implementation).
- **NLP CB self-host** — FOMC-RoBERTa + FinBERT-tone (CPU OK).

## Status (2026-05-06)

**SHIPPED in production** — Hetzner runs the HMM regime, HAR-RV
forecast, DTW analogue matcher, and FinBERT/FOMC-RoBERTa scorers
on a daily schedule. The 7 probability-only bias trainers (LightGBM,
XGBoost, RandomForest, Logistic, NumPyro, MLP, plus the features
helper) were reinstated by [ADR-022](../../docs/decisions/ADR-022-probability-bias-models-reinstated.md)
under the ADR-017 boundary : every trainer exposes `predict_proba()`
returning `float ∈ [0, 1]`, never a BUY/SELL signal.

`model_registry.yaml` carries 14 entries with matching Mitchell-2019
model cards in `model_cards/`. Lazy-imported from `apps/api` to avoid
the torch + transformers import-time cost at API boot.

## Versions

All package versions in `pyproject.toml` are pinned against PyPI
(see `pnpm-workspace.yaml` catalog for JS deps and `pyproject.toml`
constraints for Python). Stack : numpy ≥ 2.0, lightgbm ≥ 4.5,
xgboost ≥ 2.1, transformers ≥ 4.46, torch ≥ 2.5 (CPU-only via uv
index `pytorch-cpu`).

## Activation note

`apps/api`'s venv ships without transformers/torch by default —
the RAG path (`services/rag/`) and the FOMC/ECB tone scorers
(`services/cb_tone_check.py`) lazy-import them. To activate those
on Hetzner :
```
/opt/ichor/api/.venv/bin/pip install transformers torch \
    --index-url https://download.pytorch.org/whl/cpu
```
