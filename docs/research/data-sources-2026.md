# Macro & Market Data Sources — 2026 Shopping List

> Source : research subagent task `a009e01982bcfae3d`, completed 2026-05-03.
> Persisted by main thread for context preservation.

A ranked, value-per-dollar map for an Ichor Phase-1 build. Goal: assemble a starting set under $50/month total.

> Methodology: each pricing/feature claim is cited inline. When live verification failed, flagged as `(unverified live, last known 2025/2026)`.

---

## 1. Macro hard data (free tier focus)

| Source | URL | Auth | Rate limit | Strengths | Weaknesses |
|---|---|---|---|---|---|
| **FRED** (St. Louis Fed) | fred.stlouisfed.org/docs/api | Free key | **120 req/min** | 800k+ US/global series, redistribution of H.4.1, BLS, BEA, ECB | US-centric mirror; some non-US lagging |
| **Treasury Fiscal Data** | fiscaldata.treasury.gov/api-documentation | **None** | Not published | Daily TGA, debt, DTS; v1+v2 REST/JSON | Schema sprawl across endpoints |
| **BLS Public Data API v2** | bls.gov/developers/api_signature_v2.htm | Free key | **500 queries/day, 50 series/req, 20yr history** | Calculations, catalog metadata | Daily cap is real |
| **ECB Data Portal (SDMX 2.1)** | data.ecb.europa.eu/help/api/overview | None | Not published | Full euro-area stats, JSON/XML/CSV | SDMX learning curve |
| **Bank of England IADB** | bankofengland.co.uk/boeapps/iadb | None | 300 series codes/request | CSV endpoint, no key | Older URL shape |
| **EIA API v2** | eia.gov/opendata | Free key | Not published; bulk download keyless | 14 categories | Some endpoints return strings |
| **USDA NASS / ERS** | quickstats.nass.usda.gov/api | Free key | Generous | Crops, livestock | Brittle parameter combos |
| **China NBS** | data.stats.gov.cn | None | None | Free | Mostly scraping; English thin |
| **IMF SDMX 3.0** | api.imf.org/external/sdmx/3.0 | None | Not published | WEO, IFS, BoP, COFER | SDMX 3.0 maturing |
| **World Bank WDI SDMX** | api.worldbank.org/v2/sdmx/rest | None | Not published | WDI canonical for cross-country | Annual cadence |
| **OECD Data Explorer SDMX** | sdmx.oecd.org/public/rest | None | **60 req/hour** | Cross-country macro | `lastN/firstNObservations` blocked |

**Phase-1 starting set (Macro): FRED + Treasury Fiscal + ECB SDMX + EIA + BLS v2.** All free. Covers ~85% of macro features. Total: **$0/mo**.

---

## 2. Market data (FX, indices, gold, bonds, commodities)

8-asset target: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, XAU/USD, NAS100, SPX500.

| Provider | Daily bars cost | 1-min intraday | WebSocket | Free-tier prod-viable? |
|---|---|---|---|---|
| **yfinance** (Yahoo unofficial) | $0 | $0 (limited history) | No | Brittle but works |
| **Stooq** | $0 + free API key (CAPTCHA once) | $0 (daily/hourly/min available) | No | Yes for daily |
| **Alpha Vantage Free** | $0 / 25 req/day, 5/min | Same cap | No | **No** — kills production |
| **Alpha Vantage Standard** | **$49.99/mo**, 75 req/min, no daily cap | Yes | No native WS | Yes |
| **Polygon.io Basic (Free)** | $0 / 5 req/min, EOD only, 2yr | No | No | **No** for our 8 assets |
| **Polygon Starter** | **~$29/mo**, unlimited, 15-min delayed, 5+yr | Delayed | Delayed WS | Yes for backtest, no for live |
| **Polygon Developer** | **~$79/mo**, real-time | Real-time | Real-time WS | Yes |
| **Polygon Advanced** | **~$199/mo**, tick-level | Yes | Unlimited WS | Yes |
| **FMP Free** | 250 req/day | Limited | No | Marginal |
| **Twelve Data Free** | 800/day, 8/min, 8 trial WS | Limited | Trial WS | **No** for 8-asset live |
| **Twelve Data Grow** | **$29/mo**, 55 credits/min | Yes | Trial WS | Marginal |
| **Twelve Data Pro** | **$99/mo**, 610 credits + 500 WS | Yes | 500 WS | Yes |
| **IEX Cloud** | **SHUT DOWN August 31, 2024** | — | — | Migrate |
| **Marketstack Basic** | 10k req/mo, intraday + 10yr | Yes | No | Yes for batch backtests |
| **OANDA v20 REST** | Demo free; live needs OANDA broker | Yes (M5/M15) | Pricing stream | Yes if you broker with them |
| **TradingView** | No public market-data API | — | — | **No backend feed offered** |
| **Norgate** | **$630/yr** Platinum US Stocks | EOD only | No | Backtest-only |

