"""FOMC-RoBERTa wrapper — Hawkish/Dovish/Neutral classification on FOMC text.

Model: gtfintechlab/fomc-roberta-large (HuggingFace).
Training corpus: 1996-2022 FOMC statements + minutes + press conferences.
Output: 3-class label (HAWKISH / DOVISH / NEUTRAL) + softmax.

Used by CB-NLP agent post-FOMC press conferences. Fed into Bias Aggregator
as a calibrable signal (Brier-trained on historical Fed-tone-vs-30d-rate
move).

Long texts (FOMC minutes are typically 10-30 KB) are chunked to fit the
RoBERTa-large 512-token input limit ; chunks are scored independently
and aggregated via `aggregate_fomc_chunks`. Without chunking, the
HuggingFace pipeline silently truncates to the first 512 tokens, losing
~80% of the signal on a typical minutes release.

ADR-022 boundary : output is a probability triple (HAWKISH/DOVISH/NEUTRAL),
never a BUY/SELL signal. Fed as one input to the brain Pass 2 confluence.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

FomcTone = Literal["HAWKISH", "DOVISH", "NEUTRAL"]


# RoBERTa-large hard max is 512 tokens ; we leave headroom for special
# tokens (CLS, SEP) and the overlap window so each chunk stays ≤ 510.
_CHUNK_MAX_TOKENS = 480
_CHUNK_OVERLAP_TOKENS = 60


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


@lru_cache(maxsize=1)
def _load_tokenizer():
    """Standalone tokenizer for chunking (re-uses the pipeline's tokenizer)."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained("gtfintechlab/fomc-roberta-large")


def chunk_long_text(
    text: str,
    *,
    max_tokens: int = _CHUNK_MAX_TOKENS,
    overlap_tokens: int = _CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split a long FOMC text into RoBERTa-sized chunks with overlap.

    Tokenizes once with the model's tokenizer (no <CLS>/<SEP> markers),
    then slices with overlap so a sentence broken across boundaries is
    seen by both adjacent chunks.

    Args:
        text: arbitrary-length input.
        max_tokens: chunk size in tokens (default 480 ; head-room < 512).
        overlap_tokens: how many tokens to repeat at the start of each
            chunk after the first. 0 = no overlap.

    Returns:
        List of text chunks (decoded back to strings). For short inputs
        (≤ max_tokens) returns `[text]` unchanged. Empty / whitespace-
        only input returns `[]`.
    """
    if not text or not text.strip():
        return []
    tokenizer = _load_tokenizer()
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return [text]

    step = max(1, max_tokens - max(0, overlap_tokens))
    chunks: list[str] = []
    start = 0
    while start < len(ids):
        end = min(start + max_tokens, len(ids))
        slice_ids = ids[start:end]
        chunks.append(tokenizer.decode(slice_ids, skip_special_tokens=True))
        if end == len(ids):
            break
        start += step
    return chunks


def score_fomc_tone(text: str) -> FomcToneScore:
    """Classify a single FOMC statement / minutes paragraph.

    For long inputs (> 480 tokens), use `score_long_fomc_text` instead —
    this function would otherwise truncate silently to the first 512
    tokens of the input.

    Args:
        text: FOMC text snippet (≤ ~480 tokens for clean classification).

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


def score_long_fomc_text(text: str) -> list[FomcToneScore]:
    """Chunk + score long FOMC text. Returns one FomcToneScore per chunk.

    Designed for FOMC minutes / press conferences which run 10-30 KB
    (~3-10k tokens), well past the RoBERTa-large 512 limit. Each chunk
    is scored independently ; pass the result list to
    `aggregate_fomc_chunks` for a single net-hawkish score.

    Empty / whitespace-only input returns `[]` rather than raising.
    """
    chunks = chunk_long_text(text)
    if not chunks:
        return []
    return [score_fomc_tone(c) for c in chunks]


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
