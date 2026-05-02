"""NLP central-bank + news models, all self-host (CPU OK).

Models pinned (verified 2026-05):
  - FinBERT-tone (yiyanghkust/finbert-tone, HuggingFace, MIT)
  - FOMC-RoBERTa (gtfintechlab/fomc-roberta, planned Phase 0 W2 step 13)
"""

from .finbert_tone import (
    ToneLabel,
    ToneScore,
    aggregate_tone,
    score_tone,
    score_tones_batch,
)

__all__ = [
    "ToneLabel",
    "ToneScore",
    "aggregate_tone",
    "score_tone",
    "score_tones_batch",
]
