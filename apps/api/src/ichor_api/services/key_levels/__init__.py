"""Key levels (non-technical / fundamental) — ADR-083 D3.

This package implements the trader-grade contract from ADR-083 §D3 :

> Output must include "niveaux clés" — NOT technical analysis levels
> (Eliot does that on TradingView). Instead, **non-technical /
> fundamental price levels that act as macro/microstructure switches**.

Categories defined in ADR-083 D3 :

1. **Option gamma flip levels** (SqueezeMetrics dealer GEX)
2. **Peg break thresholds** (HKMA hard 7.80 ; PBOC daily fix CFETS ± 2σ)
3. **Liquidity gates** (Fed TGA WTREGEN, RRP RRPONTSYD)
4. **Polymarket decision thresholds** (binary contract resolution prices)
5. **VIX / SKEW regime switches**
6. **HY OAS regime switches** (BAMLH0A0HYM2 percentile thresholds)

Phase 1 (r54) ships TGA only as proof of pattern. Phase 2+ (r55-r58)
will add peg break, gamma flip, VIX threshold, Polymarket per the
roadmap codified in SESSION_LOG_2026-05-15-r54-EXECUTION.md.

The output format follows ADR-083 D3 spec :

    {"asset": "...", "level": <float>, "kind": "...", "side": "...",
     "source": "..."}

For r54 phase 1, the KeyLevel objects are surfaced via data_pool.py
section markdown (consumed by Pass 2 LLM). r55+ will add JSONB
persistence in session_card_audit + frontend Living Analysis View
rendering per ADR-083 D4.

Voie D respect : pure-Python computation from already-collected
upstream data. ZERO LLM call. ZERO new paid feed. ZERO ban-risk
(per ADR-091 §invariants).
"""

from .gamma_flip import compute_gamma_flip_levels
from .peg_break import compute_hkma_peg_break
from .tga import compute_tga_key_level
from .types import KeyLevel

__all__ = [
    "KeyLevel",
    "compute_gamma_flip_levels",
    "compute_hkma_peg_break",
    "compute_tga_key_level",
]
