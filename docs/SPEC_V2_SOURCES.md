# SPEC v2 — Sources data free tier / public 2026

**Date** : 2026-05-04
**Compagnon de** : `D:\Ichor\SPEC.md` (Phase 2 Ichor)
**Source** : recherche READ-ONLY web 2026 (60+ sources sourcées avec URL, quota, format vérifiés)
**Budget Eliot** : strict — Claude Max 20x $200 + Massive Currencies $49 ; reste exclusivement free tier ou public data.

## 1. Tableau exhaustif (60 sources)

Pertinence Ichor (forex / indices US / gold, sessions Londres/NY) notée 1-5. Effort F(faible) / M(moyen) / E(élevé). Risque idem.

| #   | Catégorie             | Source                                           | URL                                                | Quota                                                                               | Format               | Pertinence | Effort | Risque                  |
| --- | --------------------- | ------------------------------------------------ | -------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------- | ---------- | ------ | ----------------------- |
| 1   | Regulatory US         | SEC EDGAR Submissions/XBRL                       | data.sec.gov                                       | Pas de clé, fair-use UA, bulk ZIP nightly 03:00 ET                                  | JSON / ZIP           | 3          | F      | F                       |
| 2   | Regulatory US         | SEC DERA Financial Data                          | sec.gov/dera                                       | Bulk trim/mensuel                                                                   | CSV/TSV              | 3          | M      | F                       |
| 3   | Regulatory US         | FFIEC CDR Bulk                                   | cdr.ffiec.gov                                      | Public bulk                                                                         | TSV/XBRL             | 2          | M      | F                       |
| 4   | Regulatory US         | FFIEC REST API                                   | ffiec.gov                                          | OAuth2, 2500 req/h                                                                  | JSON                 | 2          | M      | M (token 90j)           |
| 5   | Regulatory US         | FDIC BankFind                                    | banks.data.fdic.gov                                | Pas de clé                                                                          | JSON REST            | 2          | F      | F                       |
| 6   | Regulatory US         | HMDA / CFPB                                      | ffiec.cfpb.gov/v2/public/                          | Public                                                                              | JSON                 | 1          | F      | F                       |
| 7   | Regulatory US         | FINRA Equity Short Interest                      | api.finra.org                                      | Compte free non-commercial                                                          | JSON/CSV             | 4          | M      | M                       |
| 8   | Regulatory US         | FINRA ATS / OTC Weekly                           | api.finra.org                                      | Free dev account                                                                    | JSON/CSV             | 3          | M      | M                       |
| 9   | Regulatory US         | FINRA Daily Short Sale                           | api.finra.org/.../regShoDaily                      | Free dev                                                                            | JSON/CSV             | 4          | M      | M                       |
| 10  | Regulatory US         | CFTC COT (Socrata API)                           | publicreporting.cftc.gov                           | Public Socrata                                                                      | JSON/CSV             | 5          | F      | F                       |
| 11  | Regulatory US         | CFTC SDR Swap Snapshots                          | cftc.gov/data                                      | Public bulk hebdo                                                                   | CSV                  | 2          | M      | F                       |
| 12  | Stats internationales | OECD SDMX REST v2                                | sdmx.oecd.org/public/rest                          | Pas de clé, max 1M obs/réponse                                                      | JSON/XML/CSV         | 4          | M      | F                       |
| 13  | Stats internationales | World Bank Indicators                            | api.worldbank.org/v2                               | Public                                                                              | JSON                 | 3          | F      | F                       |
| 14  | Stats internationales | IMF SDMX / DataMapper                            | data.imf.org                                       | Public                                                                              | JSON SDMX            | 3          | M      | F                       |
| 15  | Stats internationales | BIS Stats SDMX                                   | stats.bis.org/api/v1                               | Public                                                                              | SDMX                 | 4          | M      | F                       |
| 16  | Stats internationales | Eurostat SDMX 3.0                                | ec.europa.eu/eurostat/api                          | Public, libre re-use                                                                | SDMX-CSV / JSON-stat | 3          | M      | F                       |
| 17  | Stats internationales | DBnomics (agrégateur)                            | db.nomics.world                                    | Public                                                                              | JSON/Parquet         | 4          | F      | F                       |
| 18  | CB Europe             | ECB Data Portal SDMX 2.1                         | data.ecb.europa.eu                                 | Public                                                                              | SDMX                 | 5          | M      | F                       |
| 19  | CB UK                 | BoE IADB                                         | bankofengland.co.uk/boeapps/iadb                   | Public CSV via URL params                                                           | CSV                  | 5          | F      | F                       |
| 20  | CB Suisse             | SNB Data Portal                                  | data.snb.ch                                        | Public                                                                              | JSON/CSV             | 3          | F      | F                       |
| 21  | CB Allemagne          | Bundesbank SDMX                                  | api.statistiken.bundesbank.de                      | Public                                                                              | SDMX                 | 3          | M      | F                       |
| 22  | CB Japon              | BoJ Time-Series Search                           | boj.or.jp/en/statistics                            | Web/CSV download                                                                    | CSV/Excel            | 3          | E      | M (scrape)              |
| 23  | CB Inde               | RBI DBIE                                         | dbie.rbi.org.in                                    | Web/Excel                                                                           | XLS/CSV              | 1          | E      | M                       |
| 24  | CB Australie          | RBA Statistical Tables                           | rba.gov.au/statistics                              | CSV publiées                                                                        | CSV                  | 2          | F      | F                       |
| 25  | Energie               | EIA OpenData v2 (clé free)                       | api.eia.gov/v2                                     | Free key                                                                            | JSON                 | 5          | F      | F                       |
| 26  | Energie               | EIA Bulk (5h+15h ET)                             | eia.gov/opendata                                   | Public bulk                                                                         | ZIP/JSON             | 4          | F      | F                       |
| 27  | Options               | Tradier Sandbox                                  | api.tradier.com / sandbox                          | Free account ; real-time gated brokerage                                            | JSON REST            | 3          | F      | M                       |
| 28  | Options               | CBOE delayed (via OpenBB)                        | cboe.com                                           | Délayé, pas de clé                                                                  | JSON                 | 3          | F      | F                       |
| 29  | Crypto on-chain       | DeFiLlama                                        | api-docs.defillama.com                             | Pas d'auth                                                                          | JSON                 | 4          | F      | F                       |
| 30  | Crypto on-chain       | Etherscan                                        | etherscan.io/apis                                  | Free key, 5 req/s                                                                   | JSON                 | 2          | F      | F                       |
| 31  | Crypto on-chain       | Bitquery Dev Free                                | bitquery.io                                        | 1000 trial points, 10 req/min                                                       | GraphQL              | 2          | E      | M (points opaques)      |
| 32  | Crypto on-chain       | Dune Analytics                                   | dune.com                                           | Free dashboards/community SQL ; API payant                                          | SQL/CSV              | 2          | M      | M                       |
| 33  | Crypto on-chain       | Glassnode free                                   | docs.glassnode.com                                 | Très limité, gated Pro                                                              | JSON                 | 2          | F      | E                       |
| 34  | Crypto sentiment      | Crypto Fear & Greed                              | api.alternative.me/fng                             | Public                                                                              | JSON/CSV             | 3          | F      | F                       |
| 35  | Crypto sentiment      | Binance fundingRate USDⓈ-M                       | fapi.binance.com/fapi/v1/fundingRate               | Public, 500/5min/IP                                                                 | JSON                 | 4          | F      | F                       |
| 36  | Crypto sentiment      | Binance fundingRate COIN-M                       | dapi.binance.com/dapi/v1/fundingRate               | Public IP-limit                                                                     | JSON                 | 3          | F      | F                       |
| 37  | Crypto sentiment      | OKX funding-rate-history                         | okx.com/api/v5/public/funding-rate-history         | Public IP-limit                                                                     | JSON                 | 3          | F      | F                       |
| 38  | Sentiment social      | Reddit PRAW (OAuth)                              | praw.readthedocs.io                                | 100 req/min, 1000-post listing cap                                                  | JSON                 | 2          | M      | E (commercial $0.24/1k) |
| 39  | Sentiment social      | Bluesky AT Protocol                              | bsky.social                                        | Public, ouvert                                                                      | JSON                 | 2          | M      | F                       |
| 40  | Sentiment social      | Mastodon (instances)                             | docs.joinmastodon.org                              | Public, par instance                                                                | JSON                 | 1          | M      | F                       |
| 41  | Sentiment social      | X/Twitter pay-per-use                            | developer.x.com                                    | Plus de free tier nouveau dev (févr 2026), ~$0.005/lecture                          | JSON                 | 1          | M      | E                       |
| 42  | Search/attention      | Google Trends pytrends                           | pypi.org/project/pytrends                          | Non officiel, 429 fréquents                                                         | DataFrame            | 3          | M      | M                       |
| 43  | Search/attention      | Wikipedia Pageviews REST                         | wikimedia.org/api/rest_v1/metrics/pageviews        | Public, UA requis                                                                   | JSON                 | 3          | F      | F                       |
| 44  | Search/attention      | Wikimedia Pageview dumps                         | dumps.wikimedia.org/other/pageviews                | Bulk public                                                                         | TSV gzip             | 2          | M      | F                       |
| 45  | Open-source platform  | OpenBB Platform                                  | docs.openbb.co                                     | AGPL, multi-providers (cboe/fred/ecb/finra/eia/imf/fama-french/multpl/wsj/yfinance) | Python + REST        | 5          | F      | F                       |
| 46  | Open-source platform  | Microsoft qlib + qlib-server                     | github.com/microsoft/qlib                          | MIT, scripts CN/US/TW                                                               | Python               | 3          | M      | F                       |
| 47  | Open-source platform  | wilsonfreitas/awesome-quant                      | github.com/wilsonfreitas/awesome-quant             | Repo curaté                                                                         | —                    | 4          | F      | F                       |
| 48  | Tick data             | Dukascopy Historical Export                      | dukascopy.com/swiss/english/marketwatch/historical | Tick free (TOS Dukascopy)                                                           | CSV                  | 5          | M      | M                       |
| 49  | Tick data             | dukascopy-node                                   | github.com/Leo4815162342/dukascopy-node            | OSS tool                                                                            | CSV/JSON             | 5          | F      | M                       |
| 50  | Tick data             | Histdata.com FX                                  | histdata.com                                       | Bulk M1/tick                                                                        | CSV/MT4              | 3          | F      | M                       |
| 51  | News                  | RSS Reuters/AP/Bloomberg/Yahoo Finance/Investing | divers feeds                                       | Public RSS                                                                          | XML                  | 3          | F      | M (TOS Investing)       |
| 52  | Academic              | arXiv q-fin RSS                                  | arxiv.org/list/q-fin/new                           | OAI-PMH                                                                             | RSS/XML              | 2          | F      | F                       |
| 53  | Academic              | NBER Working Papers                              | nber.org/papers                                    | 3 papers/an non-affiliés ; >18 mois open                                            | RSS/PDF              | 2          | F      | F                       |
| 54  | Academic              | SSRN FEN                                         | ssrn.com/index.cfm/en/fen                          | Open access preprints                                                               | Web                  | 2          | M      | F                       |
| 55  | Academic              | RePEc / IDEAS                                    | ideas.repec.org                                    | Public RSS                                                                          | RSS/XML              | 2          | F      | F                       |
| 56  | Gov US                | Treasury Fiscal Data DTS                         | api.fiscaldata.treasury.gov                        | Public, pas de clé                                                                  | JSON/CSV/XML         | 5          | F      | F                       |
| 57  | Gov US                | Treasury TIC                                     | home.treasury.gov/.../tic                          | Web public                                                                          | HTML/CSV             | 3          | M      | F                       |
| 58  | Gov Asie              | NBS China English                                | stats.gov.cn/english/                              | Web public                                                                          | HTML/Excel           | 2          | E      | F                       |
| 59  | Gov Asie              | DBnomics NBS                                     | db.nomics.world/NBS                                | Public                                                                              | JSON                 | 3          | F      | F                       |
| 60  | Geopolitical          | GDELT 2.0 DOC + GEO 2.0                          | gdeltproject.org / docs.gdeltcloud.com             | Public, refresh 15 min                                                              | JSON                 | 4          | M      | M                       |
| 61  | Geopolitical          | ACLED myACLED                                    | acleddata.com                                      | Free academic key                                                                   | JSON/CSV             | 2          | F      | M                       |
| 62  | Agricultural          | USDA NASS QuickStats                             | quickstats.nass.usda.gov/api                       | Free key, 50k records max                                                           | JSON/CSV             | 2          | F      | F                       |
| 63  | Agricultural          | USDA WAOB WASDE                                  | usda.gov                                           | Public release                                                                      | PDF/JSON             | 2          | M      | F                       |
| 64  | Shipping              | AISstream.io                                     | aisstream.io                                       | Free WebSocket bbox                                                                 | WS                   | 2          | M      | F                       |
| 65  | Shipping              | AISHub                                           | aishub.net                                         | Free contributif                                                                    | TCP/HTTP             | 1          | E      | M                       |
| 66  | Crypto signal         | CoinGlass                                        | coinglass.com                                      | Web aggregator                                                                      | scrape               | 3          | M      | M                       |

