/**
 * /sources — exhaustive catalog of all data sources Ichor uses.
 *
 * Transparency page : Eliot can see every upstream feed the brain
 * has access to, with a direct URL to verify any cited source.
 * Powers the "click a number → see provenance" UX promised in
 * VISION_2026 §8 (institutional-grade anti-hallucination).
 */

export const metadata = { title: "Sources" };

interface Source {
  id: string;
  category: string;
  name: string;
  description: string;
  url: string;
  collector: string | null;
  cadence: string;
  pricing: string;
  tableSlot: string | null;
  status: "live" | "scaffold" | "deferred";
}

const SOURCES: Source[] = [
  // ───────────────────────── MARKET DATA ─────────────────────────
  {
    id: "polygon",
    category: "Market data",
    name: "Polygon.io / Massive Currencies",
    description:
      "1-min OHLCV intraday on EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, XAU/USD + indices via REST aggs endpoint.",
    url: "https://massive.com/currencies",
    collector: "polygon",
    cadence: "1 min cron",
    pricing: "$49/mo flat",
    tableSlot: "polygon_intraday",
    status: "live",
  },
  {
    id: "yfinance",
    category: "Market data",
    name: "Yahoo Finance (yfinance) + Stooq",
    description:
      "Daily OHLCV fallback chain when Polygon is unavailable. EOD bars on the 8 Phase-1 assets.",
    url: "https://finance.yahoo.com",
    collector: "market_data",
    cadence: "daily 23:10 Paris",
    pricing: "free",
    tableSlot: "market_data",
    status: "live",
  },

  // ───────────────────────── MACRO ────────────────────────────────
  {
    id: "fred",
    category: "Macro",
    name: "St. Louis Fed FRED",
    description:
      "37 series : DXY broad, US10Y, VIX, TIPS real yields (DFII10/5/30), HY OAS, IG OAS, T10Y2Y, foreign 10Y (DE/JP/UK/AU/CA), CPI, PAYEMS, UNRATE, GDP, INDPRO, SOFR, EFFR, RRP, WALCL, etc.",
    url: "https://fred.stlouisfed.org",
    collector: "fred + fred_extended",
    cadence: "every 4 h",
    pricing: "free",
    tableSlot: "fred_observations",
    status: "live",
  },

  // ───────────────────────── GEOPOLITICS ─────────────────────────
  {
    id: "gdelt",
    category: "Geopolitics",
    name: "GDELT 2.0 DOC API",
    description:
      "Translingual news article-level events with tone classification. 8 keyword buckets (Fed, ECB, BoJ, BoE, geopolitics, oil, gold, US data).",
    url: "https://gdeltproject.org",
    collector: "gdelt",
    cadence: "every 2 h (post backoff fix)",
    pricing: "free",
    tableSlot: "gdelt_events",
    status: "live",
  },
  {
    id: "ai_gpr",
    category: "Geopolitics",
    name: "AI-GPR Index (Caldara-Iacoviello)",
    description:
      "LLM-scored daily geopolitical risk index built from NYT/WaPo/Chicago Tribune. Full historical series 1960-present.",
    url: "https://www.matteoiacoviello.com/ai_gpr.html",
    collector: "ai_gpr (xls parser via xlrd)",
    cadence: "daily on demand (15096 obs loaded)",
    pricing: "free",
    tableSlot: "gpr_observations",
    status: "live",
  },

  // ───────────────────────── SENTIMENT / POSITIONING ─────────────
  {
    id: "polymarket",
    category: "Prediction markets",
    name: "Polymarket Gamma API",
    description:
      "Decentralized prediction markets (Fed-cut, recession, election, geopolitical events). 'Insider' truth-engine via on-chain pricing.",
    url: "https://polymarket.com",
    collector: "polymarket",
    cadence: "every 5 min",
    pricing: "free",
    tableSlot: "polymarket_snapshots",
    status: "live",
  },
  {
    id: "kalshi",
    category: "Prediction markets",
    name: "Kalshi (CFTC-regulated)",
    description:
      "US-regulated event contracts. Volume-sorted top markets via /markets discovery.",
    url: "https://kalshi.com",
    collector: "kalshi (discovery)",
    cadence: "on-demand polling",
    pricing: "free",
    tableSlot: "kalshi_markets",
    status: "live",
  },
  {
    id: "manifold",
    category: "Prediction markets",
    name: "Manifold Markets",
    description:
      "Community wisdom-of-crowds via play-money. Discovery on 10 macro topics (fed rate, recession, ECB, BoJ, election, etc.).",
    url: "https://manifold.markets",
    collector: "manifold (discovery)",
    cadence: "on-demand polling",
    pricing: "free",
    tableSlot: "manifold_markets",
    status: "live",
  },
  {
    id: "cot",
    category: "Positioning",
    name: "CFTC Disaggregated Futures Only",
    description:
      "Weekly speculator vs commercial positioning on EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, XAU/USD, NAS100. Published Friday post-Tuesday close.",
    url: "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
    collector: "cot",
    cadence: "Friday 23:00 Paris",
    pricing: "free",
    tableSlot: "cot_positions",
    status: "live",
  },

  // ───────────────────────── CENTRAL BANKS ──────────────────────
  {
    id: "bis",
    category: "Central banks",
    name: "BIS speech aggregator",
    description:
      "BIS public speech feed + per-CB feeds (Fed, ECB, BoE, BoJ). 126 speeches indexed currently.",
    url: "https://www.bis.org",
    collector: "cb_speeches",
    cadence: "every 6 h",
    pricing: "free",
    tableSlot: "cb_speeches",
    status: "live",
  },

  // ───────────────────────── NEWS ────────────────────────────────
  {
    id: "rss",
    category: "News",
    name: "RSS pollers (Reuters / BBC / Fed / ECB / BoE / Treasury / SEC)",
    description:
      "7 official feeds. ~176 items currently in DB. Tone label populated by FinBERT-tone (planned, currently null).",
    url: "https://www.reuters.com",
    collector: "rss",
    cadence: "every 15 min",
    pricing: "free",
    tableSlot: "news_items",
    status: "live",
  },
  {
    id: "polygon_news",
    category: "News",
    name: "Massive News API (ticker-linked)",
    description:
      "Tied to the Currencies subscription — richer than RSS thanks to per-article ticker tagging (mega-cap 7 + DXY + GLD + indices).",
    url: "https://massive.com/news",
    collector: "polygon_news",
    cadence: "deferred to brain on-demand",
    pricing: "included in $49 Currencies plan",
    tableSlot: "(reuses news_items)",
    status: "live",
  },

  // ───────────────────────── OPTIONS / GEX ──────────────────────
  {
    id: "flashalpha",
    category: "Options / GEX",
    name: "FlashAlpha free tier",
    description:
      "SPX + NDX dealer GEX, gamma_flip, call_wall, put_wall, zero_gamma snapshots. 5 req/day free tier sized for 4 sessions × 2 tickers/day.",
    url: "https://flashalphalive.com",
    collector: "flashalpha (scaffold)",
    cadence: "awaits Eliot's free key",
    pricing: "free 5 req/day",
    tableSlot: "(no migration yet)",
    status: "scaffold",
  },

  // ───────────────────────── CLAUDE LLM ──────────────────────────
  {
    id: "claude",
    category: "LLM analysis",
    name: "Anthropic Claude (Max 20x)",
    description:
      "Brain orchestrator runs 4-pass per session card via Claude Code headless on Win11 (`claude -p`), routed through Cloudflare Tunnel. Voie D ADR-009 — flat $200/mo, no API consumption ever.",
    url: "https://claude.ai",
    collector: "n/a (claude-runner)",
    cadence: "on session-cards batch trigger",
    pricing: "$200/mo flat (Eliot's existing sub)",
    tableSlot: "session_card_audit (consumer)",
    status: "live",
  },
];

