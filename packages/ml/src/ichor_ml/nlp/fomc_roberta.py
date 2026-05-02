"""FOMC-RoBERTa wrapper — Hawkish/Dovish/Neutral classification on FOMC text.

Model: gtfintechlab/fomc-roberta-large (HuggingFace).
Training corpus: 1996-2022 FOMC statements + minutes + press conferences.
Output: 3-class label (HAWKISH / DOVISH / NEUTRAL) + softmax.

Used by CB-NLP agent post-FOMC press conferences. Fed into Bias Aggregator
as a calibrable signal (Brier-trained on historical Fed-tone-vs-30d-rate
move).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

FomcTone = Literal["HAWKISH", "DOVISH", "NEUTRAL"]


@dataclass
class FomcToneScore:
    label: FomcTone
    confidence: float
    distribution: dict[FomcTone, float]


@lru_cache(maxsize=1)
def _load_pipeline():
    """Lazy-load the model. ~1.4 GB download on first call (cached after)."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    model_name = "gtfintechlab/fomc-roberta-large"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        device=-1,
        top_k=None,
    )


def score_fomc_tone(text: str) -> FomcToneScore:
    """Classify a single FOMC statement / minutes paragraph.

    Args:
        text: FOMC text snippet (max ~512 tokens — chunk longer texts).

    Returns:
        FomcToneScore with label + confidence + full softmax distribution.
    """
    pipe = _load_pipeline()
    raw = pipe(text)[0]
    dist: dict[str, float] = {item["label"].upper(): float(item["score"]) for item in raw}
    label = max(dist, key=dist.get)
    return FomcToneScore(
        label=label,  # type: ignore[arg-type]
        confidence=dist[label],
        distribution=dist,  # type: ignore[arg-type]
    )


def aggregate_fomc_chunks(scores: list[FomcToneScore]) -> dict[str, float]:
    """For long FOMC texts split into chunks, aggregate to a net Hawkish-Dovish score.

    Returns a dict with `net_hawkish` ∈ [-1, +1] (positive = hawkish overall),
    plus per-class means.
    """
    if not scores:
        return {"net_hawkish": 0.0, "mean_hawkish": 0.0, "mean_dovish": 0.0, "mean_neutral": 0.0}

    haw = sum(s.distribution.get("HAWKISH", 0.0) for s in scores) / len(scores)
    dov = sum(s.distribution.get("DOVISH", 0.0) for s in scores) / len(scores)
    neu = sum(s.distribution.get("NEUTRAL", 0.0) for s in scores) / len(scores)
    return {
        "net_hawkish": float(haw - dov),
        "mean_hawkish": float(haw),
        "mean_dovish": float(dov),
        "mean_neutral": float(neu),
    }
