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
    "DGS3MO",  # 3-month Treasury constant maturity
    "DGS2",  # 2y (already in fred.py — kept for completeness)
    "DGS5",  # 5y
    "DGS10",  # 10y (already)
    "DGS30",  # 30y
    "T10Y2Y",  # 10Y - 2Y spread (recession signal)
    "T10Y3M",  # 10Y - 3M spread (NY Fed preferred)
    # ─── Real yields (TIPS) ───
    "DFII5",  # 5Y TIPS real yield
    "DFII10",  # 10Y TIPS real yield (PRIMARY gold driver)
    "DFII30",  # 30Y TIPS real yield
    # ─── Term premium (Phase E.2 / ADR-041) ───
    # Kim-Wright model term premium on 10Y zero-coupon Treasury.
    # NB: FRED hosts the KW model under THREEFYTP10 ; the strict ACM
    # series (Adrian-Crump-Moench) lives on the NY Fed website only.
    # Per Federal Reserve note 2017-04-03, KW and ACM agree to within
    # bps once survey-rate-expectations are matched. We use KW because
    # it's free, daily, and FRED-hosted.
    "THREEFYTP10",
    # ─── Inflation expectations ───
    "T5YIE",  # 5Y breakeven inflation
    "T10YIE",  # 10Y breakeven inflation
    "T5YIFR",  # 5Y5Y forward inflation expectations
    # ─── Credit spreads ───
    "BAMLH0A0HYM2",  # HY OAS (already in fred.py)
    "BAMLC0A0CM",  # IG OAS
    "BAMLEMHYHYTRIV",  # EM HY total return (sentiment proxy)
    # ─── Liquidity ───
    "WALCL",  # Fed balance sheet (already)
    "WTREGEN",  # Treasury General Account (already)
    "RRPONTSYD",  # Reverse Repo (already)
    "M2SL",  # M2 (already)
    # ─── Fed H.4.1 detail (Phase II Layer 1, Wave 23) ───
    # WALCL is a single number; the H.4.1 sub-components below let us
    # disaggregate balance-sheet drivers (active QT vs runoff).
    "WSHOSHO",  # Treasuries held outright (UST runoff cap signal)
    "WSHOMCB",  # MBS held outright (mortgage convexity / housing channel)
    "WRESBAL",  # Reserve balances at Federal Reserve Banks
    # ─── Macro nowcasts (Phase II Layer 1, Wave 23) ───
    # Atlanta Fed GDPNow: real-time GDP nowcast updated 6-7×/month after
    # each headline release. Critical for regime classification (PCE/IPP/
    # net exports nowcasts feed the dollar smile + risk appetite blocks).
    "GDPNOW",  # Atlanta Fed GDP nowcast (composite)
    "PCENOW",  # Atlanta Fed PCE component nowcast
    # ─── Dollar smile / FX ───
    "DTWEXBGS",  # Trade-weighted dollar broad (DXY proxy, already)
    "DTWEXAFEGS",  # Trade-weighted dollar advanced foreign economies
    # ─── Vol ───
    "VIXCLS",  # VIX (already)
    "VXVCLS",  # VIX 3-month (term structure with VIXCLS)
    "GVZCLS",  # CBOE Gold ETF Volatility Index (GLD vol — XAU exposure)
    "OVXCLS",  # CBOE Crude Oil ETF Volatility Index (USO vol — energy exposure)
    # ─── Vol surface completion (Phase II Layer 1, Wave 28) ───
    # RVX = CBOE Russell 2000 Volatility Index. Small-cap-vol completes
    # the equity vol surface (VIX large-cap + RVX small-cap + VXV term).
    # VVIX (vol of VIX) is NOT on FRED — would require separate Yahoo
    # collector, deferred to a future wave.
    "RVXCLS",  # CBOE Russell 2000 Volatility Index (small-cap vol)
    # ─── Sentiment / risk appetite ───
    "UMCSENT",  # U Michigan Consumer Sentiment (monthly)
    "CSCICP03USM665S",  # OECD US Composite Consumer Confidence Index
    "DRTSCILM",  # Bank lending standards : tighter for C&I loans (qoq)
    # ─── Energy ───
    "DCOILWTICO",  # WTI (already)
    "DCOILBRENTEU",  # Brent
    "DGASRGW",  # Gasoline
    "DHHNGSP",  # Henry Hub natural gas
    # ─── Commodities ───
    "GOLDAMGBD228NLBM",  # Gold London PM (already)
    "PALLFNFUSDM",  # Palladium
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
