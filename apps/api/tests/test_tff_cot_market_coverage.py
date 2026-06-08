"""Anti-drift guard: data_pool consumer market codes ⊆ collector codes.

The S04 liveness gate (`_section_tff_positioning` / `_section_cot`) keys on a
market code looked up via `_TFF_MARKET_BY_ASSET` / `_COT_MARKET_BY_ASSET`. If
data_pool consumes a code the collector never fetches, the gate would mark it
permanently ABSENT (a self-inflicted false degraded) instead of surfacing a
real collector gap. These tests pin the invariant `consumer ⊆ collector` so a
typo or a new asset added to data_pool without the matching collector entry
fails CI rather than silently degrading the pool.
"""

from __future__ import annotations

from ichor_api.collectors.cftc_tff import TRACKED_MARKET_CODES
from ichor_api.collectors.cot import MARKET_CODE_TO_ASSET
from ichor_api.services.data_pool import _COT_MARKET_BY_ASSET, _TFF_MARKET_BY_ASSET


def test_tff_consumer_codes_subset_of_collector() -> None:
    """Every TFF market code data_pool reads must be in the collector's
    `TRACKED_MARKET_CODES` whitelist (else it can never be persisted)."""
    consumed = set(_TFF_MARKET_BY_ASSET.values())
    collected = set(TRACKED_MARKET_CODES)
    missing = consumed - collected
    assert not missing, (
        f"data_pool._TFF_MARKET_BY_ASSET consumes TFF market codes the "
        f"cftc_tff collector never fetches: {sorted(missing)}"
    )


def test_cot_consumer_codes_subset_of_collector() -> None:
    """Every COT market code data_pool reads must be a key in the collector's
    `MARKET_CODE_TO_ASSET` map (else it can never be persisted)."""
    consumed = set(_COT_MARKET_BY_ASSET.values())
    collected = set(MARKET_CODE_TO_ASSET.keys())
    missing = consumed - collected
    assert not missing, (
        f"data_pool._COT_MARKET_BY_ASSET consumes COT market codes the "
        f"cot collector never fetches: {sorted(missing)}"
    )
