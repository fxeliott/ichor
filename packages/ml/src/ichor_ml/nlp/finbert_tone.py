"""FinBERT-tone wrapper — sentiment classification on financial text.

Model: yiyanghkust/finbert-tone (HuggingFace). 3-class: positive / neutral / negative.
Runs CPU-only, ~50ms per sentence on a modern Hetzner CX32.

Used by: News-NLP agent + CB-NLP agent for tone scoring of FOMC/ECB statements,
news headlines, and Reddit/Twitter sentiment buckets.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import numpy as np

ToneLabel = Literal["positive", "neutral", "negative"]


@dataclass
class ToneScore:
    label: ToneLabel
    confidence: float  # softmax probability of the predicted label
    distribution: dict[ToneLabel, float]  # full softmax over the 3 classes


@lru_cache(maxsize=1)
def _load_pipeline():
    """Lazy-load the model on first call. Cached for the process lifetime."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    model_name = "yiyanghkust/finbert-tone"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return pipeline(
        "sentiment-analysis",
        model=model,
        tokenizer=tokenizer,
        device=-1,  # CPU
        top_k=None,
    )


def score_tone(text: str) -> ToneScore:
    """Classify tone of a single text snippet (max ~512 tokens)."""
    pipe = _load_pipeline()
    raw = pipe(text)[0]  # list of dicts with "label" + "score"

    # Normalize labels to lowercase
    dist: dict[ToneLabel, float] = {item["label"].lower(): float(item["score"]) for item in raw}
    label = max(dist, key=dist.get)
    return ToneScore(
        label=label,  # type: ignore[arg-type]
        confidence=dist[label],
        distribution=dist,
    )


def score_tones_batch(texts: list[str], *, batch_size: int = 32) -> list[ToneScore]:
    """Vectorized over a list of texts. Faster for >10 inputs."""
    pipe = _load_pipeline()
    results: list[ToneScore] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        raws = pipe(chunk)
        for raw in raws:
            dist = {item["label"].lower(): float(item["score"]) for item in raw}
            label = max(dist, key=dist.get)
            results.append(ToneScore(label=label, confidence=dist[label], distribution=dist))  # type: ignore[arg-type]
    return results


def aggregate_tone(scores: list[ToneScore]) -> dict[str, float]:
    """Aggregate a batch of scores into mean per-class probabilities + a
    single net tone score in [-1, +1] (positive minus negative)."""
    if not scores:
        return {"net_tone": 0.0, "mean_positive": 0.0, "mean_neutral": 0.0, "mean_negative": 0.0}

    pos = np.mean([s.distribution.get("positive", 0.0) for s in scores])
    neu = np.mean([s.distribution.get("neutral", 0.0) for s in scores])
    neg = np.mean([s.distribution.get("negative", 0.0) for s in scores])
    return {
        "net_tone": float(pos - neg),
        "mean_positive": float(pos),
        "mean_neutral": float(neu),
        "mean_negative": float(neg),
    }
