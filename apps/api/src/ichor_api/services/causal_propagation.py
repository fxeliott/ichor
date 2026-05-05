"""Causal forward-propagation on the macro causal map.

Pure-Python Bayesian-lite : given a "shock" at one node with a
probability, propagate the impact downstream by interpreting each
directed edge weight as a conditional transmission probability.

   P(target | source) = clamp(weight / 5, 0..1)

(weight 5 = canonical edges have P = 1 ; weight 1 → P = 0.2)

For each downstream node we accumulate via "noisy-OR" :
   P(node) = 1 − ∏( 1 − P(parent) * P(node|parent) )

This is a simplified discrete CBN ; full pgmpy support stays
deferred to Phase 3 once we have observational data to fit
conditional probability tables. The discrete version is enough to
power the UI "what happens if Powell turns hawkish?" simulator.

VISION_2026 delta L — proxy version.
"""

from __future__ import annotations

from dataclasses import dataclass

# Mirror of routers/graph.py:_CAUSAL_EDGES — kept here because the
# graph router lazy-imports this module ; circular import otherwise.
# Edge weights : 5 = canonical certain transmission, 1 = weak.
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

# Maximum hops we propagate before stopping (avoid runaway loops on
# any future cyclic edge).
_MAX_HOPS = 6


def _children(node: str) -> list[tuple[str, float]]:
    """Outgoing edges + their conditional probability."""
    out: list[tuple[str, float]] = []
    for s, t, w in _CAUSAL_EDGES:
        if s == node:
            p = max(0.0, min(1.0, w / 5.0))
            out.append((t, p))
    return out


@dataclass(frozen=True)
class NodeImpact:
    node_id: str
    probability: float
    """Probability of being affected by the shock, in [0, 1]."""
    hops_from_shock: int
    """Path length from the originating shock node."""


def propagate_shock(
    *,
    shock_node: str,
    shock_probability: float,
) -> list[NodeImpact]:
    """Forward-propagate a shock from `shock_node` along causal edges.

    Returns a list of NodeImpact with probability > 0.01, sorted by
    probability descending. The shock node itself is included with
    probability = `shock_probability`.

    Algorithm :
      - Initialise P[shock_node] = shock_probability, all others = 0.
      - For up to _MAX_HOPS rounds, propagate :
          For each parent with P > 0 :
              For each child :
                  P[child] = 1 - (1 - P[child]) * (1 - P[parent] * P(child|parent))
      - Stop when no node's probability changes by more than 1e-3.
    """
    if not (0.0 <= shock_probability <= 1.0):
        raise ValueError("shock_probability must be in [0, 1]")

    probs: dict[str, float] = {shock_node: shock_probability}
    hops: dict[str, int] = {shock_node: 0}

    for round_n in range(1, _MAX_HOPS + 1):
        any_change = False
        for parent, p_parent in list(probs.items()):
            if p_parent <= 0:
                continue
            for child, cond in _children(parent):
                added = p_parent * cond
                prev = probs.get(child, 0.0)
                new = 1.0 - (1.0 - prev) * (1.0 - added)
                if new - prev > 1e-3:
                    probs[child] = new
                    any_change = True
                    if child not in hops or hops[child] > round_n:
                        hops[child] = round_n
        if not any_change:
            break

    out = [
        NodeImpact(
            node_id=node,
            probability=round(p, 4),
            hops_from_shock=hops.get(node, 0),
        )
        for node, p in probs.items()
        if p > 0.01
    ]
    out.sort(key=lambda x: x.probability, reverse=True)
    return out


def supported_shock_nodes() -> list[str]:
    """All nodes that have outgoing edges (i.e. can be a shock origin)."""
    seen: set[str] = set()
    for s, _, _ in _CAUSAL_EDGES:
        seen.add(s)
    return sorted(seen)
