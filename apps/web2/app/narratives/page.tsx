// /narratives — top emerging narratives from `services.narrative_tracker`.
//
// Live: GET /v1/narratives?hours=48&top_k=20. The API exposes per-keyword
// stats (count, share, sample_title) ; sentiment/intensity-trend signals
// are deferred until the News-NLP Couche-2 agent populates the cluster
// table.

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type NarrativeReport, type NarrativeTopic } from "@/lib/api";

interface NarrativeView {
  label: string;
  intensity: number; // 0..1 — derived from `share`
  n_articles: number;
  representative_headline: string | null;
}

const MOCK_NARRATIVES: NarrativeView[] = [
  {
    label: "AI capex deceleration",
    intensity: 0.78,
    n_articles: 42,
    representative_headline: "Hyperscalers cut Q4 capex guidance 8 % vs prior",
  },
  {
    label: "ECB hawkish pivot",
    intensity: 0.62,
    n_articles: 28,
    representative_headline: "Lagarde signals risk of restrictive bias longer than priced",
  },
  {
    label: "China property contagion 2.0",
    intensity: 0.51,
    n_articles: 19,
    representative_headline: "Property developer Vanke debt restructuring talks",
  },
  {
    label: "Mid-East escalation tail risk",
    intensity: 0.44,
    n_articles: 31,
    representative_headline: "Diplomatic rupture between Israel and Iran proxy actors",
  },
  {
    label: "US disinflation continues",
    intensity: 0.39,
    n_articles: 16,
    representative_headline: "Core PCE prints 2.7 % YoY, below 2.9 % consensus",
  },
];

function adaptTopics(report: NarrativeReport): NarrativeView[] {
  // `share` ∈ [0, 1] is the per-topic share of total tokens — it doubles
  // as an intensity proxy. We normalize to make the top topic = 1.0.
  const top = report.topics[0];
  const max = top !== undefined ? top.share || 1 : 1;
  return report.topics.slice(0, 8).map((t: NarrativeTopic) => ({
    label: t.keyword,
    intensity: Math.min(1, t.share / max),
    n_articles: t.count,
    representative_headline: t.sample_title,
  }));
}

export default async function NarrativesPage() {
  const data = await apiGet<NarrativeReport>("/v1/narratives?hours=48&top_k=20", {
    revalidate: 60,
  });
  const apiOnline = isLive(data);
  const narratives: NarrativeView[] =
    apiOnline && data.topics.length > 0 ? adaptTopics(data) : MOCK_NARRATIVES;
  const summary = apiOnline
    ? `${data.n_documents} documents · ${data.n_tokens} tokens · window ${data.window_hours}h`
    : "5 mock narratives · refresh 4h";

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Narratives · {summary}{" "}
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
          Narratives
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Top keywords extraits de cb_speeches + news_items via{" "}
          <MetricTooltip
            term="services.narrative_tracker"
            definition="Tokenisation simple + filtre stopwords + comptage. Pondérée par fenêtre temporelle. Pas encore clustering NLP — la Couche-2 News-NLP enrichira intensity + sentiment + entities."
            glossaryAnchor="narrative-tracker"
            density="compact"
          >
            services.narrative_tracker
          </MetricTooltip>
          . Intensité ∝ part du keyword dans le pool. Sentiment/entities en attente Couche-2.
        </p>
      </header>

      <ol className="space-y-4">
        {narratives.map((n, i) => (
          <li
            key={`${n.label}-${i}`}
            className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
          >
            <header className="mb-3 flex items-baseline justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm tabular-nums text-[var(--color-text-muted)]">
                  #{i + 1}
                </span>
                <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                  {n.label}
                </h2>
              </div>
              <BiasIndicator
                bias="neutral"
                value={n.intensity * 100}
                unit="%"
                variant="default"
                size="sm"
                ariaLabel={`Intensité ${Math.round(n.intensity * 100)}%`}
              />
            </header>
            {n.representative_headline && (
              <p className="mb-3 text-sm text-[var(--color-text-secondary)]">
                <span className="text-[var(--color-text-muted)]">«&nbsp;</span>
                {n.representative_headline}
                <span className="text-[var(--color-text-muted)]">&nbsp;»</span>
              </p>
            )}
            <div className="flex flex-wrap items-baseline gap-3 text-xs">
              <span className="font-mono text-[var(--color-text-muted)]">
                {n.n_articles} mention{n.n_articles > 1 ? "s" : ""}
              </span>
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-6 text-xs text-[var(--color-text-muted)]">
        Note : la Couche-2 News-NLP enrichira chaque narrative avec sentiment FinBERT-tone-weighted,
        entités nommées, et trend 24h. Endpoint <code className="font-mono">/v1/narratives</code>{" "}
        sera étendu en conséquence.
      </p>
    </div>
  );
}
