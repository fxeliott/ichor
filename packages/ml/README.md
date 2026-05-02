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

## Versions verified 2026-05-02

All package versions in `pyproject.toml` were verified against PyPI on
2026-05-02. See `docs/AUDIT_V3.md` §5 for the full version matrix.

## Phase 0 status

🚧 Skeleton only. Implementation Phase 0 Week 2 (steps 12-13).
