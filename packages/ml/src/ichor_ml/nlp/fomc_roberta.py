"""Multi-CB stance classifier — Hawkish/Dovish/Neutral/Irrelevant per CB.

Models (gtfintechlab 2025 series, replaces older `fomc-roberta-large`
that was deprecated/removed from HuggingFace):

  - FED  : gtfintechlab/model_federal_reserve_system_stance_label
  - ECB  : gtfintechlab/model_european_central_bank_stance_label
  - BoE  : gtfintechlab/model_bank_of_england_stance_label
  - BoJ  : gtfintechlab/model_bank_of_japan_stance_label

Each model is a ~0.4B-parameter RoBERTa-base fine-tuned on the
respective CB's speeches/statements/minutes corpus by gtfintechlab.
Output is a 4-class label : LABEL_0 (Neutral) / LABEL_1 (Hawkish) /
LABEL_2 (Dovish) / LABEL_3 (Irrelevant) — the IRRELEVANT class is
the key benefit over the old 3-class FOMC model : sentences that are
not about monetary policy (boilerplate, biographical, procedural)
get filtered out of the aggregation rather than diluted into NEUTRAL.

Long texts (CB minutes are typically 10-30 KB) are chunked to fit the
RoBERTa-base 512-token input limit ; chunks are scored independently
and aggregated via `aggregate_fomc_chunks`. IRRELEVANT chunks are
dropped from the net_hawkish aggregate to focus on monetary policy
signal only.

Backward-compatibility : the legacy `_load_pipeline()` / `score_fomc_tone`
/ `score_long_fomc_text` / `aggregate_fomc_chunks` functions are kept
with the new FED model as default. The new `score_long_text_for_cb`
takes a `cb` argument for explicit per-CB selection.

ADR-022 boundary : output is a probability triple (HAWKISH/DOVISH/NEUTRAL)
plus IRRELEVANT mass, never a BUY/SELL signal. Fed as one input to the
brain Pass 2 confluence.

Cf ADR-040 (Phase D.5.d BoE+BoJ tone shift alerts).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

FomcTone = Literal["HAWKISH", "DOVISH", "NEUTRAL", "IRRELEVANT"]


# Per-CB model registry. Add new CBs here when shipped — the
# gtfintechlab 2025 series covers 10+ central banks (Swiss SNB,
# Reserve Bank of Australia / India, BIS, BoP, MAS, etc.).
CB_MODEL_REGISTRY: dict[str, str] = {
    "FED": "gtfintechlab/model_federal_reserve_system_stance_label",
    "ECB": "gtfintechlab/model_european_central_bank_stance_label",
    "BOE": "gtfintechlab/model_bank_of_england_stance_label",
    "BOJ": "gtfintechlab/model_bank_of_japan_stance_label",
}

# Default model used by legacy `score_fomc_tone` / `score_long_fomc_text`
# when no CB is specified — keeps backward compatibility for any caller
# that hasn't migrated to `score_long_text_for_cb`.
_DEFAULT_CB = "FED"

# Map LABEL_<int> raw HuggingFace output → semantic label.
_LABEL_MAP: dict[str, FomcTone] = {
    "LABEL_0": "NEUTRAL",
    "LABEL_1": "HAWKISH",
    "LABEL_2": "DOVISH",
    "LABEL_3": "IRRELEVANT",
}


# RoBERTa-base hard max is 512 tokens ; we leave headroom for special
# tokens (CLS, SEP) and the overlap window so each chunk stays ≤ 510.
_CHUNK_MAX_TOKENS = 480
_CHUNK_OVERLAP_TOKENS = 60


@dataclass
class FomcToneScore:
    label: FomcTone
    confidence: float
    distribution: dict[FomcTone, float]


def _resolve_model_name(cb: str) -> str:
    """Map a CB code to its HuggingFace model id. Falls back to FED on
    unknown CB (legacy callers passing 'FED' or no CB at all)."""
    cb_upper = cb.upper()
    return CB_MODEL_REGISTRY.get(cb_upper, CB_MODEL_REGISTRY[_DEFAULT_CB])


@lru_cache(maxsize=4)
def _load_pipeline_for_cb(cb: str):
    """Lazy-load the per-CB model. ~0.4 GB download on first call per CB
    (cached after). The lru_cache holds up to 4 pipelines simultaneously
    in RAM — sufficient for our 4-CB workload."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    model_name = _resolve_model_name(cb)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        device=-1,
        top_k=None,
    )


