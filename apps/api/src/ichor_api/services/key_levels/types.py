"""KeyLevel canonical type per ADR-083 D3 spec.

Frozen dataclass so consumers can't accidentally mutate a level's
threshold mid-pipeline. The `to_dict()` helper produces the exact
shape ADR-083 D3 prescribes for `key_levels[]` JSONB array.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Closed enum of recognized "kind" values per ADR-083 D3.
# Adding a new kind = ADR amendment. Catches future drift.
KeyLevelKind = Literal[
    "tga_liquidity_gate",
    "rrp_liquidity_gate",
    "gamma_flip",
    "peg_break_hkma",
    "peg_break_pboc_fix",
    "vix_regime_switch",
    "skew_regime_switch",
    "hy_oas_percentile",
    "polymarket_decision",
]

# Direction semantics. ADR-083 D3 example uses
# "above_long_below_short" (gamma flip) but the doctrine generalises
# to any threshold-driven switch.
KeyLevelSide = Literal[
    "above_long_below_short",
    "above_short_below_long",
    "above_risk_off_below_risk_on",
    "above_risk_on_below_risk_off",
    "above_liquidity_drain_below_inject",
    "above_liquidity_inject_below_drain",
    "neutral",
]


@dataclass(frozen=True)
class KeyLevel:
    """One fundamental / non-technical level acting as a macro switch.

    Attributes :
        asset : asset code OR cross-asset marker (e.g. "USD" for TGA
            which impacts all USD pairs ; "NAS100" for SPX gamma flip).
        level : numeric threshold value in the level's natural units
            (USD billions for TGA, basis points for OAS, etc.).
        kind : one of `KeyLevelKind` enum.
        side : one of `KeyLevelSide` enum.
        source : provenance string with date stamp (e.g.
            "FRED:WTREGEN 2026-05-13").
        note : optional 1-line context for Pass 2 (e.g. "Latest TGA
            $815B is above $700B drain threshold").
    """

    asset: str
    level: float
    kind: KeyLevelKind
    side: KeyLevelSide
    source: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to ADR-083 D3 spec JSONB shape."""
        out: dict[str, Any] = {
            "asset": self.asset,
            "level": self.level,
            "kind": self.kind,
            "side": self.side,
            "source": self.source,
        }
        if self.note:
            out["note"] = self.note
        return out

    def to_markdown_line(self) -> str:
        """Render as a single Markdown bullet for data_pool section."""
        line = f"- **{self.kind}** ({self.asset}) : level={self.level}, side={self.side}"
        if self.note:
            line += f" — {self.note}"
        line += f" [{self.source}]"
        return line
