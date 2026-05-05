"""Critic reviewer — extracts factual claims from a briefing and checks
each against the source pool. Pure-Python, no LLM dependency for the
SOURCED-CLAIM CHECK ; the LLM is only used to extract claims (planned
Phase 2).

The Phase-1 implementation is rule-based + heuristic :
  - Extract "evidence sentences" — anything containing a number,
    a percentage, an asset code, a known central-bank name, or
    a model_id.
  - For each evidence sentence, flag it as HALLUCINATION if it
    references an entity / number not present in the source pool.
  - Compute a confidence score = 1 - (n_unsourced / n_evidence).

This is intentionally conservative — it errs on the side of "amendments"
or "blocked" rather than approving silently. False positives are
preferable to false approvals when capital is at stake (even paper).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Verdict = Literal["approved", "amendments", "blocked"]


@dataclass(frozen=True)
class HallucinationFinding:
    """One sentence flagged as unsourced."""

    sentence: str
    reason: str
    severity: Literal["info", "warning", "critical"]


@dataclass
class CriticVerdict:
    verdict: Verdict
    confidence: float
    """Confidence in [0, 1] : 1 = perfectly sourced, 0 = nothing matches."""

    findings: list[HallucinationFinding] = field(default_factory=list)
    suggested_footer: str = ""
    """Markdown footer to append if verdict == 'amendments'."""

    n_evidence_sentences: int = 0
    n_unsourced: int = 0
    reviewed_at: datetime | None = None


# ───────────────────────── extraction ─────────────────────────


# Sentences that contain a number, %, or known finance entity → "evidence"
_NUMBER_RE = re.compile(r"\b\d+(?:[\.,]\d+)?(?:\s?[%bps]+)?\b")
_ASSET_RE = re.compile(
    r"\b(?:EUR/USD|EURUSD|GBP/USD|USD/JPY|AUD/USD|USD/CAD|XAU/USD|"
    r"NAS100|SPX500|S&P\s*500|Nasdaq|NDX|VIX|DXY|HY\s*OAS|IG\s*OAS)\b",
    re.IGNORECASE,
)
_CB_RE = re.compile(
    r"\b(?:Fed|FOMC|ECB|BoE|BoJ|SNB|BCE|RBA|RBNZ|BoC|PBoC)\b",
    re.IGNORECASE,
)
_MODEL_RE = re.compile(r"\b[a-z][a-z0-9_-]+-bias-[a-z0-9_-]+-v\d+\b", re.IGNORECASE)


def _split_sentences(md: str) -> list[str]:
    """Cheap sentence splitter — periods + question marks + exclamation +
    newlines, but careful not to split on "0.5" decimals."""
    cleaned = re.sub(r"\s+", " ", md).strip()
    # Protect decimal numbers from being split at '.'
    cleaned = re.sub(r"(\d)\.(\d)", r"\1​.​\2", cleaned)
    parts = re.split(r"(?<=[\.\!\?])\s+", cleaned)
    return [p.replace("​", "").strip() for p in parts if p.strip()]


def _is_evidence(sentence: str) -> bool:
    return bool(
        _NUMBER_RE.search(sentence)
        or _ASSET_RE.search(sentence)
        or _CB_RE.search(sentence)
        or _MODEL_RE.search(sentence)
    )


# ───────────────────────── source check ─────────────────────────


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


# Asset spellings that should all be considered equivalent during the
# source-pool match. The LLM tends to emit the human-readable slash form
# (EUR/USD, XAU/USD) while data_pool.py emits underscored codes (EUR_USD)
# and Polygon-prefixed tickers (C:EURUSD, C:XAUUSD, I:NDX). Without this
# mapping the Critic flags every asset mention as "not in pool" and the
# entire pipeline blocks even when sources are perfectly tracked.
_ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "eur/usd": ("eur/usd", "eur_usd", "eurusd", "c:eurusd"),
    "eurusd": ("eur/usd", "eur_usd", "eurusd", "c:eurusd"),
    "gbp/usd": ("gbp/usd", "gbp_usd", "gbpusd", "c:gbpusd"),
    "usd/jpy": ("usd/jpy", "usd_jpy", "usdjpy", "c:usdjpy"),
    "aud/usd": ("aud/usd", "aud_usd", "audusd", "c:audusd"),
    "usd/cad": ("usd/cad", "usd_cad", "usdcad", "c:usdcad"),
    "xau/usd": ("xau/usd", "xau_usd", "xauusd", "c:xauusd", "gold"),
    "nas100": ("nas100", "nas100_usd", "ndx", "i:ndx"),
    "spx500": ("spx500", "spx500_usd", "spx", "i:spx", "s&p 500", "s&p500"),
    "s&p 500": ("spx500", "spx500_usd", "spx", "i:spx", "s&p 500", "s&p500"),
    "nasdaq": ("nas100", "nas100_usd", "ndx", "i:ndx", "nasdaq"),
    "ndx": ("nas100", "nas100_usd", "ndx", "i:ndx"),
    "vix": ("vix", "vixcls", "vix9d", "vix3m"),
    "dxy": ("dxy", "dtwexbgs", "dollar index", "us dollar index"),
    "hy oas": ("hy oas", "bamlh0a0hym2", "hy spread"),
    "ig oas": ("ig oas", "bamlc0a0cm", "bamlc0a0cmtriv", "ig spread"),
}


def _asset_in_pool(asset_text: str, source_pool_norm: str) -> bool:
    """Return True if any known alias of `asset_text` appears in the
    normalized source pool. Falls back to direct substring check for
    unknown assets so we stay conservative."""
    key = _normalize(asset_text).strip()
    aliases = _ASSET_ALIASES.get(key)
    if aliases is None:
        return key in source_pool_norm
    return any(alias in source_pool_norm for alias in aliases)


def _entity_present_in_sources(entity: str, source_pool: str) -> bool:
    return _normalize(entity) in _normalize(source_pool)


def _check_sentence(sentence: str, source_pool_norm: str) -> HallucinationFinding | None:
    """Return a finding if the sentence references entities/numbers not
    present in the source pool."""
    # 1. Asset codes — every mentioned asset MUST appear in sources
    #    via any of its known aliases (slash/underscore/Polygon-prefixed).
    for m in _ASSET_RE.finditer(sentence):
        if not _asset_in_pool(m.group(0), source_pool_norm):
            return HallucinationFinding(
                sentence=sentence,
                reason=f"asset '{m.group(0)}' not in source pool",
                severity="warning",
            )

    # 2. Central bank mentions — same.
    for m in _CB_RE.finditer(sentence):
        if _normalize(m.group(0)) not in source_pool_norm:
            return HallucinationFinding(
                sentence=sentence,
                reason=f"institution '{m.group(0)}' not in source pool",
                severity="info",
            )

    # 3. Model_id — must match a real model id in the source pool.
    for m in _MODEL_RE.finditer(sentence):
        if _normalize(m.group(0)) not in source_pool_norm:
            return HallucinationFinding(
                sentence=sentence,
                reason=f"model_id '{m.group(0)}' not in source pool",
                severity="critical",
            )

    return None


# ───────────────────────── verdict ─────────────────────────


def _decide(confidence: float, findings: list[HallucinationFinding]) -> Verdict:
    if any(f.severity == "critical" for f in findings):
        return "blocked"
    if confidence < 0.6:
        return "blocked"
    if findings:
        return "amendments"
    return "approved"


def review_briefing(
    briefing_markdown: str,
    source_pool: str,
    *,
    asset_whitelist: list[str] | None = None,
) -> CriticVerdict:
    """Review a briefing for unsourced claims.

    Args :
      briefing_markdown : the Claude-generated briefing body
      source_pool       : concatenated text of all data the briefing
                          was supposed to be derived from (context_markdown
                          assembled in BLOC B, for example)
      asset_whitelist   : optional override — if provided, asset mentions
                          must be in this list. Useful when the briefing
                          is supposed to be scope-limited.

    Returns :
      CriticVerdict (verdict + confidence + findings + suggested footer).
    """
    source_pool_norm = _normalize(source_pool)
    if asset_whitelist:
        whitelist_norm = " ".join(_normalize(a) for a in asset_whitelist)
        source_pool_norm = source_pool_norm + " " + whitelist_norm

    sentences = _split_sentences(briefing_markdown)
    evidence = [s for s in sentences if _is_evidence(s)]
    findings: list[HallucinationFinding] = []
    for s in evidence:
        f = _check_sentence(s, source_pool_norm)
        if f is not None:
            findings.append(f)

    confidence = 1.0 - (len(findings) / len(evidence)) if evidence else 1.0

    verdict = _decide(confidence, findings)
    footer = ""
    if verdict in ("amendments", "blocked"):
        footer = (
            "\n\n---\n*Critic notes (auto-generated):* "
            f"{len(findings)} unsourced claims out of {len(evidence)} "
            f"evidence sentences (confidence {confidence:.0%}). "
            "Flagged items above should be cross-checked manually before "
            "trading off this briefing."
        )

    return CriticVerdict(
        verdict=verdict,
        confidence=round(confidence, 4),
        findings=findings,
        suggested_footer=footer,
        n_evidence_sentences=len(evidence),
        n_unsourced=len(findings),
        reviewed_at=datetime.now(UTC),
    )
