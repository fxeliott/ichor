"""Data collectors — pull external feeds into Ichor's Postgres + Redis Streams.

All collectors are async + idempotent. They run as systemd services on Hetzner
(timers registered via scripts/hetzner/register-cron-collectors.sh).

Implemented modules (Phase 1 Step 1):
  fred                     FRED REST polling (Net Liquidity, OAS, term structure)
  fred_extended            FRED extended series (DGS3MO, DFII10, T10Y2Y, ...)
  market_data              Stooq + yfinance fallback chain (daily OHLCV)
  rss                      RSS pollers (Reuters, BBC, Fed, ECB, BoE, Treasury, SEC)
  gdelt                    GDELT 2.0 DOC API (geopolitical events, narrative density)
  ai_gpr                   Caldara-Iacoviello AI-GPR daily (geopolitical risk index)
  cot                      CFTC Disaggregated Futures (positioning weekly)
  central_bank_speeches    BIS RSS + Fed/ECB/BoE/BoJ speech feeds
  kalshi                   Kalshi REST (CFTC-regulated event contracts)
  manifold                 Manifold Markets REST (community prediction markets)
  polymarket               Polymarket Gamma REST (decentralized prediction markets)
  polygon                  Polygon.io / Massive v2/aggs (1-min OHLCV, 8 assets)
  polygon_news             Massive /v2/reference/news — ticker-linked news flow
  persistence              Async upsert helpers (DB-backed, dedup-aware)

Planned (Phase 1+):
  bls           BLS v2 (NFP, CPI components, real wages)
  ecb_sdmx      ECB SDMX (HICP, M3, OMT operations)
  eia           EIA v2 (weekly stocks, STEO, AEO)
  boe_iadb      BoE IADB (UK monetary stats, gilt yields)
  treasury_dts  Treasury Fiscal Data DTS (daily Treasury cash, TGA)
  flashalpha    FlashAlpha free GEX (5 req/jour)
  vix_live      Cboe VIX/VVIX/VIX9D real-time
  aaii          AAII sentiment survey weekly
  reddit_wsb    Reddit OAuth (r/wallstreetbets, r/forex, r/Gold)
  finra_si      FINRA short interest twice-monthly
  finra_ats     FINRA ATS weekly (dark pool prints)
  oanda_ws      OANDA streaming WebSocket (ticks 24/5)
  polymarket_ws Polymarket WS subscription (live odds shifts)
  fomc_pdf      FOMC press conference PDF scraper (post-meeting NLP)
  eco_calendar  Forex Factory + ECB + BLS unified calendar
"""

from .fred import FredObservation, SERIES_TO_POLL, fetch_latest, poll_all

__all__ = ["FredObservation", "SERIES_TO_POLL", "fetch_latest", "poll_all"]
