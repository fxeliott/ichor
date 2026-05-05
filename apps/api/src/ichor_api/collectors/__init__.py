"""Data collectors — pull external feeds into Ichor's Postgres + Redis Streams.

All collectors are async + idempotent. They run as systemd services on Hetzner
(timers registered via scripts/hetzner/register-cron-collectors*.sh).

Implemented (Phase 1) — register-cron-collectors.sh:
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

Implemented (Phase 2) — register-cron-collectors-extended.sh:
  flashalpha               FlashAlpha free GEX (5 req/day, 13h+21h Paris)
  vix_live                 CBOE VIX/VVIX/VIX9D real-time (5min cadence in market hrs)
  aaii                     AAII sentiment survey weekly (Thu 22:30 UTC)
  bls                      BLS v2 (NFP, CPI components) — daily 5h Paris
  ecb_sdmx                 ECB SDMX (HICP, M3) — daily 5:30 Paris
  dts_treasury             Treasury Fiscal Data DTS (daily TGA cash) — every 4h
  boe_iadb                 BoE IADB (UK monetary stats) — daily 5:15 Paris
  eia_petroleum            EIA v2 (weekly petroleum stocks) — daily 18h Paris
  finra_short              FINRA short interest — Mon-Fri 23:30 UTC
  bluesky                  Bluesky firehose (sentiment) — every 30min
  yfinance_options         yfinance options chain (XAU/SPX) — 14h+21:30 Paris

Implemented (Phase 2 sweep, parser-only — pending dedicated tables):
  forex_factory  FairEconomy/ForexFactory weekly XML calendar (NFP, CPI,
                 FOMC, ECB, ...) with consensus + previous
  mastodon       Mastodon ATOM feeds (decentralized social signal —
                 per-user + per-tag) ; will stream into news_items with
                 source_kind="social" once persistence wiring lands

Planned (future phases):
  reddit_wsb     Reddit OAuth (r/wallstreetbets, r/forex, r/Gold)
  pytrends       Google Trends (sentiment proxy on macro keywords)
  finra_ats      FINRA ATS weekly (dark pool prints)
  oanda_ws       OANDA streaming WebSocket (ticks 24/5)
  polymarket_ws  Polymarket WS subscription (live odds shifts)
  fomc_pdf       FOMC press conference PDF scraper (post-meeting NLP)

The `__all__` below intentionally re-exports only `fred` symbols for
backwards compatibility with import sites that did
`from ichor_api.collectors import poll_all`. Each collector is otherwise
imported via its submodule path: `from ichor_api.collectors.bls import ...`.
"""

from .fred import SERIES_TO_POLL, FredObservation, fetch_latest, poll_all

__all__ = ["SERIES_TO_POLL", "FredObservation", "fetch_latest", "poll_all"]
