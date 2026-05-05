"""Extract entities from news items and load them into the AGE
`ichor_graph` as nodes + relationships.

Idempotent : MERGE-style Cypher means re-running the populator just
ensures the edges exist without duplicating them.

Entity extraction is regex-based — cheap, deterministic, no NLP
runtime needed. Catches the canonical Ichor universe :
- 8 Phase-0 assets
- ~10 central banks / regulators
- Optionally the upstream feed source
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


# ───────────────────────── canonical entities ─────────────────────────

_ASSET_CODES = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)
# Map free-form mentions back to canonical codes
_ASSET_MENTIONS = {
    r"\bEUR/?USD\b|\beuro\b": "EUR_USD",
    r"\bGBP/?USD\b|\bsterling\b|\bcable\b": "GBP_USD",
    r"\bUSD/?JPY\b|\byen\b": "USD_JPY",
    r"\bAUD/?USD\b|\baussie\b": "AUD_USD",
    r"\bUSD/?CAD\b|\bloonie\b": "USD_CAD",
    r"\bXAU/?USD\b|\bgold\b": "XAU_USD",
    r"\bNAS100\b|\bNasdaq\s*100\b|\bNDX\b": "NAS100_USD",
    r"\bSPX500\b|\bS&P\s*500\b|\bSP500\b|\bS\s*and\s*P\s*500\b": "SPX500_USD",
}
_ASSET_PATTERNS = [(re.compile(pat, re.IGNORECASE), code) for pat, code in _ASSET_MENTIONS.items()]

_INSTITUTIONS = {
    "Fed": r"\bFed\b|\bFederal Reserve\b|\bFOMC\b",
    "ECB": r"\bECB\b|\bEuropean Central Bank\b|\bBCE\b",
    "BoE": r"\bBoE\b|\bBank of England\b",
    "BoJ": r"\bBoJ\b|\bBank of Japan\b",
    "SNB": r"\bSNB\b|\bSwiss National Bank\b",
    "RBA": r"\bRBA\b|\bReserve Bank of Australia\b",
    "RBNZ": r"\bRBNZ\b|\bReserve Bank of New Zealand\b",
    "BoC": r"\bBoC\b|\bBank of Canada\b",
    "PBoC": r"\bPBoC\b|\bPeople'?s Bank of China\b",
    "Treasury": r"\bU?S?\s*Treasury\b",
    "SEC": r"\bSEC\b|\bSecurities and Exchange Commission\b",
}
_INSTITUTION_PATTERNS = [
    (re.compile(pat, re.IGNORECASE), name) for name, pat in _INSTITUTIONS.items()
]


@dataclass(frozen=True)
class NewsEntityExtraction:
    guid_hash: str
    source: str
    title: str
    assets: list[str]
    institutions: list[str]


def extract_entities(title: str, summary: str = "") -> tuple[list[str], list[str]]:
    """Return (assets_canonical, institutions_canonical) found in the text."""
    text_blob = f"{title} {summary}"
    assets: set[str] = set()
    for pat, code in _ASSET_PATTERNS:
        if pat.search(text_blob):
            assets.add(code)
    institutions: set[str] = set()
    for pat, name in _INSTITUTION_PATTERNS:
        if pat.search(text_blob):
            institutions.add(name)
    return sorted(assets), sorted(institutions)


# ───────────────────────── populator ─────────────────────────


_INIT_GRAPH = """
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
"""

# Cypher MERGE creates nodes if missing, idempotent.
_MERGE_NEWS = """
SELECT * FROM cypher('ichor_graph', $$
  MERGE (n:NewsArticle {guid_hash: %s})
  ON CREATE SET n.title = %s, n.source = %s
  RETURN n
$$, %s) AS (v ag_catalog.agtype);
"""

_MERGE_ASSET = """
SELECT * FROM cypher('ichor_graph', $$
  MERGE (a:Asset {code: %s})
  RETURN a
$$, %s) AS (v ag_catalog.agtype);
"""

_MERGE_INSTITUTION = """
SELECT * FROM cypher('ichor_graph', $$
  MERGE (i:Institution {name: %s})
  RETURN i
$$, %s) AS (v ag_catalog.agtype);
"""

_MERGE_MENTIONS_ASSET = """
SELECT * FROM cypher('ichor_graph', $$
  MATCH (n:NewsArticle {guid_hash: %s}), (a:Asset {code: %s})
  MERGE (n)-[r:MENTIONS]->(a)
  RETURN r
$$, %s) AS (v ag_catalog.agtype);
"""

_MERGE_MENTIONS_INSTITUTION = """
SELECT * FROM cypher('ichor_graph', $$
  MATCH (n:NewsArticle {guid_hash: %s}), (i:Institution {name: %s})
  MERGE (n)-[r:MENTIONS]->(i)
  RETURN r
$$, %s) AS (v ag_catalog.agtype);
"""


async def populate_news_edges(session: AsyncSession, *, since_minutes: int = 60 * 24 * 7) -> int:
    """Walk recent news_items and populate the AGE graph.

    Returns the number of NewsArticle nodes touched (created or merged).
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from ..models import NewsItem

    cutoff = datetime.now(UTC) - timedelta(minutes=since_minutes)
    rows = (
        (await session.execute(select(NewsItem).where(NewsItem.published_at >= cutoff)))
        .scalars()
        .all()
    )

    if not rows:
        return 0

    await session.execute(text(_INIT_GRAPH))

    touched = 0
    for r in rows:
        assets, institutions = extract_entities(r.title, r.summary or "")
        try:
            await session.execute(
                text(_MERGE_NEWS),
                {"p1": r.guid_hash, "p2": r.title[:200], "p3": r.source},
            )
        except Exception as e:
            log.warning("graph.merge_news_failed", guid=r.guid_hash, error=str(e))
            continue

        for asset in assets:
            try:
                await session.execute(text(_MERGE_ASSET), {"p1": asset})
                await session.execute(
                    text(_MERGE_MENTIONS_ASSET),
                    {"p1": r.guid_hash, "p2": asset},
                )
            except Exception as e:
                log.warning(
                    "graph.merge_mentions_asset_failed",
                    guid=r.guid_hash,
                    asset=asset,
                    error=str(e),
                )

        for inst in institutions:
            try:
                await session.execute(text(_MERGE_INSTITUTION), {"p1": inst})
                await session.execute(
                    text(_MERGE_MENTIONS_INSTITUTION),
                    {"p1": r.guid_hash, "p2": inst},
                )
            except Exception as e:
                log.warning(
                    "graph.merge_mentions_institution_failed",
                    guid=r.guid_hash,
                    inst=inst,
                    error=str(e),
                )

        touched += 1

    await session.commit()
    log.info(
        "graph.populated",
        news_touched=touched,
        since_minutes=since_minutes,
    )
    return touched
