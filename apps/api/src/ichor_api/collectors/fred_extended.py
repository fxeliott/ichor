"""FRED extended series — beyond the 19 series in fred.py.

Adds the macro trinity + financial conditions + liquidity proxies needed
for the régime detection Pass 1 of the Claude pipeline.

Inspired by `docs/research/macro-frameworks-2026.md` :
  - Macro trinity (DXY + 10Y + VIX) — already partially in fred.py
  - Real yields (DFII10) → primary gold driver
  - Term structure (T10Y2Y, T10Y3M) → recession signal
  - Credit spreads (BAMLH0A0HYM2 already present)
  - Dollar smile inputs (DTWEXBGS DXY proxy)
  - Liquidity (WALCL, WTREGEN, RRPONTSYD)
  - Inflation expectations (T5YIE, T5YIFR)
  - MOVE Index proxy (no FRED MOVE — fall back to BAMLC0A0CM as IG-OAS proxy)
  - Fed Funds futures via FEDFUNDS

This collector reuses the same FRED API + key as the original fred.py.
"""

from __future__ import annotations

# Series codes : the macro-trinity, liquidity, inflation expectations,
# dollar smile, term structure, real yields. All FRED-hosted.
EXTENDED_SERIES_TO_POLL: tuple[str, ...] = (
    # ─── Yield curve ───
    "DGS3MO",       # 3-month Treasury constant maturity
    "DGS2",         # 2y (already in fred.py — kept for completeness)
    "DGS5",         # 5y
    "DGS10",        # 10y (already)
    "DGS30",        # 30y
    "T10Y2Y",       # 10Y - 2Y spread (recession signal)
    "T10Y3M",       # 10Y - 3M spread (NY Fed preferred)
    # ─── Real yields (TIPS) ───
    "DFII5",        # 5Y TIPS real yield
    "DFII10",       # 10Y TIPS real yield (PRIMARY gold driver)
    "DFII30",       # 30Y TIPS real yield
    # ─── Inflation expectations ───
    "T5YIE",        # 5Y breakeven inflation
    "T10YIE",       # 10Y breakeven inflation
    "T5YIFR",       # 5Y5Y forward inflation expectations
    # ─── Credit spreads ───
    "BAMLH0A0HYM2", # HY OAS (already in fred.py)
    "BAMLC0A0CM",   # IG OAS
    "BAMLEMHYHYTRIV",  # EM HY total return (sentiment proxy)
    # ─── Liquidity ───
    "WALCL",        # Fed balance sheet (already)
    "WTREGEN",      # Treasury General Account (already)
    "RRPONTSYD",    # Reverse Repo (already)
    "M2SL",         # M2 (already)
    # ─── Dollar smile / FX ───
    "DTWEXBGS",     # Trade-weighted dollar broad (DXY proxy, already)
    "DTWEXAFEGS",   # Trade-weighted dollar advanced foreign economies
    # ─── Vol ───
    "VIXCLS",       # VIX
    "VXVCLS",       # VIX 3-month (term structure with VIXCLS)
    # ─── Energy ───
    "DCOILWTICO",   # WTI (already)
    "DCOILBRENTEU", # Brent
    "DGASRGW",      # Gasoline
    "DHHNGSP",      # Henry Hub natural gas
    # ─── Commodities ───
    "GOLDAMGBD228NLBM",  # Gold London PM (already)
    "PALLFNFUSDM",       # Palladium
    # ─── Macro hard data already covered in fred.py ───
    # CPIAUCSL, PCEPI, PAYEMS, UNRATE, GDPC1, INDPRO, SOFR, DFF
    # ─── Foreign rate differentials ───
    "IRLTLT01DEM156N",  # Germany 10y (for EUR-USD spread)
    "IRLTLT01JPM156N",  # Japan 10y (for USD-JPY)
    "IRLTLT01GBM156N",  # UK 10y (for GBP-USD)
)


def merged_series() -> tuple[str, ...]:
    """All series we want to poll, deduped, in one tuple — combines
    the original `fred.py` SERIES_TO_POLL with EXTENDED_SERIES_TO_POLL.

    Caller can pass this directly to `fred.poll_all(api_key, series=...)`.
    """
    from .fred import SERIES_TO_POLL

    seen: set[str] = set()
    out: list[str] = []
    for s in (*SERIES_TO_POLL, *EXTENDED_SERIES_TO_POLL):
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)