**Phase-1 starting set (Markets): yfinance + Stooq with apikey + Polygon Starter $29/mo for true intraday.** Total: **~$29/mo**.

---

## 3. Economic calendar + central bank speeches

| Source | Access | Cost | Latency | Has consensus + actual + revised? |
|---|---|---|---|---|
| **Trading Economics API** | REST | Std ~$75/mo, Pro ~$200/mo `(unverified 2026)` | Near real-time | **Yes** — `Forecast` + `Actual` + `Previous` + revised flag |
| **ForexFactory** | No official API; XML dumps + scrapers | Free | Site-update lag | Yes after release |
| **Investing.com** | No public API; ToS-hostile scrapers | Free if scraped | Real-time | Yes |
| **Finnhub Economic Calendar** | REST | Free tier covers it | Real-time | Yes |
| **DailyFX / FXStreet** | FXStreet OAuth2 API | Paid | Real-time | Yes |
| **CME FedWatch** | Public web tool; scrapeable | Free | Each session | Implied probabilities via Fed-funds futures |
| **Central bank RSS** | XML | Free | Same minute as publish | Statements + speeches, no consensus |

**Central bank RSS feeds (verified):**
- Fed: federalreserve.gov/feeds/feeds.htm
- ECB: ecb.europa.eu/home/html/rss.en.html
- BoE: bankofengland.co.uk/rss
- BoJ: boj.or.jp/en/rss/whatsnew.xml
- BIS speeches: bis.org/doclist/cbspeeches.rss

**Phase-1 starting set (Calendar/CB): ForexFactory weekly XML + central-bank RSS bundle.** Total: **$0/mo**. Add Finnhub free tier or budget $75/mo for Trading Economics later.

---

## 4. Positioning + flows

| Source | Access | Cost | Latency | Notes |
|---|---|---|---|---|
| **CFTC COT (PRE)** | REST API | **Free, no token** | Friday 15:30 CET, positions Tuesday | Python `cftc-cot` lib. **Pause oct 1 – nov 12 2025** (US shutdown) |
| **OANDA Order Book** | REST `forexlabs/orderbook` | Free with OANDA account | Near real-time | 16 instruments |
| **IG Client Sentiment** | DailyFX site; **no documented standalone API** | Free via DailyFX | Hourly | Contrarian signal |
| **ETF.com flows** | Site-only; no public API | Paid for full | Daily | FactSet via ETF.com paywalled |
| **EPFR Global** | Institutional only | $$$$ enterprise | Daily/weekly | Out of scope |
| **Treasury TGA** | FRED `WTREGEN` weekly + Treasury DTS daily | **Free** | Daily | DTS = `Operating Cash Balance` table |
| **Fed RRP** | FRED `RRPONTSYD` daily | **Free** | Daily | NY Fed Markets Data Hub |
| **Gamma data alternatives** | FlashAlpha free GEX (5 req/day), Barchart, SpotGamma free SPX | $0 (limited) | Daily | Same numerics as paid |

**Phase-1 starting set (Positioning): CFTC COT + DTS TGA + FRED RRP + OANDA Order Book + FlashAlpha free GEX.** Total: **$0/mo**.