## 2. Top 20 sources prioritaires Phase 2 Ichor

1. **CFTC COT (Socrata)** — positions managed-money/non-commercial gold + EUR/JPY/GBP futures, signal hebdo positionning robuste.
2. **Treasury Fiscal Data DTS** — TGA daily, signal liquidité USD direct sessions NY.
3. **EIA OpenData v2** — pétrole hebdo (Wed 10:30 ET) impact direct USD/CAD, indices via énergie.
4. **BoE IADB** — SONIA, gilts, Bank Rate ; complément GBP sessions Londres.
5. **ECB Data Portal SDMX** — €STR, taux directeurs, BdP ; couverture EUR.
6. **OECD SDMX REST v2** — CLI composite, signaux cycliques avancés.
7. **BIS Stats SDMX** — effective exchange rates, dette globale, position bancaires.
8. **DeFiLlama free** — TVL stablecoins (USDT/USDC supply = proxy liquidité crypto/risk-on).
9. **Binance + OKX funding rates** — stress crypto leverage, corrélation NDX/BTC sessions NY.
10. **Crypto Fear & Greed Index** — sentiment crypto agrégé, signal contrarian.
11. **GDELT 2.0 DOC API** — détection événements géopolitiques 15 min latency, gold catalyst.
12. **Wikipedia Pageviews REST** — proxy attention valeurs (Apple, Tesla, BTC).
13. **Dukascopy historical tick** — backtests forex tick gratuit, deep history.
14. **OpenBB Platform** — wrapper unifié à embarquer (cboe / multpl / fama-french / wsj en un seul SDK).
15. **FINRA Daily Short Sale Volume** — short selling intraday US tickers.
16. **FRED via OpenBB** — déjà dans Phase 1, à étendre H.8/H.4.1 Fed.
17. **arXiv q-fin RSS** — alpha academic émergent.
18. **DBnomics agrégateur** — fallback unifié BIS/IMF/NBS/OECD.
19. **NASS QuickStats** — WASDE feed pour gold/AG corrélation.
20. **Treasury TIC monthly** — flux capitaux étrangers Treasuries.

