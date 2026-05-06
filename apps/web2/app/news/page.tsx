// /news — recent news feed (RSS + Polygon News + GDELT clustered).
//
// Live: GET /v1/news?since_minutes=720&limit=80 (last 12h, ranked
// newest-first). Tone score is populated by the FinBERT-tone worker;
// rows without tone are shown with a neutral muted indicator.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type NewsItem as ApiNews } from "@/lib/api";

interface NewsItem {
  id: string;
  source: string;
  title: string;
  url: string;
  published_at: string;
  tone: number;
  tickers: string[];
}

function adapt(n: ApiNews): NewsItem {
  return {
    id: n.id,
    source: n.source,
    title: n.title,
    url: n.url,
    published_at: n.published_at,
    tone: n.tone_score ?? 0,
    tickers: [], // ticker enrichment isn't on /v1/news yet
  };
}

const MOCK_NEWS: NewsItem[] = [
  {
    id: "n1",
    source: "Reuters",
    title: "ECB's Lagarde signals risk of restrictive bias longer than priced",
    url: "https://example.com/n1",
    published_at: "2026-05-04T07:18:00Z",
    tone: 0.32,
    tickers: ["EUR", "ECB"],
  },
  {
    id: "n2",
    source: "Bloomberg",
    title: "Hyperscalers cut Q4 capex guidance 8 % vs prior",
    url: "https://example.com/n2",
    published_at: "2026-05-04T06:45:00Z",
    tone: -0.41,
    tickers: ["NVDA", "MSFT", "GOOGL", "META"],
  },
  {
    id: "n3",
    source: "FT",
    title: "Core PCE prints 2.7 % YoY, below 2.9 % consensus — disinflation continues",
    url: "https://example.com/n3",
    published_at: "2026-05-04T06:30:00Z",
    tone: 0.55,
    tickers: ["USD", "Fed"],
  },
  {
    id: "n4",
    source: "Reuters",
    title: "Property developer Vanke debt restructuring talks intensify",
    url: "https://example.com/n4",
    published_at: "2026-05-04T05:12:00Z",
    tone: -0.62,
    tickers: ["China", "PBoC"],
  },
  {
    id: "n5",
    source: "WSJ",
    title: "Diplomatic rupture between Israel and Iran proxy actors",
    url: "https://example.com/n5",
    published_at: "2026-05-04T04:55:00Z",
    tone: -0.71,
    tickers: ["Israel", "Iran"],
  },
];

function toneColor(tone: number): string {
  if (tone > 0.3) return "var(--color-bull)";
  if (tone < -0.3) return "var(--color-bear)";
  return "var(--color-text-muted)";
}

export default async function NewsPage() {
  const data = await apiGet<ApiNews[]>("/v1/news?since_minutes=720&limit=80", {
    revalidate: 30,
  });
  const apiOnline = isLive(data);
  const news: NewsItem[] = apiOnline && data.length > 0 ? data.map(adapt) : MOCK_NEWS;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          News · feed unifié 12h glissantes · {news.length} headlines{" "}
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
          News
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Headlines aggregées RSS + Polygon News (ticker-linked) + GDELT 2.0 events. Tone enrichi
          par{" "}
          <MetricTooltip
            term="FinBERT-tone"
            definition="HuggingFace `yiyanghkust/finbert-tone` — modèle BERT fine-tuné sur les sentiments financiers. Score ∈ [-1, +1] : positif/neutral/négatif."
            glossaryAnchor="finbert-tone"
            density="compact"
          >
            FinBERT-tone
          </MetricTooltip>{" "}
          en post-traitement. Filtre ticker-linked sur la page asset drill-down.
        </p>
      </header>

      <ul className="space-y-3">
        {news.map((n) => (
          <li
            key={n.id}
            className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4"
          >
            <header className="mb-1 flex flex-wrap items-baseline gap-3 text-xs">
              <span className="font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                {n.source}
              </span>
              <time dateTime={n.published_at} className="font-mono text-[var(--color-text-muted)]">
                {new Date(n.published_at).toLocaleTimeString("fr-FR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              <span
                className="ml-auto font-mono tabular-nums"
                style={{ color: toneColor(n.tone) }}
                aria-label={`Tone ${n.tone.toFixed(2)}`}
              >
                tone {n.tone > 0 ? "+" : ""}
                {n.tone.toFixed(2)}
              </span>
            </header>
            <a
              href={n.url}
              className="block text-sm font-medium text-[var(--color-text-primary)] hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              {n.title}
            </a>
            {n.tickers.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1">
                {n.tickers.map((t) => (
                  <li
                    key={t}
                    className="rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-secondary)]"
                  >
                    {t}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
