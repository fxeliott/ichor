"""Ichor ML stack — Couche 3 (no LLM, pure Python, runs on Hetzner).

Modules:
  types          Pydantic schemas: Prediction, BiasSignal, ModelCard
  registry       Read model_registry.yaml + model cards
  bias_aggregator Tournament + Brier-weighted ensemble of 6 models
  regime         HMM 3-state regime detection + concept drift (river)
  analogues      DTW historical-analogue matching (dtaidistance)
  vol            Vol surface SABR/SVI (vollib) + HAR-RV (arch)
  microstructure VPIN (homemade Easley-LdP-O'Hara 2012)
  nlp            FOMC-RoBERTa + FinBERT-tone (HuggingFace, CPU)
  calibration    Isotonic calibration 90-day rolling
"""

__version__ = "0.0.0"
