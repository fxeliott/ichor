"""GET /v1/graph — read the AGE knowledge graph for visualization.

Powers the `/knowledge-graph` Next.js page. Returns the news-mentions
graph in a JSON shape compatible with force-directed renderers
(nodes + links arrays).

VISION_2026 delta K — knowledge graph navigable.

The graph is populated by `apps/api/src/ichor_api/graph/populator.py`
(news entity extraction → AGE Cypher MERGE). This route only reads,
never writes.

Two views :
  - `/v1/graph/news-network` : recent (assets + institutions + news)
    co-mention graph aggregated to weighted edges
  - `/v1/graph/causal-map` : pre-coded causal edges Powell→Fed→USD→DXY→XAU
    (no DB query, the structural map is canonical)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..graph.populator import extract_entities
from ..models import NewsItem
from ..services.causal_propagation import (
    propagate_shock,
    supported_shock_nodes,
)

router = APIRouter(prefix="/v1/graph", tags=["graph"])


# ────────────────────────── Response shapes ──────────────────────────


NodeKind = Literal["asset", "institution", "narrative"]


class GraphNode(BaseModel):
    id: str
    label: str
    kind: NodeKind
    weight: int  # degree in the visible window — drives node size


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int  # number of co-mentions
    kind: Literal["MENTIONS_TOGETHER", "CAUSAL_FORWARD"]


class GraphOut(BaseModel):
    window_hours: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    n_news: int
    """Total news items in the window (whether they had entities or not)."""


# ────────────────────────── News-network builder ──────────────────────


@router.get("/news-network", response_model=GraphOut)
async def news_network(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(48, ge=1, le=336),
) -> GraphOut:
    """Build the (Asset + Institution) co-mention graph from recent news.

    We don't actually round-trip Apache AGE here — the news entity
    extractor in `graph/populator.extract_entities` is deterministic
    so we re-derive the graph from `news_items` directly. This avoids
    AGE permission issues and keeps the route latency low (< 100 ms).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(
        (
            await session.execute(
                select(NewsItem.title, NewsItem.summary).where(NewsItem.published_at >= cutoff)
            )
        ).all()
    )
    n_news = len(rows)

    # Co-mention counts and node-degree counts
    edge_counts: dict[tuple[str, str], int] = {}
    node_degree: dict[str, int] = {}
    asset_seen: set[str] = set()
    inst_seen: set[str] = set()

    for title, summary in rows:
        assets, institutions = extract_entities(title or "", summary or "")
        # Each entity gains +1 degree per article mentioning it
        for a in assets:
            asset_seen.add(a)
            node_degree[f"asset:{a}"] = node_degree.get(f"asset:{a}", 0) + 1
        for i in institutions:
            inst_seen.add(i)
            node_degree[f"inst:{i}"] = node_degree.get(f"inst:{i}", 0) + 1
        # Co-mention edges (asset ↔ institution + asset ↔ asset + inst ↔ inst)
        for a in assets:
            for i in institutions:
                key = (f"asset:{a}", f"inst:{i}")
                edge_counts[key] = edge_counts.get(key, 0) + 1
        # Asset-asset cross
        for ai in range(len(assets)):
            for aj in range(ai + 1, len(assets)):
                key = (f"asset:{assets[ai]}", f"asset:{assets[aj]}")
                edge_counts[key] = edge_counts.get(key, 0) + 1
        # Institution-institution cross
        institutions_sorted = sorted(institutions)
        for ii in range(len(institutions_sorted)):
            for ij in range(ii + 1, len(institutions_sorted)):
                key = (f"inst:{institutions_sorted[ii]}", f"inst:{institutions_sorted[ij]}")
                edge_counts[key] = edge_counts.get(key, 0) + 1

    nodes: list[GraphNode] = []
    for asset in sorted(asset_seen):
        nodes.append(
            GraphNode(
                id=f"asset:{asset}",
                label=asset.replace("_", "/"),
                kind="asset",
                weight=node_degree.get(f"asset:{asset}", 0),
            )
        )
    for inst in sorted(inst_seen):
        nodes.append(
            GraphNode(
                id=f"inst:{inst}",
                label=inst,
                kind="institution",
                weight=node_degree.get(f"inst:{inst}", 0),
            )
        )

    edges = [
        GraphEdge(source=s, target=t, weight=w, kind="MENTIONS_TOGETHER")
        for (s, t), w in edge_counts.items()
    ]
    edges.sort(key=lambda e: e.weight, reverse=True)

    return GraphOut(
        window_hours=hours,
        nodes=nodes,
        edges=edges,
        n_news=n_news,
    )


