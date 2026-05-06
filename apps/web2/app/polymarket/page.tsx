// /polymarket — exploitation maximale Polymarket (whales + divergence + theme impact).
//
// Cf SPEC.md §3.9 + §5 Phase A item #8.
//
// Live wiring :
//   - DivergenceSection ← GET /v1/divergences (cross-venue scan)
//   - TopMoversSection  ← GET /v1/polymarket-impact (themed clusters,
//                         flattened to per-market rows)
//   - WhalesSection     remains MOCK (no whale API yet — needs trade
//                         history from Polymarket which isn't ingested)

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type DivergenceList, type PolymarketImpact } from "@/lib/api";

interface PolyMarketView {
  slug: string;
  question: string;
  yes_price: number;
  weight: number;
  theme_label: string;
}

interface DivergenceView {
  question: string;
  high_venue: string;
  high_price: number;
  low_venue: string;
  low_price: number;
  gap: number;
}

interface WhaleBet {
  slug: string;
  question: string;
  size_usd: number;
  side: "yes" | "no";
  ts: string;
}

const MOCK_MARKETS: PolyMarketView[] = [
  {
    slug: "fed-rate-cut-jul-2026",
    question: "Will the Fed cut rates by July 2026?",
    yes_price: 0.62,
    weight: 0.42,
    theme_label: "fed-policy",
  },
  {
    slug: "us-recession-2026",
    question: "Will the US enter a recession in 2026?",
    yes_price: 0.18,
    weight: 0.18,
    theme_label: "macro-risk",
  },
  {
    slug: "ecb-hold-may-2026",
    question: "Will ECB hold rates at May meeting?",
    yes_price: 0.71,
    weight: 0.21,
    theme_label: "ecb-policy",
  },
];

const MOCK_DIVERGENCES: DivergenceView[] = [
  {
    question: "Fed rate cut by July 2026",
    high_venue: "polymarket",
    high_price: 0.62,
    low_venue: "kalshi",
    low_price: 0.51,
    gap: 0.11,
  },
];

// Whales are illustrative until trade-tape ingestion lands.
const WHALES: WhaleBet[] = [
  {
    slug: "fed-rate-cut-jul-2026",
    question: "Fed cut by Jul",
    size_usd: 145_000,
    side: "yes",
    ts: "2026-05-04T05:18Z",
  },
  {
    slug: "btc-150k-by-q3",
    question: "BTC > $150K Q3",
    size_usd: 92_000,
    side: "no",
    ts: "2026-05-04T03:42Z",
  },
  {
    slug: "fed-rate-cut-jul-2026",
    question: "Fed cut by Jul",
    size_usd: 81_500,
    side: "yes",
    ts: "2026-05-04T01:55Z",
  },
];

function adaptMarkets(impact: PolymarketImpact): PolyMarketView[] {
  return impact.themes
    .flatMap((t) =>
      t.markets.map((m) => ({
        slug: m.slug,
        question: m.question,
        yes_price: m.yes,
        weight: m.weight,
        theme_label: t.label,
      })),
    )
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 12);
}

function adaptDivergences(d: DivergenceList): DivergenceView[] {
  return d.alerts.map((a) => ({
    question: a.question,
    high_venue: a.high_venue,
    high_price: a.high_price,
    low_venue: a.low_venue,
    low_price: a.low_price,
    gap: a.gap,
  }));
}

export default async function PolymarketPage() {
  const [impact, divergences] = await Promise.all([
    apiGet<PolymarketImpact>("/v1/polymarket-impact?hours=24&limit=200", {
      revalidate: 60,
    }),
    apiGet<DivergenceList>("/v1/divergences?since_hours=24&limit=10", {
      revalidate: 60,
    }),
  ]);

  const apiOnline = isLive(impact) || isLive(divergences);
  const markets = isLive(impact) && impact.themes.length > 0 ? adaptMarkets(impact) : MOCK_MARKETS;
  const alerts =
    isLive(divergences) && divergences.alerts.length > 0
      ? adaptDivergences(divergences)
      : MOCK_DIVERGENCES;
  const nScanned = isLive(impact) ? impact.n_markets_scanned : MOCK_MARKETS.length;

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <header className="mb-10 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Polymarket · whales + divergence cross-venue · {nScanned} markets scanned{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? "live" : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Polymarket
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Exploitation maximale des prediction markets : top markets pondérés par theme impact,
          whale bets &gt; $50K, et{" "}
          <MetricTooltip
            term="divergence cross-venue"
            definition="Quand un même événement (e.g. Fed cut Jul) a un yes price ≥ 5pp d'écart entre Polymarket / Kalshi / Manifold. Souvent un signal de mispricing exploitable."
            glossaryAnchor="cross-venue-divergence"
            density="compact"
          >
            divergence cross-venue
          </MetricTooltip>{" "}
          (Polymarket / Kalshi / Manifold).
        </p>
      </header>

      <DivergenceSection alerts={alerts} />
      <TopMoversSection markets={markets} />
      <WhalesSection whales={WHALES} />
    </div>
  );
}