@lru_cache(maxsize=4)
def _load_tokenizer_for_cb(cb: str):
    """Standalone tokenizer for chunking (re-uses the pipeline's tokenizer)."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(_resolve_model_name(cb))


def _load_pipeline():
    """Backward-compat shim — delegates to FED pipeline."""
    return _load_pipeline_for_cb(_DEFAULT_CB)


def _load_tokenizer():
    """Backward-compat shim — delegates to FED tokenizer."""
    return _load_tokenizer_for_cb(_DEFAULT_CB)


def _normalize_label(raw_label: str) -> FomcTone:
    """Map raw HuggingFace label (`LABEL_0` / `LABEL_1` / etc.) → semantic
    string. Falls back to NEUTRAL on unknown labels (defensive — should
    never happen with the gtfintechlab models)."""
    upper = raw_label.upper()
    if upper in _LABEL_MAP:
        return _LABEL_MAP[upper]
    # Already-semantic label (legacy zero-shot path)
    if upper in ("HAWKISH", "DOVISH", "NEUTRAL", "IRRELEVANT"):
        return upper  # type: ignore[return-value]
    return "NEUTRAL"


def chunk_long_text(
    text: str,
    *,
    cb: str = _DEFAULT_CB,
    max_tokens: int = _CHUNK_MAX_TOKENS,
    overlap_tokens: int = _CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split a long CB text into RoBERTa-sized chunks with overlap.

    Tokenizes once with the model's tokenizer (no <CLS>/<SEP> markers),
    then slices with overlap so a sentence broken across boundaries is
    seen by both adjacent chunks.

    Args:
        text: arbitrary-length input.
        cb: CB code (FED/ECB/BOE/BOJ) — selects the right tokenizer.
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
    tokenizer = _load_tokenizer_for_cb(cb)
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


def score_text_for_cb(text: str, *, cb: str = _DEFAULT_CB) -> FomcToneScore:
    """Classify a single short paragraph with the per-CB model.

    For long inputs (> 480 tokens), use `score_long_text_for_cb` instead —
    this function would otherwise truncate silently to the first 512
    tokens of the input.

    Args:
        text: CB text snippet (≤ ~480 tokens for clean classification).
        cb: CB code (FED/ECB/BOE/BOJ) — selects the right model.

    Returns:
        FomcToneScore with label + confidence + full softmax distribution.
    """
    pipe = _load_pipeline_for_cb(cb)
    raw = pipe(text)[0]
    dist: dict[FomcTone, float] = {}
    for item in raw:
        norm = _normalize_label(str(item["label"]))
        dist[norm] = float(item["score"])
    label = max(dist, key=lambda k: dist[k])
    return FomcToneScore(
        label=label,
        confidence=dist[label],
        distribution=dist,
    )


def score_long_text_for_cb(text: str, *, cb: str = _DEFAULT_CB) -> list[FomcToneScore]:
    """Chunk + score long CB text. Returns one FomcToneScore per chunk.

    Designed for CB minutes / press conferences which run 10-30 KB
    (~3-10k tokens), well past the RoBERTa-base 512 limit. Each chunk
    is scored independently ; pass the result list to
    `aggregate_fomc_chunks` for a single net-hawkish score.

    Empty / whitespace-only input returns `[]` rather than raising.

    Args:
        text: CB text (any length).
        cb: CB code (FED/ECB/BOE/BOJ) — selects the right model.
    """
    chunks = chunk_long_text(text, cb=cb)
    if not chunks:
        return []
    return [score_text_for_cb(c, cb=cb) for c in chunks]


# Backward-compatibility shims — same signatures as before, default to FED.
def score_fomc_tone(text: str) -> FomcToneScore:
    """Legacy alias for `score_text_for_cb(text, cb='FED')`."""
    return score_text_for_cb(text, cb=_DEFAULT_CB)


def score_long_fomc_text(text: str) -> list[FomcToneScore]:
    """Legacy alias for `score_long_text_for_cb(text, cb='FED')`."""
    return score_long_text_for_cb(text, cb=_DEFAULT_CB)


def aggregate_fomc_chunks(scores: list[FomcToneScore]) -> dict[str, float]:
    """Aggregate per-chunk scores to a net Hawkish-Dovish score.

    IRRELEVANT chunks (boilerplate, procedural, biographical) are EXCLUDED
    from the aggregate so they don't dilute the monetary-policy signal.
    The mean_irrelevant field is exposed for diagnostic visibility (high
    irrelevant share = low-signal speech).

    Returns:
        net_hawkish ∈ [-1, +1] (positive = hawkish overall, computed only
        over relevant chunks). 0.0 if all chunks are IRRELEVANT.
    """
    if not scores:
        return {
            "net_hawkish": 0.0,
            "mean_hawkish": 0.0,
            "mean_dovish": 0.0,
            "mean_neutral": 0.0,
            "mean_irrelevant": 0.0,
            "n_relevant_chunks": 0,
            "n_total_chunks": 0,
        }

    n_total = len(scores)
    relevant = [
        s for s in scores
        if s.label != "IRRELEVANT"
        and s.distribution.get("IRRELEVANT", 0.0) < 0.5
    ]
    n_rel = len(relevant)

    haw_all = sum(s.distribution.get("HAWKISH", 0.0) for s in scores) / n_total
    dov_all = sum(s.distribution.get("DOVISH", 0.0) for s in scores) / n_total
    neu_all = sum(s.distribution.get("NEUTRAL", 0.0) for s in scores) / n_total
    irr_all = sum(s.distribution.get("IRRELEVANT", 0.0) for s in scores) / n_total

    if n_rel == 0:
        return {
            "net_hawkish": 0.0,
            "mean_hawkish": float(haw_all),
            "mean_dovish": float(dov_all),
            "mean_neutral": float(neu_all),
            "mean_irrelevant": float(irr_all),
            "n_relevant_chunks": 0,
            "n_total_chunks": n_total,
        }

    haw_rel = sum(s.distribution.get("HAWKISH", 0.0) for s in relevant) / n_rel
    dov_rel = sum(s.distribution.get("DOVISH", 0.0) for s in relevant) / n_rel
    neu_rel = sum(s.distribution.get("NEUTRAL", 0.0) for s in relevant) / n_rel

    return {
        "net_hawkish": float(haw_rel - dov_rel),
        "mean_hawkish": float(haw_rel),
        "mean_dovish": float(dov_rel),
        "mean_neutral": float(neu_rel),
        "mean_irrelevant": float(irr_all),
        "n_relevant_chunks": n_rel,
        "n_total_chunks": n_total,
    }