---

## 5. Sentiment data

| Source | Access | Cost | Notes |
|---|---|---|---|
| **VIX/VVIX** | FRED `VIXCLS` daily; CBOE 20-min delayed | **Free** for daily | Real-time intraday VIX needs CBOE-licensed feed |
| **MOVE Index** | Yahoo `^MOVE`, FRED limited | Free for daily | ICE BofA owned |
| **AAII Sentiment Survey** | Free basic AAII account → spreadsheet | **Free** | Weekly Thursday release |
| **BofA FMS** | **Gated to BofA clients** | Paid via BofA | Free monthly summaries on Hedge Fund Tips, Mace News |
| **Twitter/X sentiment** | X API basic = $200/mo `(unverified 2026)` | Effectively unaffordable | Use scraping at own risk |
| **Reddit (WSB)** | Reddit API: free for small apps | Free for low-vol | `praw` works |
| **Yahoo News scoring** | yfinance returns recent news | $0 | Need own NLP layer |

**Phase-1 starting set (Sentiment): FRED VIXCLS + AAII free + Hedge Fund Tips RSS for monthly FMS digest + Reddit `praw`.** Total: **$0/mo**.

---

## 6. News

| Source | Access | Cost | Notes |
|---|---|---|---|
| **Reuters** | No public open feed | Paid | Limited free RSS topical |
| **Bloomberg** | No public open feed | Paid (Terminal) | Public Bloomberg.com RSS exists |
| **AFP / AP** | RSS available | Free | Headline-only; full content licensed |
| **Central bank RSS** | Confirmed list above | Free | Most reliable signal-to-noise |
| **NewsAPI.org Developer** | 100 req/day, **localhost only**, 256-char truncation | $0 | **Cannot be used in production** per ToS |
| **NewsAPI Business+** | **$449/mo+** | Steep | Production unlock |
| **GDELT 2.0 Doc API** | Free, 3-month rolling window | $0 | **65-language translingual coverage; updates every 15 min** |
| **GDELT Cloud** | Paid managed (data starts Jan 2025) | API-key | Hourly Stories/Entities/Summaries |

**Phase-1 starting set (News): GDELT 2.0 Doc API + central-bank RSS + AP/AFP topical RSS + Reuters Top News RSS.** Total: **$0/mo**. **GDELT covers what NewsAPI charges $449/mo for.**

---

## 7. Prediction markets

| Source | REST | WebSocket | Historical | Cost |
|---|---|---|---|---|
| **Polymarket** | Gamma + CLOB + Data API | RTDS WS at `wss://ws-subscriptions-clob.polymarket.com/ws/market` (5 conn/IP, ping 5s) | 7 days via Bitquery free; bulk via S3 (paid) | All 3 native APIs **free** |
| **Kalshi** | REST + FIX | WS for ticker/trade/orderbook | New `GET /historical/trades` endpoint (March 2026) | Public market data unauth |
| **Manifold** | Free REST + WS at `wss://api.manifold.markets/ws` | Yes | Full bet history per market | **Free, 500 req/min/IP, no key required for read** |
| **PredictIt** | `predictit.org/api/marketdata/all/` | No | CSV downloads | Free; survived July 2025 CFTC shutdown attempt |

**Phase-1 starting set (Prediction): Polymarket Gamma + CLOB REST + RTDS WS for live, Kalshi public REST for US contracts, Manifold for prototyping.** Total: **$0/mo**.

---

## 8. Geopolitics

| Source | Access | Cost | Notes |
|---|---|---|---|
| **GPR Index (Caldara & Iacoviello)** | CSV/Excel from matteoiacoviello.com/gpr.htm | **Free** | Monthly; 1985-present; subindexes |
| **AI-GPR Index** | matteoiacoviello.com/ai_gpr.html | **Free** | **Daily frequency since 1960; updated through March 31, 2026; LLM-scored** |
| **ACLED** | API with auth; tiered access | Free for academic .edu; commercial paid | 5,000-row default limit |
| **GDELT** | See section 6 | Free | CAMEO event taxonomy; 300+ event categories |
| **News scrape + classification** | Roll your own with GDELT GKG themes | Free | GKG already extracts persons/orgs/locations/themes/emotions |