function DivergenceSection({ alerts }: { alerts: DivergenceView[] }) {
  if (alerts.length === 0) {
    return (
      <section className="mb-12 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Divergence cross-venue · gap ≥ 5pp
        </h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          Aucune divergence active sur 24h — pricing cross-venue cohérent.
        </p>
      </section>
    );
  }
  return (
    <section className="mb-12 rounded-xl border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/5 p-6">
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-warn)]">
        ⚠ Divergence cross-venue · gap ≥ 5pp
      </h2>
      <ul className="space-y-2">
        {alerts.map((a) => (
          <li
            key={`${a.question}-${a.high_venue}-${a.low_venue}`}
            className="flex flex-wrap items-baseline gap-3 border-b border-[var(--color-border-subtle)] py-2 last:border-b-0"
          >
            <span className="font-medium text-[var(--color-text-primary)]">{a.question}</span>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              {a.high_venue} {(a.high_price * 100).toFixed(0)} % · {a.low_venue}{" "}
              {(a.low_price * 100).toFixed(0)} %
            </span>
            <span className="ml-auto font-mono text-sm tabular-nums text-[var(--color-warn)]">
              gap {(a.gap * 100).toFixed(1)}pp
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TopMoversSection({ markets }: { markets: PolyMarketView[] }) {
  return (
    <section className="mb-12">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Top markets · theme-weighted
      </h2>
      <ul className="grid gap-3 lg:grid-cols-2">
        {markets.map((m) => {
          const bias = m.yes_price >= 0.5 ? "bull" : "bear";
          return (
            <li
              key={m.slug}
              className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 shadow-[var(--shadow-sm)]"
            >
              <p className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">
                {m.question}
              </p>
              <div className="flex flex-wrap items-baseline gap-3 text-xs">
                <span className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
                  {(m.yes_price * 100).toFixed(0)} %
                </span>
                <BiasIndicator
                  bias={bias}
                  value={m.yes_price * 100}
                  unit="%"
                  variant="compact"
                  size="sm"
                />
                <span className="ml-auto font-mono text-[var(--color-text-muted)]">
                  theme: {m.theme_label} · w {m.weight.toFixed(2)}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function WhalesSection({ whales }: { whales: WhaleBet[] }) {
  return (
    <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Whale bets &gt; $50K · 24h{" "}
        <span className="ml-2 font-normal normal-case tracking-normal text-[var(--color-text-muted)]/70">
          (illustratif — trade-tape ingestion en attente)
        </span>
      </h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border-default)] text-left">
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Question
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Side
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Size
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              When
            </th>
          </tr>
        </thead>
        <tbody>
          {whales.map((w) => (
            <tr
              key={`${w.slug}-${w.ts}`}
              className="border-b border-[var(--color-border-subtle)] last:border-b-0"
            >
              <td className="py-2 text-sm text-[var(--color-text-primary)]">{w.question}</td>
              <td className="py-2">
                <span
                  className="font-mono text-xs uppercase tracking-widest"
                  style={{
                    color: w.side === "yes" ? "var(--color-bull)" : "var(--color-bear)",
                  }}
                >
                  {w.side}
                </span>
              </td>
              <td className="py-2 font-mono tabular-nums text-[var(--color-text-primary)]">
                ${(w.size_usd / 1000).toFixed(0)}k
              </td>
              <td className="py-2 font-mono text-xs text-[var(--color-text-muted)]">
                {new Date(w.ts).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