## 3. Sources à ÉVITER (audit critique)

- **Glassnode free tier** : officiellement gated derrière Professional. Le "free" anecdotique. Inadapté.
- **Bitquery** : système points opaque, 1000 points trial épuisable en 1 requête mal scopée.
- **Dune Analytics API** : compute SQL payant ; le free limité aux dashboards web manuels.
- **MarineTraffic** : depuis acquisition Kpler, plus de free tier crédit. Préférer **AISstream.io**.
- **Twitter/X API** : free tier supprimé pour nouveaux dev depuis fév 2026. Pay-per-use ~$0.005/lecture peut exploser. **Préférer Bluesky/Mastodon**.
- **ForexFactory / Investing.com scraping** : pas d'API officielle, ToS hostile, zone grise CFAA. **Éviter en commercial**.
- **Reddit PRAW commercial** : $0.24/1000 calls. **OK pour Ichor en R&D** ; à reconsidérer si SaaS public.
- **BoJ / RBI** : pas d'API REST publique, scrape Excel — effort élevé, ROI faible vs ECB/BoE.

## 4. Hedge funds capabilities — comparatif feature

| Fonds                                  | Sources signature publiquement documentées                           | Reproductible free tier                                              | Impossible sans budget                                          |
| -------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------- |
| Bridgewater (Pure Alpha / All Weather) | Macroeconomic data, modèles systémiques globaux ; Daily Observations | Oui partiellement : OECD/BIS/IMF/FRED + qlib factor library          | Données privées négociées avec CB, dataset propriétaire 30+ ans |
| Renaissance (Medallion)                | Aucune (secret total)                                                | Non, pipeline ML + tick data + infra                                 | Tick L2/L3 multi-venue, infra colocalisée                       |
| Citadel                                | HFT, market-making, real-time news NLP                               | Non, l'edge = exécution                                              | Connectivité co-loc, trade-cost modeling                        |
| Two Sigma                              | Alt data : satellite, credit card flows, Fed minutes NLP             | Partiellement : NLP Fed minutes (FOMC PDFs), GDELT, Wikipedia trends | Satellite RS Metrics/Orbital Insight, panels transactions       |
| AQR                                    | Academic factor papers (carry/value/momentum/defensive)              | Reproductible : pandas-datareader Fama/French                        | Le réseau Cliff Asness                                          |

