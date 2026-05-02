"""Data collectors — pull external feeds into Ichor's Postgres + Redis Streams.

All collectors are async + idempotent. They run as systemd services on Hetzner
(per role 'collectors' in Ansible — Phase 0 W2 step 11).

Modules:
  fred         FRED REST polling (every 4-6h depending on series)
  oanda        OANDA streaming WebSocket (ticks 24/5)
  polymarket   Polymarket Gamma WS (events + market shifts)
  rss_news     RSS pollers (Reuters, AP, FT, Bloomberg) every 60s
  eia          EIA energy data (weekly + daily inventories)
  fomc_pdf     FOMC press conference PDF scraper (post-meeting)
"""

from .fred import FredObservation, SERIES_TO_POLL, fetch_latest, poll_all

__all__ = ["FredObservation", "SERIES_TO_POLL", "fetch_latest", "poll_all"]
