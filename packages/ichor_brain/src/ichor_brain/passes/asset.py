"""Pass 2 — Asset specialization.

Inputs : the régime reading from Pass 1 + the asset-specific framework
+ the asset's own data slice (rate diff, COT, GDELT subset, polymarket
overlay, etc.).

Output : bias direction + conviction + magnitude/timing window +
mechanisms (with sources) + catalysts.

Phase 1 ships the EUR/USD framework first ; Phase 1 Step 2 (commit on
2026-05-03) adds explicit frameworks for the 7 other Phase-1 assets so
no asset falls back to the generic rubric anymore.

Each framework is a short text block describing :
  - the **primary driver** (the macro/positioning quantity that
    historically explains > 50 % of session-window variance for that
    asset),
  - **secondary** drivers,
  - **catalysts watch** (scheduled events that can swing the bias),
  - **régime overlay** (how the régime quadrant from Pass 1 should bend
    the framework's directional prior).

Drivers are sourced from the canonical macro literature for each asset
(see `docs/research/macro-frameworks-2026.md` for the full taxonomy).
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


# ─────────────────────────────── Frameworks ──────────────────────────────
# Each block is consumed verbatim by the LLM. Keep them tight ; the prompt
# cache breakpoint sits *after* the system prompt, so each framework adds
# uncached tokens per session card. Aim for < 60 tokens per framework.

_FRAMEWORK_EUR_USD = (
    "EUR/USD framework :\n"
    "  - Primary driver  : US-DE 10Y differential (DGS10 - IRLTLT01DEM156N).\n"
    "  - Secondary       : ECB-Fed rate-path expectations (futures-implied).\n"
    "  - Tertiary        : DXY + EURUSD COT managed-money net.\n"
    "  - Catalysts watch : ECB/Fed speeches, EZ HICP, US CPI, NFP.\n"
    "  - Régime overlay  : haven_bid → DXY bid, EUR/USD short bias.\n"
)

_FRAMEWORK_GBP_USD = (
    "GBP/USD framework :\n"
    "  - Primary driver  : US-UK 10Y differential (DGS10 - UK10Y gilt).\n"
    "  - Secondary       : BoE NLP hawk/dove + UK CPI/wages prints.\n"
    "  - Tertiary        : DXY + GBPUSD COT specs + EU-UK PMI gap.\n"
    "  - Catalysts watch : BoE MPC, UK CPI, UK wages, US CPI/NFP.\n"
    "  - Régime overlay  : funding_stress → cable underperforms vs DXY.\n"
)

_FRAMEWORK_USD_JPY = (
    "USD/JPY framework :\n"
    "  - Primary driver  : US-JP 10Y differential (DGS10 - JGB 10Y).\n"
    "  - Secondary       : BoJ YCC stance + Tokyo fixing direction (9:55 JST).\n"
    "  - Tertiary        : JPY safe-haven flag + MOF intervention proximity.\n"
    "  - Catalysts watch : BoJ statements, US Treasury yields, MoF FX.\n"
    "  - Régime overlay  : haven_bid → JPY bid, USD/JPY short pressure.\n"
    "  - Tail risk       : MoF intervention probability rises sharply > 152.\n"
)

_FRAMEWORK_AUD_USD = (
    "AUD/USD framework :\n"
    "  - Primary driver  : China activity proxies (PMI, credit impulse).\n"
    "  - Secondary       : Iron ore + LME copper momentum (HG=F).\n"
    "  - Tertiary        : RBA NLP + AUDUSD COT + AU-US 2Y diff.\n"
    "  - Catalysts watch : RBA, China data, US-China trade headlines.\n"
    "  - Régime overlay  : funding_stress → AUD short alongside copper sell-off.\n"
)

_FRAMEWORK_USD_CAD = (
    "USD/CAD framework :\n"
    "  - Primary driver  : WTI crude (CL=F) — high inverse correlation.\n"
    "  - Secondary       : BoC stance + Canadian CPI + US-CA 2Y diff.\n"
    "  - Tertiary        : Baker Hughes US oil rig count weekly.\n"
    "  - Catalysts watch : BoC, Canadian CPI, EIA crude stocks, OPEC+.\n"
    "  - Régime overlay  : haven_bid + oil down → USD/CAD long.\n"
)

_FRAMEWORK_XAU_USD = (
    "XAU/USD framework :\n"
    "  - Primary driver  : 10Y TIPS real yield (DFII10) — strong inverse.\n"
    "  - Secondary       : DXY + central bank gold buying (WGC quarterly).\n"
    "  - Tertiary        : SPDR Gold Trust ETF flows + gold-silver ratio.\n"
    "  - Catalysts watch : US CPI, real-yield prints, FOMC, geopolitical flash.\n"
    "  - Régime overlay  : haven_bid + funding_stress both gold-bullish.\n"
    "  - Tail risk       : real yields > 2.5 % historically caps gold rallies.\n"
)

_FRAMEWORK_NAS100_USD = (
    "NAS100 framework :\n"
    "  - Primary driver  : US 10Y nominal (DGS10) — duration sensitivity.\n"
    "  - Secondary       : Mega-cap 7 earnings momentum (AAPL/MSFT/GOOGL/\n"
    "                      AMZN/META/NVDA/TSLA) + AI capex narrative.\n"
    "  - Tertiary        : SPX/NDX 0DTE GEX (FlashAlpha) + VIX term slope.\n"
    "  - Catalysts watch : Mega-cap earnings, US CPI, FOMC, NFP, AI events.\n"
    "  - Régime overlay  : goldilocks → NAS100 long ; funding_stress → short.\n"
    "  - Magnitude unit  : POINTS (NDX index points), not pips.\n"
)

_FRAMEWORK_SPX500_USD = (
    "SPX500 framework :\n"
    "  - Primary driver  : Broad US macro (ISM, NFP, CPI) + Fed-cut probability.\n"
    "  - Secondary       : SPX dealer GEX + VIX term slope (VIX9D vs VIX3M).\n"
    "  - Tertiary        : HY OAS (BAMLH0A0HYM2) — credit risk-off proxy.\n"
    "  - Catalysts watch : NFP, US CPI, FOMC, ISM, large earnings.\n"
    "  - Régime overlay  : funding_stress → SPX short ; goldilocks → long.\n"
    "  - Magnitude unit  : POINTS (SPX index points), not pips.\n"
)

# Synonym for what ADR-017 calls "US100" / "US30" — left as aliases so the
# orchestrator can pass either ticker convention.
_FRAMEWORK_US100 = _FRAMEWORK_NAS100_USD
_FRAMEWORK_US30 = (
    "US30 (Dow) framework :\n"
    "  - Primary driver  : Cyclical earnings (industrials, financials, energy).\n"
    "  - Secondary       : ISM Manufacturing + oil price + Fed-cut probability.\n"
    "  - Tertiary        : DJI dealer GEX + USD strength (cyclical FX exposure).\n"
    "  - Catalysts watch : ISM, NFP, CPI, FOMC, oil-related events.\n"
    "  - Régime overlay  : goldilocks + oil bid → US30 long.\n"
    "  - Magnitude unit  : POINTS (DJI index points), not pips.\n"
)

_FRAMEWORK_BY_ASSET: dict[str, str] = {
    "EUR_USD": _FRAMEWORK_EUR_USD,
    "GBP_USD": _FRAMEWORK_GBP_USD,
    "USD_JPY": _FRAMEWORK_USD_JPY,
    "AUD_USD": _FRAMEWORK_AUD_USD,
    "USD_CAD": _FRAMEWORK_USD_CAD,
    "XAU_USD": _FRAMEWORK_XAU_USD,
    "NAS100_USD": _FRAMEWORK_NAS100_USD,
    "SPX500_USD": _FRAMEWORK_SPX500_USD,
    # ADR-017 ticker aliases (US100 / US30) — keep both spellings live.
    "US100": _FRAMEWORK_US100,
    "US30": _FRAMEWORK_US30,
}


_FRAMEWORK_DEFAULT = (
    "Generic framework (no dedicated rubric for this asset yet) :\n"
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
        # Strip any underscore-prefixed meta keys (Claude sometimes emits
        # `_caveats`, `_notes`, etc. as commentary that shouldn't break the
        # schema). The underscore prefix is the convention for "private /
        # informational only" fields in JSON-LD style.
        if isinstance(obj, dict):
            obj = {k: v for k, v in obj.items() if not k.startswith("_")}
        try:
            return AssetSpecialization.model_validate(obj)
        except Exception as e:
            raise PassError(f"asset pass: validation failed — {e}") from e


def supported_assets() -> tuple[str, ...]:
    """Assets with a dedicated Phase 1 framework. Others get the fallback."""
    return tuple(sorted(_FRAMEWORK_BY_ASSET.keys()))