**Conclusion** : Ichor en free tier peut reproduire ~60 % du signal macro Bridgewater (FRED/OECD/BIS + COT + DTS), ~30 % du Two Sigma sentiment layer (GDELT + Reddit + Wikipedia + arXiv), 0 % de l'edge HFT Renaissance/Citadel (et c'est OK : Ichor n'est pas un HFT).

## 5. Architecture de collecte recommandée

### 5.1 Top 10 collectors Phase 2 ROI

1. CFTC COT (hebdo vendredi 15:30 ET)
2. Treasury DTS (daily 16:00 ET)
3. EIA petroleum weekly + daily (mercredi 10:30 ET)
4. ECB SDMX €STR + rates (daily)
5. BoE IADB SONIA + gilts (daily)
6. DeFiLlama stablecoin supply (15 min)
7. Binance + OKX funding rates (1h aggregation)
8. GDELT DOC API thematic queries (15 min)
9. Wikipedia Pageviews per asset (daily)
10. arXiv q-fin RSS (daily)

### 5.2 Cadence recommandée

| Source                       | Cadence                 |
| ---------------------------- | ----------------------- |
| Tick FX backtest (Dukascopy) | One-shot bulk + monthly |
| Funding rates, DeFiLlama TVL | 15 min – 1h             |
| GDELT, RSS news              | 15 min                  |
| EIA, DTS, COT                | quotidien post-release  |
| ECB, BoE, OECD, BIS          | quotidien               |
| arXiv, NBER, SSRN            | quotidien               |
| Wikipedia pageviews          | quotidien               |