const STATUS_COLOR: Record<Source["status"], string> = {
  live: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  scaffold: "bg-amber-900/40 text-amber-200 border-amber-700/40",
  deferred: "bg-[var(--color-ichor-surface-2)] text-[var(--color-ichor-text-muted)] border-[var(--color-ichor-border-strong)]/40",
};

const CATEGORIES = Array.from(new Set(SOURCES.map((s) => s.category)));

export default function SourcesPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">Sources data</h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1 max-w-2xl">
          Liste exhaustive des feeds upstream que Ichor poll. Chaque carte
          session cite explicitement les sources qu&apos;elle utilise (FRED
          series IDs, Polygon tickers, CFTC market codes, Polymarket slugs,
          URLs news). Cliquez un nom pour vérifier la source à
          l&apos;upstream.
        </p>
      </header>

      <p className="text-[11px] text-[var(--color-ichor-text-subtle)] italic">
        🟢 live · 🟡 scaffold (prêt à activer) · ⚪ deferred
      </p>

      {CATEGORIES.map((cat) => {
        const items = SOURCES.filter((s) => s.category === cat);
        return (
          <section key={cat}>
            <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3">
              {cat} <span className="text-[var(--color-ichor-text-subtle)] text-sm">({items.length})</span>
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {items.map((s) => (
                <article
                  key={s.id}
                  className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-4 flex flex-col gap-2"
                >
                  <header className="flex items-baseline justify-between gap-2">
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-semibold text-[var(--color-ichor-text)] hover:text-emerald-300 truncate"
                    >
                      {s.name} ↗
                    </a>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${STATUS_COLOR[s.status]}`}
                    >
                      {s.status}
                    </span>
                  </header>
                  <p className="text-xs text-[var(--color-ichor-text-muted)] leading-snug">
                    {s.description}
                  </p>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-[var(--color-ichor-text-muted)] mt-1">
                    {s.collector && (
                      <>
                        <dt>Collector</dt>
                        <dd className="font-mono text-[var(--color-ichor-text-muted)]">
                          {s.collector}
                        </dd>
                      </>
                    )}
                    <dt>Cadence</dt>
                    <dd className="font-mono text-[var(--color-ichor-text-muted)]">{s.cadence}</dd>
                    <dt>Pricing</dt>
                    <dd className="text-[var(--color-ichor-text-muted)]">{s.pricing}</dd>
                    {s.tableSlot && (
                      <>
                        <dt>Table</dt>
                        <dd className="font-mono text-[var(--color-ichor-text-muted)] truncate">
                          {s.tableSlot}
                        </dd>
                      </>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          </section>
        );
      })}

      <footer className="border-t border-[var(--color-ichor-border)] pt-4">
        <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
          Les sources hors upstream (modèles empiriques code-internes :
          CB intervention probability, causal map canonique, surprise
          index z-score proxy) sont documentées dans{" "}
          <a
            href="/knowledge-graph"
            className="text-[var(--color-ichor-text-muted)] hover:text-emerald-300 underline"
          >
            /knowledge-graph
          </a>{" "}
          (carte causale) et{" "}
          <a
            href="/admin"
            className="text-[var(--color-ichor-text-muted)] hover:text-emerald-300 underline"
          >
            /admin
          </a>{" "}
          (compteurs DB live).
        </p>
        <p className="text-[11px] text-[var(--color-ichor-text-subtle)] italic mt-2">
          Sprint pending : audit FlashAlpha key activation, snapshot du
          data_pool per session_card pour reproductibilité, KalshiCategory
          filter macro/politics only (drop sport markets).
        </p>
      </footer>
    </div>
  );
}
