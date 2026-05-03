# Macro Tools Landscape 2026 — Research Brief for Ichor

> Source : research subagent task `a7ae4fbc930e82ff5`, completed 2026-05-03.
> Persisted by main thread for context preservation.

**Status** : research synthesis, not validated by user interviews
**Author** : Claude (read-only research subagent)

## 1. Competitive landscape

| Tool | 1-line | Target | Price/mo | Strengths | Weaknesses |
|---|---|---|---|---|---|
| **Tier1Alpha** | Dealer gamma + vol-control flow models, distributed via Hedgeye | Sophisticated retail / RIA | Not public; Hedgeye-bundled, est. $300-800/mo | Best-in-class market-structure quant, daily MSR + weekly webcast | US equities only, no FX/macro, opaque pricing |
| **SpotGamma** | Options gamma/HIRO real-time dealer hedging signals | Active US-options day traders | Essential $99 / Alpha $299 | HIRO is the reference for 0DTE/dealer flows, Equity Hub 3,500 names | US equities only, no macro narrative, no FX |
| **Real Vision Pro Macro** | Video + Macro Insiders (Pal/Brigden) institutional notes | Discretionary macro retail | Pricing gated; "Macro Insiders" historically ~$200-400/mo standalone | Top-tier voices, narrative depth, video-first | Async (video), no real-time data, no per-asset bias |
| **Koyfin** | Bloomberg-lite charting + global fundamentals | Buy-side analysts, retail pros | Plus $39 / Premium (ex-Pro) $79 | Cheap, broad coverage, modern UI | No proprietary macro view, no options flow, web-only |
| **42 Macro (Darius Dale)** | KISS portfolio + GRID regime model | Retail + RIAs | Macro Strategist Pro ~$199/qtr promo; daily tiers higher (not public) | Calibrated regime framework, ETF-actionable | US-centric, no FX-pair granularity, no real-time |
| **Bridgewater Daily Observations** | "The wire" — flagship institutional note | Pensions, sovereigns, central banks | Bundled w/ multi-million advisory; no retail tier | Gold-standard analysis | Inaccessible. "Connecting the Dots" is the free abridged version |
| **TradingView Premium/Ultimate** | Charting + community | Discretionary technical traders | Premium $59.95 / Ultimate $199.95 | Ubiquitous charts, alerts, Pine | No proprietary macro, news is shallow |
| **Bloomberg Terminal** | All-in-one institutional data + chat | Sell-side, large buy-side | $31,980/yr (~$2,665/mo), 2-yr lock | Coverage, IB chat, MARS | Price, UX from 1990, info overload not synthesis |
| **FactSet Workstation** | Modular buy-side analytics | Buy-side analysts | $4k–$50k/user/yr | Better analytics/API than BBG, modular | Same overload problem, no narrative |
| **Macro Hive** (Bilal Hafeez) | Quant + discretionary macro research | Retail (Prime) + institutional (Pro) | Prime price not on landing pages; widely cited ~$50-100/mo | Independent, machine-learning trade ideas | Anglo-centric, no real-time interactivity |
| **Jenova "AI Macro Strategist"** (2025-26 entrant) | Cross-asset LLM macro analyst | Pros + retail | Per-token / platform plan | Conversational, MCP-integrated, multi-LLM | New, no track record, generic prompt-shop feel |
| **MenthorQ QUIN** (2025-26) | Regime + positioning context engine | Discretionary blend | Tiered (not surfaced) | Regime-aware framing | Limited public proof |

**Could not verify**: exact Tier1Alpha standalone price; Real Vision Pro Macro current 2026 figure (gated checkout); 42 Macro retail tier monthly rates; Macro Hive Prime monthly figure (page returned 403).

## 2. Table-stakes (what ALL of them have, Ichor must have)

- Daily/intraday written note with directional view per asset class.
- Economic calendar with event flagging.
- Cross-asset coverage (rates, FX, equities, vol, commodities).
- Some form of regime / volatility framework.
- Email + web delivery, mobile-friendly.
- Disclaimer / "not investment advice" footer.
- Author identity / institutional credibility.

## 3. Where they all fail — Ichor's wedge

1. **Session-aware delivery is absent everywhere.** All publish on a US calendar (morning ET note). None packages a dedicated London-open and NY-open brief tuned for the next 6-8 hours. **This is the clearest gap.**
2. **Polymarket as first-class macro signal.** Despite Polymarket reaching $25.7B March 2026 volume, ICE backing and Bernstein's $240B 2026 forecast, no incumbent surfaces prediction-market implied probabilities side-by-side with macro views. Pure wedge.
3. **Conversational query.** Only Jenova attempts it; incumbents are PDF/email/video. Letting a trader ask "why is DXY rallying despite dovish FOMC?" and get a structured answer with citations is genuinely missing.
4. **Per-instrument personalization.** Everyone publishes one global note; nobody serves an EURUSD-specific or XAUUSD-specific brief with bias + invalidation.
5. **Calibration transparency.** Polymarket publishes Brier scores; macro shops do not. A public reliability diagram on Ichor's own historical bias calls would be unique.
6. **French-native.** Zero serious francophone macro product. Small market but defensible niche.
7. **Real-time interactivity vs static publication.** Even Bloomberg's research is static documents.

