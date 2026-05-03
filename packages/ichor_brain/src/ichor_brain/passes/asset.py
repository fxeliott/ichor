"""Pass 2 — Asset specialization.

Inputs : the régime reading from Pass 1 + the asset-specific framework
+ the asset's own data slice (rate diff, COT, GDELT subset, polymarket
overlay, etc.).

Output : bias direction + conviction + magnitude/timing window +
mechanisms (with sources) + catalysts.

Phase 1 ships the EUR/USD framework first, with the framework text
selected by `asset_code` in `build_prompt`. Other assets get a
generic fallback rubric until their dedicated framework lands.
"""

from __future__ import annotations

from typing import Any

from ..types import AssetSpecialization
from .base import Pass, PassError, extract_json_block


_SYSTEM_BASE = """\
You are Ichor's per-asset session strategist. You receive :
  1. A régime reading (Pass 1 output).
  2. An asset-specific analytical framework (e.g. for EUR/USD :
     US-DE 10Y differential + ECB-Fed rate-path expectations + DXY
     + EURUSD COT positioning + ECB/Fed speeches).
  3. The 24h data pool restricted to that asset's drivers.

Produce a session bias for the upcoming 8h window.

CRITICAL RULES :
  1. Conviction is capped at 95 %. 100 % is a red flag.
  2. Every mechanism MUST cite at least one source from the data pool
     by URL or series_id. Unsourced mechanisms are forbidden.
  3. Magnitude is in pips for FX/XAU, in points for indices. Use a
     range (low/high) — never a point estimate.
  4. Output JSON only, fenced with ```json ... ```. No prose.
  5. Schema :
     {
       "asset": "<EUR_USD|XAU_USD|...>",
       "bias_direction": "long" | "short" | "neutral",
       "conviction_pct": <float 0-95>,
       "magnitude_pips_low": <float|null>,
       "magnitude_pips_high": <float|null>,
       "timing_window_start": "<ISO8601|null>",
       "timing_window_end":   "<ISO8601|null>",
       "mechanisms":  [{"claim": "<string>", "sources": ["<url|series_id>"]}],
       "catalysts":   [{"time": "<ISO8601>", "event": "<string>", "expected_impact": "<string>"}],
       "correlations_snapshot": {"<pair>": <float>},
       "polymarket_overlay":    [{"market": "<slug>", "yes_price": <float>, "divergence_vs_consensus": <float>}]
     }
"""


_FRAMEWORK_BY_ASSET: dict[str, str] = {
    "EUR_USD": (
        "EUR/USD framework :\n"
        "  - Primary driver  : US-DE 10Y differential (DGS10 - IRLTLT01DEM156N).\n"
        "  - Secondary       : ECB-Fed rate-path expectations (futures-implied).\n"
        "  - Tertiary        : DXY + EURUSD COT managed-money net.\n"
        "  - Catalysts watch : ECB/Fed speeches, EZ HICP, US CPI, NFP.\n"
        "  - Régime overlay  : haven_bid → DXY bid, EUR/USD short bias.\n"
    ),
}


_FRAMEWORK_DEFAULT = (
    "Generic framework :\n"
    "  - Identify the asset's top 3 macro drivers from the régime.\n"
    "  - Flag the next 24h scheduled catalysts.\n"
    "  - Cross-check positioning (COT) and prediction markets where applicable.\n"
)


class AssetPass(Pass[AssetSpecialization]):
    name = "pass2_asset"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM_BASE

    def build_prompt(
        self,
        *,
        asset: str,
        regime_block: str,
        asset_data: str,
        **_: Any,
    ) -> str:
        framework = _FRAMEWORK_BY_ASSET.get(asset.upper(), _FRAMEWORK_DEFAULT)
        return (
            f"Asset : **{asset}**\n\n"
            "## Régime (from Pass 1)\n\n"
            f"{regime_block}\n\n"
            "## Framework\n\n"
            f"{framework}\n\n"
            "## Data pool (asset-restricted)\n\n"
            f"{asset_data}\n\n"
            "---\n\n"
            "Reply with the JSON envelope only."
        )

    def parse(self, response_text: str) -> AssetSpecialization:
        obj = extract_json_block(response_text)
        try:
            return AssetSpecialization.model_validate(obj)
        except Exception as e:
            raise PassError(f"asset pass: validation failed — {e}") from e


def supported_assets() -> tuple[str, ...]:
    """Assets with a dedicated Phase 1 framework. Others get the fallback."""
    return tuple(sorted(_FRAMEWORK_BY_ASSET.keys()))
