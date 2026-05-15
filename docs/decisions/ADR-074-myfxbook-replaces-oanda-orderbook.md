# ADR-074: MyFXBook Community Outlook replaces discontinued OANDA orderbook

- **Status**: Accepted (LIVE since 2026-05-09 — W77b session_id raw URL concat fix landed, MyFXBook collector ingesting 6 pair snapshots / 4h on Hetzner per CLAUDE.md "Recently fixed" §W77b. The earlier "dormant pending Eliot signup" status was stale post-W77b ; r50 hygiene corrects.)
- **Date**: 2026-05-09 (initial decision) / 2026-05-15 (status correction r50)
- **Deciders**: Eliot
- **Related**: ADR-009 (Voie D), ADR-017 (research-only)

## Context

W77 audit (2026-05-09) discovered that OANDA's v20 endpoints
`/v3/instruments/{instrument}/orderBook` and `/positionBook` were
**discontinued in September 2024**. OANDA's replacement product is a
"Data Service" priced at **$1,850/month on a 12-month contract**
(~$22 k/year) — incompatible with Voie D (ADR-009 — Max 20x flat,
no metered third-party billing).

The project's W77 line item ("OANDA orderbook collector") relied on
this defunct endpoint. Two paths forward:

1. Drop retail FX positioning from Ichor entirely.
2. Pivot to an alternative free-tier source.

The retail positioning surface is a useful contrarian sentiment
indicator (extreme >75 % long/short positioning on retail brokers
often precedes a turn). Dropping it would close the contrarian
sentiment leg of Ichor's data architecture. So pivot.

W77 audit identified **MyFXBook Community Outlook** as the canonical
free-tier alternative:

- API endpoint: `/api/get-community-outlook.json?session=<id>`
- Auth: email + password → session token (1 month, IP-bound)
- Rate limit: 100 req/24h (login + outlook = 2 calls per fetch →
  cadence of every 4 hours = 12 calls/day, well under the cap)
- Pairs covered: 40+ including all 6 Ichor pairs (EURUSD, GBPUSD,
  USDJPY, AUDUSD, USDCAD, XAUUSD)
- License: "any software developed using the API should be free" →
  research-internal use OK with attribution
- Bias: sample = MyFXBook-linked traders (self-selected). Documented
  inline in the data_pool surfacing.

## Decision

Ship a new collector `apps/api/src/ichor_api/collectors/myfxbook_outlook.py`
that:

1. Reads `ICHOR_API_MYFXBOOK_EMAIL` + `ICHOR_API_MYFXBOOK_PASSWORD`
   from env. **Returns `[]` silently** if either is missing — graceful
   dormant mode.
2. Logs in via GET `/api/login.json?email=&password=` → session token.
3. Fetches `/api/get-community-outlook.json?session=<id>`.
4. Filters for the 6 Ichor pairs.
5. Persists one row per pair per fetch (no dedup, historical view).

Migration `0037_myfxbook_outlooks.py`. TimescaleDB hypertable on
`fetched_at`, 30-day chunks (high cadence). Composite PK
`(id, fetched_at)`.

systemd timer `ichor-collector-myfxbook_outlook.timer` polling every
4 hours (`00,04,08,12,16,20:00 Europe/Paris`) — 6 fetches/day × 2
calls = 12 calls vs 100 limit.

`data_pool.py` adds `_section_myfxbook_outlook(session)` after the
NFIB SBET section. Surfaces:

- Latest snapshot per pair (long_pct + short_pct)
- Contrarian flag `⚠ retail-long-extreme` when `long_pct ≥ 75` (and
  symmetric short).
- Empty (no sources, caller skips append) when collector dormant.

**DORMANT BY DEFAULT**: until Eliot creates a free MyFXBook account
and sets the two env vars, the collector logs
`myfxbook.dormant reason='ICHOR_API_MYFXBOOK_EMAIL/PASSWORD unset'`
and returns 0. Service exit-clean, no failed timer, no spam.

## Consequences

### Positive

- **Retail positioning surface preserved** despite OANDA discontinuation.
- **Voie D-compliant** (ADR-009): free tier, no metered billing.
- **Verified live 2026-05-09 14:15 CEST** in dormant mode: service
  exit 0, log line confirms graceful skip, timer next trigger 16:00
  CEST. No noise on the failed-services dashboard.
- **Schema is forward-compatible**: persists volume + position-count
  - avg-entry-price fields that MyFXBook returns but Ichor doesn't
    surface yet. Future enhancements (e.g. compute "weighted average
    pain price") can read columns that already exist.
- **Contrarian flag is conservative** (75 % threshold matches
  industry convention). Pass 2 mechanism citation grounded in
  observable retail extreme rather than speculation.

### Negative

- **Self-selection bias** in the sample. MyFXBook-linked traders
  skew toward more sophisticated retail vs the OANDA total
  population. Documented in the `_section_myfxbook_outlook` lead
  paragraph + collector docstring.
- **Login per fetch** is wasteful (could cache the session token
  for ~1 month). Acceptable for v1 — 12 logins/day is well under
  the rate limit. Future enhancement: cache to
  `/var/lib/ichor/myfxbook_session.txt` with 7-day TTL.
- **Dormant by design** — Eliot must signup at myfxbook.com (free)
  and add credentials to `/etc/ichor/api.env`. Documented in the
  ADR + collector docstring + RUNBOOK pending.

## Alternatives considered

- **OANDA Data Service** ($1850/mo) — rejected, violates ADR-009.
- **FXSSI multi-broker aggregator** — no public API, scrape-only,
  more fragile than MyFXBook. Reserve as fallback.
- **Saxo Bank FX Open Orders** — only 10 pairs, ergonomic limits.
- **Drop retail positioning entirely** — rejected, leaves a
  contrarian-sentiment gap.

## Activation checklist (for Eliot)

1. Visit https://www.myfxbook.com/community/outlook — free signup.
2. Confirm email, log in.
3. SSH `ichor-hetzner` and edit `/etc/ichor/api.env`:
   ```
   ICHOR_API_MYFXBOOK_EMAIL=<your-email>
   ICHOR_API_MYFXBOOK_PASSWORD=<your-password>
   ```
4. `sudo systemctl restart ichor-api ; sudo systemctl start ichor-collector@myfxbook_outlook.service`
5. Verify: `sudo journalctl -u ichor-collector@myfxbook_outlook.service -n 20`

Expected: 6 rows persisted (one per Ichor pair) per fetch.

## References

- `apps/api/src/ichor_api/collectors/myfxbook_outlook.py` — collector
- `apps/api/src/ichor_api/models/myfxbook_outlook.py` — model
- `apps/api/migrations/versions/0037_myfxbook_outlooks.py` — migration
- `apps/api/src/ichor_api/services/data_pool.py:_section_myfxbook_outlook`
- `scripts/hetzner/register-cron-collectors-extended.sh:myfxbook_outlook`
- MyFXBook API docs: https://www.myfxbook.com/api
- Dekalog Sept 2024 — OANDA discontinuation:
  https://dekalogblog.blogspot.com/2024/09/discontinuation-of-oandas-orderbook-and.html
- ADR-009 (Voie D), ADR-017 (research-only)