## 4. Pricing benchmark (if Ichor were sold publicly)

For a discretionary FX/indices trader with €5k-50k AUM:
- **Hard ceiling**: ~€100/mo. Above this, the math breaks (1-2% monthly target on €10k = €100-200 P&L).
- **Sweet spot**: €29-49/mo (in line with Koyfin Plus, TradingView Premium). This is the "pay without thinking" zone.
- **Premium tier viable at €79-99/mo** if it credibly replaces 2+ existing subs (TradingView + a Substack + a research feed).
- **Above €150/mo**: only converts pro/RIA segment; not the V1 target.

Market clearing price for Ichor's single-user persona: **€39-59/mo**, with annual at €350-500.

> **Note Ichor-specific** : Eliot's case is single-user, no need to price publicly — Voie D Max 20x flat $200/mo IS the cost ceiling. This benchmark matters only if/when Ichor is ever opened to others.

## 5. Three positioning options

**Position A — "SpotGamma for FX/macro"** : deep niche on one mechanism (CB-NLP tone scoring + positioning + Polymarket implied path) with rigorous calibration. Trade-off: narrow TAM, but defensible technically. Price €79-129/mo.

**Position B — "Real Vision for retail, but interactive"** : narrative + framework + chat layer on top of curated voices/data. Trade-off: content-heavy, requires editorial cadence Eliot can't sustain solo; LLM-generated narrative risks AMF flagging. Price €29-49/mo.

**Position C (recommended) — "The session strategist"** : Ichor delivers a London-open and NY-open brief per instrument (EURUSD, XAUUSD, NAS100…) with bias % + conviction + magnitude + invalidation, conversational follow-up, Polymarket overlay, public Brier score. **Wedge = session-awareness × per-asset × calibration transparency**, none of which incumbents do. Trade-off: requires the ML/regime/calibration stack ; positioning is harder to pitch in one sentence than A or B. Price €49-79/mo.

**Recommendation**: C aligns with Ichor's existing architecture (HMM regimes, isotonic calibration, Brier scoring, multi-agent stack) AND directly matches Eliot's stated need (session-aware, per-asset bias, conversational query).

---

**Key takeaways for the synthesis:**

1. **No incumbent does what Eliot wants.** Real gap, not a "me-too" build.
2. **Session-aware is the #1 unique angle.** All others publish on US calendar.
3. **Polymarket integration as first-class signal is virgin territory** in macro tools.
4. **Calibration transparency** (public Brier on our own bias calls) = unique trust mechanism.
5. **French-native** is small TAM but Eliot's native need.
6. **The 4-pass orchestration** (regime → asset → stress → invalidation) is novel for retail tools.

---

## Sources

- [SpotGamma plans](https://support.spotgamma.com/hc/en-us/articles/1500002666102)
- [Tier1 Alpha/Hedgeye MSR](https://accounts.hedgeye.com/products/market_situation_report/972!973)
- [Real Vision Pro Macro](https://www.realvision.com/membership/pro-macro)
- [Koyfin pricing](https://www.koyfin.com/pricing/)
- [42 Macro Summer promo $199](https://42macro.com/summer)
- [Bridgewater BDO history](https://www.bridgewater.com/50-years-of-the-bridgewater-daily-observations)
- [TradingView pricing 2026](https://chartwisehub.com/tradingview-pricing/)
- [Bloomberg $31,980/yr](https://costbench.com/software/financial-data-terminals/bloomberg-terminal/)
- [FactSet $4k-$50k](https://costbench.com/software/financial-data-terminals/factset/)
- [Macro Hive Pro](https://macrohive.com/pro-offering/)
- [Jenova AI Macro Strategist](https://www.jenova.ai/en/resources/ai-macro-strategist)
- [MenthorQ QUIN](https://menthorq.com/guide/best-ai-trading-platforms-2026/)
- [Polymarket institutional adoption](https://markets.financialcontent.com/stocks/article/predictstreet-2026-2-6-the-great-prediction-war-of-2026-polymarket-and-kalshi-battle-for-dominance-as-ice-enters-the-fray)
- [Polymarket $400M ICE backing](https://www.tradingkey.com/analysis/cryptocurrencies/more/261801030)
- [SocGen 2024 discretionary macro survey](https://thefullfx.com/discretionary-macro-most-popular-investor-strategy-survey/)

---

**Report compiled** : 2026-05-03 by main thread from research subagent output.
