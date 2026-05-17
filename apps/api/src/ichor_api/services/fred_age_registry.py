"""FRED per-series max-age registry — dependency-free single source of truth.

Extracted r92 (ADR-097 §"future r62+ can extract to a dedicated
services/fred_age_registry.py" — anticipated at ADR-097:23 / :102).

WHY a standalone module : the CI FRED-liveness guard
(`scripts/ci/fred_liveness_check.py`, ADR-097) must read this registry
WITHOUT importing `data_pool.py` (which pulls SQLAlchemy + 33 ORM models
+ ~25 sibling services). The shipped guard imported it from `data_pool`
and the workflow installed only `httpx` → the canonical-source import
failed (exit 4) on every run since r61 (latent Defect A, fixed r92).

This module has ZERO non-stdlib imports by design — it is a pure config
literal so `pip install httpx structlog` is enough for the CI guard.

`data_pool.py` re-exports these under their historic private names
(`_FRED_SERIES_MAX_AGE_DAYS` / `_FRED_DEFAULT_MAX_AGE_DAYS`) so every
runtime caller (`_max_age_days_for`, `_latest_fred`) is byte-identical
(r71/r91 anti-accumulation extract-to-SSOT pattern).

Round-37 r35-audit-gap rationale (preserved verbatim from the original
data_pool.py inline definition) : FRED series have different publication
cadences (daily / weekly / monthly / quarterly). The default 14-day
max-age was calibrated for DAILY series and silently rejected MONTHLY
OECD observations (e.g. IRLTLT01ITM156N which is ~100 days old at read
time per r35 empirical discovery). The registry below maps each
series_id to its appropriate max-age ceiling. Adding a new monthly /
quarterly series WITHOUT a registry entry falls back to the
conservative default AND logs a structlog warning so the operator
notices.
"""

from __future__ import annotations

FRED_SERIES_MAX_AGE_DAYS: dict[str, int] = {
    # ─── MONTHLY OECD / FRED series (1-month publication lag standard) ───
    "IRLTLT01DEM156N": 120,  # Germany 10y monthly (legacy, replaced by Bund daily r29 but kept for fallback)
    "IRLTLT01ITM156N": 120,  # Italy 10y monthly (BTP-Bund spread, ADR-090 step-4 r34+r35)
    "IRLTLT01JPM156N": 120,  # Japan 10y monthly
    "IRLTLT01GBM156N": 120,  # UK 10y monthly
    "IRLTLT01AUM156N": 120,  # Australia 10y monthly (round-46 ADR-092 §T1.AUD-3)
    # ─── IMF Primary Commodity Price System monthly series ───
    # r94 RECALIBRATION (ADR-092 §Round-94 amendment) : the r46 "60d
    # acceptable because IMF PinkBook publishes early-month" assumption
    # was empirically REFUTED by the r93 ADR-103 liveness surface + the
    # r94 R53 triage (prod-DB + live fred.stlouisfed.org primary source) :
    # IMF PCPS publishes month-M ~mid-month-M+1 (~2-week-after-month-end
    # lag), so the freshest observation is INHERENTLY ~75-90d old by
    # period-date in normal operation. 60d false-DEGRADED the AUD
    # iron-ore + copper composite every card. Recalibrated 60→120d to
    # match the monthly-OECD precedent (ADR-092:63 set AU-10Y=120 ; all
    # other monthly series here are 120) ; still catches a genuine
    # China-M1-class death within ~4 months for a composite sub-driver.
    "MYAGM1CNM189N": 60,  # China M1 monthly — GENUINELY DISCONTINUED 2019-08-01
    #                       (latest obs frozen 2019, age ~2481d ; ADR-093
    #                       §r49). Left at 60d INTENTIONALLY : any threshold
    #                       flags a 6-year-dead series ; correctly DEGRADED
    #                       by the ADR-103 surface (do NOT widen — that
    #                       would mask a real dead series). Swap history :
    #                       r46-round-2 from MYAGM2CNM189N (also dead) ;
    #                       credit-impulse proxy per Barcelona et al. 2022
    #                       Fed IFDP 1360 ; TSF direct deferred ADR-092 §DEFER
    "PIORECRUSDM": 120,  # Global Iron Ore Price Index monthly, IMF PCPS — LIVE
    #                      (r94 R53-verified : latest Mar 2026, NOT discontinued).
    #                      60→120 r94 recalibration, ADR-092 §Round-94 amendment.
    "PCOPPUSDM": 120,  # Global Copper Price Index monthly, IMF PCPS — LIVE
    #                    (r94 R53-verified : latest Mar 2026, NOT discontinued).
    #                    60→120 r94 recalibration, ADR-092 §Round-94 amendment.
    "USALOLITOAASTSAM": 120,  # US CLI monthly
    "G7LOLITOAASTSAM": 120,  # G7 aggregate CLI
    "JPNLOLITOAASTSAM": 120,
    "DEULOLITOAASTSAM": 120,
    "GBRLOLITOAASTSAM": 120,
    "CHNLOLITOAASTSAM": 120,
    "EA19LOLITOAASTSAM": 120,
    "UMCSENT": 60,  # U Michigan Consumer Sentiment monthly (preliminary mid-month + final end-of-month)
    "CSCICP03USM665S": 90,  # OECD Consumer Confidence monthly
    "DRTSCILM": 120,  # Senior Loan Officer Survey quarterly
    "USREC": 365,  # NBER Recession Indicator (typically updated at recession turning points only)
    "CIVPART": 45,  # Labor Force Participation monthly
    "AHETPI": 45,  # Average Hourly Earnings monthly
    "ATLSBUSRGEP": 60,  # Atlanta Fed Business Inflation Expectations
    "PSAVERT": 45,  # Personal Saving Rate monthly
    "FEDFUNDS": 45,  # Fed Funds monthly average
    "EXPINF1YR": 60,  # Cleveland Fed expected inflation monthly
    "M2SL": 45,  # M2 monthly
    "WSHOSHO": 30,  # Fed H.4.1 Treasuries weekly
    "WSHOMCB": 30,  # Fed H.4.1 MBS weekly
    "WRESBAL": 30,  # Fed reserve balances weekly
    "GDPC1": 120,  # Real GDP quarterly
    "INDPRO": 45,  # Industrial Production monthly
    "MCUMFN": 45,  # Manufacturing Capacity Utilization monthly
    "CFNAI": 45,  # Chicago Fed National Activity Index monthly
    "CFNAIDIFF": 45,
    "DFEDTARU": 45,  # Fed Funds Target Range Upper (announcement-driven)
    "DFEDTARL": 45,
    "GDPNOW": 14,  # Atlanta Fed GDP nowcast (updated 6-7x/month, but 14d is conservative)
    "PCENOW": 14,
}

# Conservative default for any FRED series NOT in the registry above.
# Suits DAILY series (DGS10, DXY, VIXCLS, etc.). Monthly/quarterly
# series MUST be added to the registry — falling back to 14 silently
# would reintroduce the r35 bug class.
FRED_DEFAULT_MAX_AGE_DAYS: int = 14