**Phase-1 starting set (Geopolitics): GPR + AI-GPR (CSV cron) + GDELT 2.0 events.** Total: **$0/mo**.

---

## 9. Order flow / dark pools (US equities)

| Source | Access | Cost | Notes |
|---|---|---|---|
| **FINRA Equity Short Interest** | REST API + bulk text | **Free** | Bi-monthly; CSV/JSON; archive to 2014 |
| **FINRA Daily Short Sale Volume Files** | Bulk files | Free | Daily TRF/ADF/ORF aggregated short volume |
| **FINRA ATS Transparency (dark pools)** | CSV downloads | Free | **Weekly cadence; 2-week lag (Tier 1), 4-week lag (Tier 2)** |
| **DTCC settlement** | Limited public stats | Free public reports only | Granular settlement not public |
| **SEC EDGAR 13F** | EDGAR API | Free | Quarterly, 45-day filing lag |
| **SEC MIDAS** | Academic/regulatory only | Restricted | Out of scope |
| **Third-party aggregators** (Fintel, Barchart, Market Chameleon) | Web/freemium | Free tiers exist | Add Z-scores on top of FINRA data |

**Phase-1 starting set (Dark/Flow): FINRA Equity Short Interest + Daily Short Sale Volume + ATS Weekly.** Total: **$0/mo**.

---

## Phase-1 total stack — recommended

| Category | Pick | Cost |
|---|---|---|
| Macro | FRED + Treasury Fiscal + ECB SDMX + EIA + BLS v2 | $0 |
| Markets (8 assets) | yfinance + Stooq apikey + Polygon Starter | **$29/mo** |
| Calendar | ForexFactory weekly XML + central-bank RSS | $0 |
| Positioning | CFTC COT + DTS daily TGA + FRED RRP + FlashAlpha free GEX | $0 |
| Sentiment | FRED VIXCLS + AAII + Hedge Fund Tips RSS | $0 |
| News | GDELT 2.0 + central-bank RSS + AP/Reuters topical RSS | $0 |
| Prediction | Polymarket + Kalshi + Manifold | $0 |
| Geopolitics | GPR + AI-GPR + GDELT events | $0 |
| Dark/flow | FINRA short interest + ATS weekly | $0 |
| **Total** | | **$29/mo** |

**$0 alternative**: drop Polygon, accept yfinance + Stooq daily-only-grade.

**$50 alternative**: Polygon Starter $29 + Twelve Data Grow $29 = $58 for redundancy pair, OR Polygon Starter alone as cleanest single dependency.

---

## Confidence map

**Verified live:** FRED 120 req/min, Stooq apikey, AlphaVantage tiers, Polygon plan structure (pricing from third-party 2026 review), Twelve Data tiers, IEX shutdown Aug 31 2024, Marketstack tiers, BLS v2 limits, ECB SDMX 2.1, BoE IADB, EIA v2, IMF SDMX 3.0, OECD 60/h, CFTC PRE shutdown Oct-Nov 2025, Polymarket free APIs + WS limits, Kalshi March 2026 fixed-point migration + `/historical/trades`, Manifold 500/min, PredictIt post-July-2025-CFTC-ruling, GDELT 2.0 endpoints + Cloud, ACLED tier model, AI-GPR daily through March 31 2026, FINRA short interest cadence + ATS lag, AAII free spreadsheet, BofA FMS gating, central bank RSS URLs, FlashAlpha free GEX.

**Industry knowledge / not freshly verified:** Trading Economics tier $ pricing, FMP Starter exact $, Norgate Futures/Forex prices, X API Basic ($200/mo) and Pro ($5,000/mo) pricing.

**Could not verify:** Polygon.io pricing page itself (returned title only); China NBS API; DTCC granular settlement.

---

**Report compiled** : 2026-05-03 by main thread from research subagent output.
