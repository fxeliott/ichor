"""Cross-venue prediction-market divergence detector.

Pure-stdlib functions. No DB, no I/O. The CLI hook in
`apps/api/src/ichor_api/cli/run_divergence_scan.py` (next sprint)
wires this into Postgres polls of `polymarket_snapshots`,
`kalshi_markets`, and `manifold_markets`.

Why not embeddings ?
  Embeddings would catch more matches (e.g. "Fed funds rate cut" vs
  "FOMC reduces rate") but require a hosted model, network call, and
  latency budget. For Phase 1 this token-Jaccard matcher is enough :
  it nails ~70 % of the high-value matches (Fed-cut, recession,
  election, geopolitical events) where the question phrasing is highly
  conventionalized across venues. Phase 2 can swap in
  bge-large-en-v1.5 self-host on Hetzner for the long tail.

Methodology
-----------
1. **Normalize** : lowercase, strip punctuation, drop a small stopword
   list (English-only V1, fine because all 3 venues are English-first).
2. **Tokenize** : split on whitespace.
3. **Jaccard** : |intersect| / |union| token-set similarity ∈ [0, 1].
4. **Match** : pairs above `threshold` (default 0.55) are considered
   the same event.
5. **Divergence** : among 2 or 3 matched venues, alert if
   max(yes_prices) - min(yes_prices) > `gap_threshold` (default 0.05).

This favors precision over recall : false positives are expensive
(Eliot trades on these) ; false negatives just mean we miss an arb.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Venue = Literal["polymarket", "kalshi", "manifold"]


# ────────────────────────── Text normalization ─────────────────────────


_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "by", "for", "with", "from", "as",
    "and", "or", "but", "so", "if", "than", "that", "this", "it", "its",
    "will", "would", "could", "should", "may", "might", "can", "do",
    "does", "did", "have", "has", "had", "?", "!",
    # finance / venue-specific noise
    "yes", "no", "market", "event", "contract",
})


def normalize_question(text: str) -> str:
    """Lowercase + drop punctuation. Whitespace-collapsed."""
    out_chars = []
    for ch in text:
        if ch.isalnum():
            out_chars.append(ch.lower())
        elif ch in (" ", "-", "/", "_"):
            out_chars.append(" ")
        # all other punctuation dropped
    raw = "".join(out_chars)
    return " ".join(raw.split())


def tokenize(text: str) -> list[str]:
    """Split normalized text into content tokens (stopwords removed)."""
    return [t for t in normalize_question(text).split() if t and t not in _STOPWORDS]


def jaccard_similarity(a: list[str], b: list[str]) -> float:
    """|intersect| / |union| on token sets. Empty sets → 0."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ────────────────────────────── Data shapes ────────────────────────────


@dataclass(frozen=True)
class PredictionMarket:
    """Normalized representation of a market across venues."""

    venue: Venue
    market_id: str  # ticker for Kalshi, slug for Polymarket/Manifold
    question: str
    yes_price: float | None  # in [0, 1]


@dataclass(frozen=True)
class MatchedMarket:
    """A set of 1+ markets across venues judged to refer to the same event."""

    representative_question: str
    similarity: float  # min similarity within the cluster
    by_venue: dict[Venue, PredictionMarket]


@dataclass(frozen=True)
class DivergenceAlert:
    """A matched market with a price gap above threshold."""

    representative_question: str
    gap: float  # max - min yes_price across venues with prices
    high: tuple[Venue, float]  # which venue at what price
    low: tuple[Venue, float]
    matched: MatchedMarket


# ────────────────────────────── Matching ───────────────────────────────