### 5.3 Stockage

- **TimescaleDB hypertables** : séries time-series haute cadence (funding rates, DTS, OHLC, FX tick agrégé en 1m).
- **Parquet partitionné par date** (S3-compat local ou cold storage) : bulk historiques (Dukascopy ticks, GDELT events, COT history).
- **Redis** : cache last-value snapshot pour dashboards live + dedup feeds RSS/news (TTL 24-48h).

## 6. Open-source platforms — inspiration

### 6.1 OpenBB

À emprunter directement : modèle d'extension provider par provider (cboe, fred, ecb, eia, finra, fama-french, multpl) — Ichor peut soit consommer OpenBB SDK Python en wrapper, soit copier le pattern d'orchestration provider+normalisation pour ses propres collectors.

### 6.2 Microsoft qlib

Factor library + data_collector scripts pour CN/US/TW. À emprunter : structure binary feature storage (point-in-time DB), pattern de cache Qlib-Server pour shared data services.

### 6.3 awesome-quant

Repo curaté wilsonfreitas — utiliser comme index pour découvrir libs de niche (pandas-datareader Fama/French/World Bank/Eurostat en un wrap, freqtrade, JQuantLib).

## 7. Risques légaux / TOS

- **ForexFactory / Investing.com** : pas d'API officielle, ToS de Fair Economy Inc. (FF) et Fusion Media (Investing) réservent droit de blocage. Zone grise CFAA US ; pas de jurisprudence 2026 spécifique. **Recommandation** : éviter scrape commercial ; pour personal/research, accepter risque mais plan B = FXStreet/Finnhub payants si Ichor monte en volume.
- **Reddit PRAW** : depuis 2023, free OK pour non-commercial, $0.24/1000 calls en commercial, monitoring agressif. **OK pour Ichor en R&D** ; à reconsidérer si SaaS public.
- **Twitter/X free 10k/mo** : **n'existe plus** depuis février 2026 pour nouveaux dev. Pay-per-use uniquement. **Mastodon + Bluesky** = alternatives crédibles, fediverse APIs ouvertes, pas de coût. Volume signal réduit vs X mais OK pour finance niche.

