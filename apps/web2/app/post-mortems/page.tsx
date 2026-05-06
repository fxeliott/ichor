// /post-mortems — weekly post-mortems history (8-section template AUTOEVO §4).
//
// Live: GET /v1/post-mortems (newest-first, summary metadata only).
// Falls back to a deterministic mock with "API offline" pill if unreachable.

import Link from "next/link";

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type PostMortemList, type PostMortemSummary } from "@/lib/api";

const MOCK_FALLBACK: PostMortemSummary[] = [
  {
    id: "mock-2026-w18",
    iso_year: 2026,
    iso_week: 18,
    generated_at: "2026-05-04T18:00:00Z",
    markdown_path: "docs/post_mortem/2026-W18.md",
    n_top_hits: 5,
    n_top_miss: 5,
    n_drift_flags: 1,
    brier_30d: 0.142,
    actionable_count: 4,
    actionable_resolved: 1,
  },
  {
    id: "mock-2026-w17",
    iso_year: 2026,
    iso_week: 17,
    generated_at: "2026-04-27T18:00:00Z",
    markdown_path: "docs/post_mortem/2026-W17.md",
    n_top_hits: 5,
    n_top_miss: 4,
    n_drift_flags: 0,
    brier_30d: 0.151,
    actionable_count: 3,
    actionable_resolved: 3,
  },
  {
    id: "mock-2026-w16",
    iso_year: 2026,
    iso_week: 16,
    generated_at: "2026-04-20T18:00:00Z",
    markdown_path: "docs/post_mortem/2026-W16.md",
    n_top_hits: 5,
    n_top_miss: 5,
    n_drift_flags: 2,
    brier_30d: 0.158,
    actionable_count: 5,
    actionable_resolved: 5,
  },
];

export default async function PostMortemsPage() {
  const data = await apiGet<PostMortemList>("/v1/post-mortems?limit=50", { revalidate: 60 });
  const apiOnline = isLive(data);
  const items: PostMortemSummary[] =
    apiOnline && data.items.length > 0 ? data.items : MOCK_FALLBACK;
  const total = apiOnline ? data.total : items.length;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Post-mortems hebdomadaires · ISO weeks{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? `live · ${total}` : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Post-mortems
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Réunion auto-générée chaque dimanche 18h Paris par Claude Opus 4.7. Suit le{" "}
          <MetricTooltip
            term="template 8 sections"
            definition="Header, Top hits, Top miss, Drift detected, Narratives émergentes, Calibration, Suggestions amendments, Stats raw. Cf docs/SPEC_V2_AUTOEVO.md §4."
            glossaryAnchor="post-mortem-template"
            density="compact"
          >
            template 8 sections AUTOEVO §4
          </MetricTooltip>
          . Le markdown source est versionné dans{" "}
          <code className="font-mono">docs/post_mortem/{"{YYYY-Www}.md"}</code>.
        </p>
      </header>

      <ol className="space-y-3">
        {items.map((p) => {
          const slug = `${p.iso_year}-W${String(p.iso_week).padStart(2, "0")}`;
          const date = new Date(p.generated_at);
          const resolution_pct =
            p.actionable_count > 0 ? (p.actionable_resolved / p.actionable_count) * 100 : 0;
          return (
            <li key={slug}>
              <Link
                href={`/post-mortems/${slug}`}
                className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5 transition-colors hover:border-[var(--color-border-strong)]"
              >
                <header className="mb-2 flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                    Semaine ISO {slug}
                  </h2>
                  <time
                    dateTime={p.generated_at}
                    className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
                  >
                    {date.toLocaleDateString("fr-FR")}
                  </time>
                </header>
                <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  <Stat label="Top hits" value={String(p.n_top_hits)} />
                  <Stat label="Top miss" value={String(p.n_top_miss)} />
                  <Stat
                    label="Brier 30d"
                    value={p.brier_30d !== null ? p.brier_30d.toFixed(3) : "—"}
                  />
                  <Stat label="Drift" value={String(p.n_drift_flags)} />
                </dl>
                {p.actionable_count > 0 && (
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                      <span>
                        Actionables : {p.actionable_resolved}/{p.actionable_count}
                      </span>
                      <span
                        className="tabular-nums"
                        style={{
                          color:
                            resolution_pct >= 80
                              ? "var(--color-bull)"
                              : resolution_pct >= 50
                                ? "var(--color-warn)"
                                : "var(--color-bear)",
                        }}
                      >
                        {resolution_pct.toFixed(0)}% résolus
                      </span>
                    </div>
                    <div
                      role="progressbar"
                      aria-valuenow={p.actionable_resolved}
                      aria-valuemin={0}
                      aria-valuemax={p.actionable_count}
                      className="h-1 overflow-hidden rounded bg-[var(--color-bg-elevated)]"
                    >
                      <span
                        aria-hidden="true"
                        className="block h-full"
                        style={{
                          width: `${resolution_pct}%`,
                          background:
                            resolution_pct >= 80
                              ? "var(--color-bull)"
                              : resolution_pct >= 50
                                ? "var(--color-warn)"
                                : "var(--color-bear)",
                        }}
                      />
                    </div>
                  </div>
                )}
              </Link>
            </li>
          );
        })}
      </ol>

      <p className="mt-6 text-xs text-[var(--color-text-muted)]">
        Cron <code className="font-mono">ichor-post-mortem.timer</code> · dimanche 18h Europe/Paris
        · Claude Opus 4.7 lit les 7 derniers jours et produit ce rapport. Push iOS quand prêt.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-sm tabular-nums text-[var(--color-text-primary)]">
        {value}
      </dd>
    </div>
  );
}
