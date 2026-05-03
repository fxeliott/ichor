"""Narrative tracker — top keywords + topic prevalence on cb_speeches + news.

Pure-Python keyword frequency analysis : extracts the dominant
narrative themes from recent central-bank speeches and news headlines
with no ML dependency. Phase 1 ships TF normalized + stopword
filtering. Phase 2 will swap in BERTopic for proper topic clustering
when we have ≥ 30 days of corpus history (today : 126 speeches +
~250 news items, enough for usable signal but thin for clustering).

VISION_2026 delta J — macro narrative tracker.

Why TF instead of BERTopic V1 :
  - No model download (BERTopic needs ~1.5 GB sentence-transformers
    + UMAP + HDBSCAN, complicates deploy)
  - Deterministic output (LLM-free), trivially testable
  - Captures the "Powell hawkish" / "ECB dovish" / "AI capex" /
    "recession" narratives well enough for a Pass 1 régime input
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CbSpeech, NewsItem


# Lowercased, accent-stripped tokens we drop. English-only V1 — the FR
# RSS feeds we follow (Reuters, Fed/ECB/BoE/BoJ) are English-first.
_STOPWORDS: frozenset[str] = frozenset(
    """a an and any as at be been being but by can could did do does for from
    had has have he her here hers him his how i if in into is it its just may
    me might more most must my no nor not of on once only or other our out
    over per said say says she should so some such than that the their them
    then there these they this those through to too under until up us was we
    were what when where which while who whom why will with would you your
    about above after again against all am also any aren be before below
    between both during each few further his how i'd i'll i'm i've if into
    isn it itself let let's me ought ours ourselves shouldn was wasn weren
    what's when's where's which while who's whom whose why's with won't
    yourself yourselves you'd you'll you're you've above against between
    cannot couldn doesn don hadn hasn haven isn shan shouldn wasn weren
    won wouldn 's 'd 'll 'm 'o 're 've 't ago around new news inc bank
    via said also told report reports said-during like really already
    last made much etc news today yesterday tomorrow week month year"""
    .split()
)

# Finance-specific stopwords — remove generic markers that pollute TF
_FINANCE_STOPWORDS: frozenset[str] = frozenset(
    {
        "market", "markets", "rate", "rates", "data", "report", "reuters",
        "bloomberg", "ap", "wsj", "ft", "stocks", "stock", "shares",
        "trading", "trader", "traders", "investor", "investors",
        "analyst", "analysts", "session", "monetary", "policy", "policies",
        "economy", "economic", "economist", "economists", "growth",
        "outlook", "view", "comments", "speech", "speeches", "interview",
        "press", "release", "statement", "minutes", "decision", "meeting",
    }
)

_TOKEN_RE = re.compile(r"[a-z][a-z\-]{2,}")


@dataclass(frozen=True)
class Topic:
    """One topic = a (lemma-ish) keyword with its count + share."""

    keyword: str
    count: int
    share: float  # count / total_tokens
    sample_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class NarrativeReport:
    """Output of `track_narratives` — top topics + corpus stats."""

    window_hours: int
    n_documents: int
    n_tokens: int
    topics: list[Topic]


def _tokenize(text: str) -> list[str]:
    """Lower, strip non-letters, drop short + stopwords + finance noise."""
    if not text:
        return []
    out = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if len(tok) < 4:
            continue
        if tok in _STOPWORDS or tok in _FINANCE_STOPWORDS:
            continue
        # Strip leading/trailing dashes left by hyphens at edges
        tok = tok.strip("-")
        if not tok:
            continue
        out.append(tok)
    return out


async def track_narratives(
    session: AsyncSession,
    *,
    window_hours: int = 48,
    top_k: int = 15,
) -> NarrativeReport:
    """Pull cb_speeches + news_items in the window, return top-K keywords.

    Tokenizes title + summary (first 500 chars) per document, removes
    stopwords + finance noise, counts global frequency, and emits the
    top-K topics with one sample title each.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # Pull both sources in parallel
    cb_stmt = (
        select(CbSpeech.title, CbSpeech.summary)
        .where(CbSpeech.published_at >= cutoff)
    )
    news_stmt = (
        select(NewsItem.title, NewsItem.summary)
        .where(NewsItem.published_at >= cutoff)
    )

    cb_rows = list((await session.execute(cb_stmt)).all())
    news_rows = list((await session.execute(news_stmt)).all())

    counter: Counter[str] = Counter()
    title_by_keyword: dict[str, str] = {}
    n_docs = 0
    n_tokens = 0

    for title, summary in [*cb_rows, *news_rows]:
        n_docs += 1
        text = f"{title or ''} {(summary or '')[:500]}"
        toks = _tokenize(text)
        n_tokens += len(toks)
        for t in set(toks):  # document frequency, not term freq
            counter[t] += 1
            if t not in title_by_keyword:
                title_by_keyword[t] = title or ""

    if n_docs == 0:
        return NarrativeReport(
            window_hours=window_hours,
            n_documents=0,
            n_tokens=0,
            topics=[],
        )

    topics: list[Topic] = []
    for kw, ct in counter.most_common(top_k):
        topics.append(
            Topic(
                keyword=kw,
                count=ct,
                share=round(ct / n_docs, 4),
                sample_titles=(title_by_keyword.get(kw, ""),) if title_by_keyword.get(kw) else (),
            )
        )

    return NarrativeReport(
        window_hours=window_hours,
        n_documents=n_docs,
        n_tokens=n_tokens,
        topics=topics,
    )


def render_narrative_block(report: NarrativeReport) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py — top topics with their share."""
    lines = [f"## Narrative tracker (last {report.window_hours}h)"]
    if report.n_documents == 0:
        lines.append("- (no documents in window)")
        return "\n".join(lines), []
    lines.append(
        f"- {report.n_documents} documents · {report.n_tokens} tokens · "
        f"top {len(report.topics)} keywords below"
    )
    for t in report.topics:
        sample = (
            f' (e.g. "{t.sample_titles[0][:60]}")'
            if t.sample_titles
            else ""
        )
        lines.append(
            f"- **{t.keyword}** · {t.count} doc(s) · "
            f"{t.share * 100:.1f}% share{sample}"
        )
    return "\n".join(lines), [
        f"narrative:{report.window_hours}h:{t.keyword}" for t in report.topics
    ]