## 8. Recommandations concrètes pour SPEC.md

À ajouter en Phase 2 (collectors prioritaires) :

```
- collector_cftc_cot               # Socrata, weekly Fri
- collector_treasury_dts           # daily 16:00 ET
- collector_eia_petroleum          # daily + weekly Wed
- collector_ecb_sdmx               # daily €STR, rates
- collector_boe_iadb               # daily SONIA, gilts
- collector_oecd_cli               # monthly composite leading indicators
- collector_bis_eer                # weekly effective exchange rates
- collector_defillama_tvl          # 15min stablecoin supply
- collector_binance_funding        # hourly perpetual funding
- collector_okx_funding            # hourly perpetual funding
- collector_fear_greed             # daily crypto sentiment index
- collector_gdelt_doc              # 15min thematic geopolitical events
- collector_wikipedia_pageviews    # daily attention proxy
- collector_finra_short_volume     # daily short sale volume
- collector_arxiv_qfin             # daily RSS academic
- collector_nber_wp                # daily working papers
- collector_dukascopy_bulk         # one-shot historical FX tick (then monthly delta)
- wrapper_openbb_provider          # bridge cboe / multpl / fama-french / wsj
```

À éviter Phase 2 (à reporter ou bypass) :

- Twitter/X collector → remplacer par Bluesky + Mastodon
- Glassnode free tier → trop limité
- Bitquery, Dune → coûts cachés
- ForexFactory scrape → ToS hostile

## Sources principales

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [FFIEC CDR Bulk](https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx)
- [FDIC BankFind Suite](https://banks.data.fdic.gov/)
- [OECD API guide](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)
- [BIS Data Portal](https://data.bis.org)
- [DBnomics](https://db.nomics.world)
- [DeFiLlama API](https://api-docs.defillama.com/)
- [Binance Futures funding](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)
- [OKX API v5](https://www.okx.com/docs-v5/en/)
- [Tradier API](https://docs.tradier.com/)
- [Dukascopy Historical](https://www.dukascopy.com/swiss/english/marketwatch/historical/)
- [dukascopy-node](https://github.com/Leo4815162342/dukascopy-node)
- [OpenBB Data Providers](https://my.openbb.co/app/platform/data-providers)
- [OpenBB Platform GitHub](https://github.com/OpenBB-finance/OpenBB)
- [EIA OpenData v2](https://www.eia.gov/opendata/)
- [Treasury Fiscal Data DTS](https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/)
- [USDA NASS QuickStats](https://quickstats.nass.usda.gov/api)
- [Microsoft qlib](https://github.com/microsoft/qlib)
- [awesome-quant](https://github.com/wilsonfreitas/awesome-quant)
- [CFTC Public Reporting](https://publicreporting.cftc.gov)
- [FINRA API Catalog](https://developer.finra.org/catalog)
- [Crypto Fear & Greed API](https://alternative.me/crypto/api/)
- [arXiv q-fin](https://arxiv.org/list/q-fin/new)
- [ECB Data Portal API](https://data.ecb.europa.eu/help/api/overview)
- [Eurostat API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction)
- [GDELT Project](https://www.gdeltproject.org/)
- [PRAW rate limits](https://praw.readthedocs.io/en/stable/getting_started/ratelimits.html)
- [BoE Database](https://www.bankofengland.co.uk/boeapps/database/)
- [X API pricing 2026](https://www.xpoz.ai/blog/guides/understanding-twitter-api-pricing-tiers-and-alternatives/)
