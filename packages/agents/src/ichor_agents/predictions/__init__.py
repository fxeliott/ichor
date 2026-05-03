"""Prediction-market intelligence — Polymarket / Kalshi / Manifold.

Polymarket (decentralized, "insider" pricing), Kalshi (US-regulated,
retail-heavy), and Manifold (community wisdom-of-crowds) price the
same future events differently. The gap between them is itself a
tradable feature : a 2-5 % divergence on Fed-cut probability or a
recession contract typically resolves toward Polymarket within 24-48 h.

Cf. VISION_2026 delta M (UNIQUE to Ichor — no competitor surfaces this
systematically). See also the *Maduro Trade* Feb 2026 ($400k profit on
a Polymarket gap).
"""

from .divergence import (
    DivergenceAlert,
    MatchedMarket,
    PredictionMarket,
    detect_divergences,
    jaccard_similarity,
    match_across_venues,
    normalize_question,
    tokenize,
)

__all__ = [
    "DivergenceAlert",
    "MatchedMarket",
    "PredictionMarket",
    "detect_divergences",
    "jaccard_similarity",
    "match_across_venues",
    "normalize_question",
    "tokenize",
]