# ────────────────────────── Canonical causal map ──────────────────────


# Pre-coded macro causality — these are the edges Ichor's brain
# uses internally as the "transmission" framework. They're canonical,
# not data-derived, so no DB query needed.
_CAUSAL_NODES: list[tuple[str, str, NodeKind]] = [
    ("speaker:Powell", "Powell", "institution"),
    ("speaker:Lagarde", "Lagarde", "institution"),
    ("speaker:Ueda", "Ueda", "institution"),
    ("inst:Fed", "Fed", "institution"),
    ("inst:ECB", "ECB", "institution"),
    ("inst:BoJ", "BoJ", "institution"),
    ("asset:USD", "USD", "asset"),
    ("asset:EUR", "EUR", "asset"),
    ("asset:JPY", "JPY", "asset"),
    ("asset:DXY", "DXY", "asset"),
    ("asset:XAU_USD", "XAU/USD", "asset"),
    ("asset:US10Y", "US10Y", "asset"),
    ("asset:DFII10", "TIPS real yield", "asset"),
    ("asset:NAS100_USD", "NAS100", "asset"),
    ("asset:SPX500_USD", "SPX500", "asset"),
    ("asset:WTI", "WTI", "asset"),
]


_CAUSAL_EDGES: list[tuple[str, str, int]] = [
    ("speaker:Powell", "inst:Fed", 5),
    ("speaker:Lagarde", "inst:ECB", 5),
    ("speaker:Ueda", "inst:BoJ", 5),
    ("inst:Fed", "asset:US10Y", 4),
    ("inst:ECB", "asset:EUR", 4),
    ("inst:BoJ", "asset:JPY", 4),
    ("asset:US10Y", "asset:USD", 3),
    ("asset:USD", "asset:DXY", 4),
    ("asset:DXY", "asset:XAU_USD", 4),
    ("asset:DFII10", "asset:XAU_USD", 5),
    ("asset:US10Y", "asset:NAS100_USD", 3),
    ("asset:US10Y", "asset:SPX500_USD", 3),
    ("inst:Fed", "asset:DFII10", 3),
    ("asset:WTI", "asset:USD", 2),
]


@router.get("/causal-map", response_model=GraphOut)
async def causal_map() -> GraphOut:
    """Static canonical causal map used by the brain transmission logic."""
    nodes = [
        GraphNode(id=node_id, label=label, kind=kind, weight=5)
        for node_id, label, kind in _CAUSAL_NODES
    ]
    edges = [
        GraphEdge(source=s, target=t, weight=w, kind="CAUSAL_FORWARD") for s, t, w in _CAUSAL_EDGES
    ]
    return GraphOut(
        window_hours=0,
        nodes=nodes,
        edges=edges,
        n_news=0,
    )


# ────────────────────────── Causal shock simulator ─────────────────────


class ShockRequest(BaseModel):
    shock_node: str
    shock_probability: float = 1.0


class NodeImpactOut(BaseModel):
    node_id: str
    probability: float
    hops_from_shock: int


class ShockResponse(BaseModel):
    shock_node: str
    shock_probability: float
    impacts: list[NodeImpactOut]


@router.get("/shock-nodes", response_model=list[str])
async def shock_nodes() -> list[str]:
    """All nodes that can originate a shock (have outgoing edges)."""
    return supported_shock_nodes()


@router.post("/shock", response_model=ShockResponse)
async def shock(body: ShockRequest) -> ShockResponse:
    """Forward-propagate a shock through the canonical causal map.

    VISION_2026 delta L (proxy form, no observational CPT fitting yet).
    """
    try:
        impacts = propagate_shock(
            shock_node=body.shock_node,
            shock_probability=body.shock_probability,
        )
    except ValueError as e:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ShockResponse(
        shock_node=body.shock_node,
        shock_probability=body.shock_probability,
        impacts=[
            NodeImpactOut(
                node_id=i.node_id,
                probability=i.probability,
                hops_from_shock=i.hops_from_shock,
            )
            for i in impacts
        ],
    )
