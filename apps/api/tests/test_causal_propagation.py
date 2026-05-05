"""Pure tests for the causal-propagation Bayesian-lite engine."""

from __future__ import annotations

import itertools

import pytest
from ichor_api.services.causal_propagation import (
    NodeImpact,
    propagate_shock,
    supported_shock_nodes,
)


def test_supported_shock_nodes_includes_speakers_and_assets() -> None:
    nodes = supported_shock_nodes()
    assert "speaker:Powell" in nodes
    assert "inst:Fed" in nodes
    assert "asset:US10Y" in nodes


def test_propagate_powell_hawkish_reaches_xau() -> None:
    """Powell hawkish should ripple to XAU (via Fed → US10Y/DFII10 → XAU)."""
    impacts = propagate_shock(shock_node="speaker:Powell", shock_probability=1.0)
    by_id = {i.node_id: i for i in impacts}

    assert "speaker:Powell" in by_id
    assert by_id["speaker:Powell"].probability == 1.0
    assert "inst:Fed" in by_id
    assert by_id["inst:Fed"].probability == 1.0  # weight 5 → P=1
    assert "asset:US10Y" in by_id
    assert by_id["asset:US10Y"].probability >= 0.5  # weight 4 → P=0.8
    assert "asset:XAU_USD" in by_id
    assert 0 < by_id["asset:XAU_USD"].probability <= 1.0


def test_propagate_includes_shock_node_with_full_probability() -> None:
    impacts = propagate_shock(shock_node="speaker:Lagarde", shock_probability=0.7)
    by_id = {i.node_id: i for i in impacts}
    assert by_id["speaker:Lagarde"].probability == 0.7


def test_propagate_zero_probability_returns_only_shock_node() -> None:
    impacts = propagate_shock(shock_node="speaker:Powell", shock_probability=0.0)
    # Shock node itself has prob 0 → filtered by > 0.01
    assert impacts == []


def test_propagate_validates_probability_range() -> None:
    with pytest.raises(ValueError):
        propagate_shock(shock_node="speaker:Powell", shock_probability=-0.5)
    with pytest.raises(ValueError):
        propagate_shock(shock_node="speaker:Powell", shock_probability=1.5)


def test_propagate_unknown_node_yields_only_self() -> None:
    """No outgoing edges → only the shock node itself surfaces."""
    impacts = propagate_shock(shock_node="asset:UNKNOWN_FAKE_NODE", shock_probability=0.9)
    assert len(impacts) == 1
    assert impacts[0].node_id == "asset:UNKNOWN_FAKE_NODE"


def test_propagate_results_sorted_descending() -> None:
    impacts = propagate_shock(shock_node="speaker:Powell", shock_probability=1.0)
    for a, b in itertools.pairwise(impacts):
        assert a.probability >= b.probability


def test_propagate_hops_increase_with_distance() -> None:
    impacts = propagate_shock(shock_node="speaker:Powell", shock_probability=1.0)
    by_id = {i.node_id: i for i in impacts}
    # Powell is hop 0, Fed is hop 1 (direct edge), US10Y hop 2 (Fed→US10Y),
    # USD is hop 3 (US10Y→USD), DXY hop 4, XAU_USD hop 5
    assert by_id["speaker:Powell"].hops_from_shock == 0
    assert by_id["inst:Fed"].hops_from_shock == 1
    assert by_id["asset:US10Y"].hops_from_shock == 2
    assert by_id["asset:USD"].hops_from_shock >= 3


def test_node_impact_is_frozen() -> None:
    """Mutability would corrupt the cached propagation if any."""
    import dataclasses

    n = NodeImpact(node_id="x", probability=0.5, hops_from_shock=1)
    try:
        n.probability = 0.6  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("NodeImpact must be frozen")


def test_lagarde_does_not_reach_xau_via_powell() -> None:
    """Sanity check : Lagarde's shock doesn't leak to Powell's chain."""
    impacts = propagate_shock(shock_node="speaker:Lagarde", shock_probability=1.0)
    by_id = {i.node_id: i for i in impacts}
    assert "asset:EUR" in by_id
    # No edge from speaker:Lagarde to inst:Fed or asset:USD chain
    assert "speaker:Powell" not in by_id
    assert "inst:Fed" not in by_id
