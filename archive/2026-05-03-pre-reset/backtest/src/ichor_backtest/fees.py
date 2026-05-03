"""Fee + slippage models.

We start with a simple flat-bps model that's good enough for liquid FX +
indices on daily bars. Per-asset configurability so we can tighten on
crowded pairs (EUR/USD ~0.5 bps round-trip on retail) and loosen on
exotic / metals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class FeeSlippageModel(Protocol):
    """Compute the effective fill price given side + reference price."""

    def fill_price(self, side: str, reference_price: float, asset: str) -> float:
        """Return the price at which an order of `side` ('buy' / 'sell')
        actually fills, given a reference (mid or close) price.
        """
        ...

    def round_trip_cost_bps(self, asset: str) -> float:
        """Total round-trip cost in basis points (fee + slippage, both sides)."""
        ...


@dataclass
class FlatFeeSlippageModel:
    """Flat per-side fee + flat per-side slippage in bps, optionally
    per-asset overridable.
    """

    fee_bps: float = 1.0
    slippage_bps: float = 1.0
    per_asset_overrides: dict[str, tuple[float, float]] = field(default_factory=dict)
    """asset → (fee_bps, slippage_bps)"""

    def _params(self, asset: str) -> tuple[float, float]:
        return self.per_asset_overrides.get(asset, (self.fee_bps, self.slippage_bps))

    def fill_price(self, side: str, reference_price: float, asset: str) -> float:
        fee, slip = self._params(asset)
        # Buy side : fill above reference (worse for us). Sell : below.
        impact_bps = fee + slip
        sign = 1.0 if side == "buy" else -1.0
        return reference_price * (1.0 + sign * impact_bps / 10_000.0)

    def round_trip_cost_bps(self, asset: str) -> float:
        fee, slip = self._params(asset)
        return 2 * (fee + slip)