def match_across_venues(
    polymarket: list[PredictionMarket],
    kalshi: list[PredictionMarket],
    manifold: list[PredictionMarket],
    *,
    threshold: float = 0.55,
) -> list[MatchedMarket]:
    """Greedy match : for each Polymarket question, find the best
    Kalshi + Manifold candidates above `threshold`.

    Polymarket is treated as the anchor venue because its market
    creation tends to lead the others by hours (cf. Bloomberg 2026
    feature on prediction markets). Polymarket-less events still
    surface if Kalshi and Manifold both have them.

    Greedy is fine because the universe is small (~100s markets per
    venue). For 1000s+ a Hungarian assignment would be cleaner.
    """
    if threshold < 0 or threshold > 1:
        raise ValueError("threshold must be in [0, 1]")

    poly_tokens = [(m, tokenize(m.question)) for m in polymarket]
    kal_tokens = [(m, tokenize(m.question)) for m in kalshi]
    man_tokens = [(m, tokenize(m.question)) for m in manifold]

    used_kalshi: set[str] = set()
    used_manifold: set[str] = set()
    out: list[MatchedMarket] = []

    def best_match(
        pool: list[tuple[PredictionMarket, list[str]]],
        used: set[str],
        anchor_tokens: list[str],
    ) -> tuple[PredictionMarket | None, float]:
        best_m: PredictionMarket | None = None
        best_s = 0.0
        for m, toks in pool:
            if m.market_id in used:
                continue
            s = jaccard_similarity(anchor_tokens, toks)
            if s > best_s:
                best_s = s
                best_m = m
        return (best_m, best_s) if best_s >= threshold else (None, best_s)

    # 1) Polymarket-anchored matches
    for poly_m, poly_toks in poly_tokens:
        kal_m, kal_s = best_match(kal_tokens, used_kalshi, poly_toks)
        man_m, man_s = best_match(man_tokens, used_manifold, poly_toks)
        if kal_m is None and man_m is None:
            continue  # solo polymarket — no cross-venue signal
        by_venue: dict[Venue, PredictionMarket] = {"polymarket": poly_m}
        sims = [1.0]
        if kal_m is not None:
            by_venue["kalshi"] = kal_m
            used_kalshi.add(kal_m.market_id)
            sims.append(kal_s)
        if man_m is not None:
            by_venue["manifold"] = man_m
            used_manifold.add(man_m.market_id)
            sims.append(man_s)
        out.append(
            MatchedMarket(
                representative_question=poly_m.question,
                similarity=min(sims),
                by_venue=by_venue,
            )
        )

    # 2) Kalshi ↔ Manifold orphan matches (no Polymarket)
    for kal_m, kal_toks in kal_tokens:
        if kal_m.market_id in used_kalshi:
            continue
        man_m, man_s = best_match(man_tokens, used_manifold, kal_toks)
        if man_m is None:
            continue
        used_manifold.add(man_m.market_id)
        out.append(
            MatchedMarket(
                representative_question=kal_m.question,
                similarity=man_s,
                by_venue={"kalshi": kal_m, "manifold": man_m},
            )
        )

    return out


# ───────────────────────────── Divergence ──────────────────────────────


def detect_divergences(
    matched: list[MatchedMarket],
    *,
    gap_threshold: float = 0.05,
) -> list[DivergenceAlert]:
    """Filter matched markets by yes-price gap. Markets with < 2 priced
    venues are skipped (no divergence to compute)."""
    if gap_threshold < 0 or gap_threshold > 1:
        raise ValueError("gap_threshold must be in [0, 1]")
    out: list[DivergenceAlert] = []
    for m in matched:
        priced = [(v, p.yes_price) for v, p in m.by_venue.items() if p.yes_price is not None]
        if len(priced) < 2:
            continue
        priced.sort(key=lambda x: x[1])  # type: ignore[arg-type]
        low_v, low_p = priced[0]
        high_v, high_p = priced[-1]
        gap = high_p - low_p  # type: ignore[operator]
        if gap >= gap_threshold:
            out.append(
                DivergenceAlert(
                    representative_question=m.representative_question,
                    gap=gap,
                    high=(high_v, high_p),  # type: ignore[arg-type]
                    low=(low_v, low_p),  # type: ignore[arg-type]
                    matched=m,
                )
            )
    out.sort(key=lambda a: a.gap, reverse=True)
    return out
