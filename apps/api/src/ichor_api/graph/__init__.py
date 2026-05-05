"""Apache AGE knowledge graph helpers.

The `ichor_graph` graph is created by the Postgres role at install time.
This module populates it with entities + edges extracted from collected
data (news_items, polymarket, market_data) so we can answer queries
like "show all news mentioning EUR + ECB last week" via Cypher.

Entities :
  - Asset(code)               : EUR_USD, XAU_USD, …
  - Institution(name)         : Fed, ECB, BoE, …
  - NewsArticle(guid_hash)    : one per persisted news_item
  - Market(slug)              : Polymarket question

Edges :
  - (NewsArticle)-[:MENTIONS]->(Asset)
  - (NewsArticle)-[:MENTIONS]->(Institution)
  - (NewsArticle)-[:PUBLISHED_BY]->(Source)

Phase 1 entity extraction is regex-based (cheap + deterministic).
Phase 2 plan : swap in spaCy NER + the FOMC-RoBERTa model_card metadata.
"""

from .populator import (
    NewsEntityExtraction,
    extract_entities,
    populate_news_edges,
)

__all__ = [
    "NewsEntityExtraction",
    "extract_entities",
    "populate_news_edges",
]
