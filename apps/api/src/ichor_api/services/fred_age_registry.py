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
    # ─── IMF World Bank PinkBook composite monthly series (round-46 ADR-092) ───
    # 60d max-age acceptable because IMF PinkBook publishes early-month
    # (vs OECD MEI mid-month with 1-month publication lag → OECD entries
    # need 120d). r46 ship validates empirically post-deploy ; if FRED
    # silent-skip emerges (60-65d delay scenarios), bump to 90d or 120d
    # in a follow-up hygiene round (code-reviewer M2 review caveat).
    "MYAGM1CNM189N": 60,  # China M1 monthly (round-46 r46-round-2 audit swap from
    #                       MYAGM2CNM189N which was DISCONTINUED Aug 2019 per IMF
    #                       IFS / FRED) ; credit-impulse proxy preserved per
    #                       Barcelona et al. 2022 Fed IFDP 1360 ; TSF direct
    #                       deferred per ADR-092 §DEFER firmly
    "PIORECRUSDM": 60,  # Global Iron Ore Price Index monthly (round-46 ADR-092 §T1.AUD-2)
    "PCOPPUSDM": 60,  # Global Copper Price Index monthly (round-46 ADR-092 §T1.AUD-2)
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
