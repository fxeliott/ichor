/**
 * /narratives — top keywords driving the news + cb_speeches corpus.
 *
 * VISION_2026 delta J. The same data the brain Pass 1 régime call
 * sees ; this page is also a debug view of "what is Claude looking
 * at right now".
 */

import { ApiError } from "../../lib/api";

export const metadata = { title: "Narratives" };
export const dynamic = "force-dynamic";
export const revalidate = 300;

interface TopicOut {
  keyword: string;
  count: number;
  share: number;
  sample_title: string | null;
}

interface NarrativeOut {
  window_hours: number;
  n_documents: number;
  n_tokens: number;
  topics: TopicOut[];
}

async function fetchNarrative(hours: number): Promise<NarrativeOut> {
  const url = `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/narratives?hours=${hours}&top_k=30`;
  const r = await fetch(url, {
    next: { revalidate: 300 },
    headers: { Accept: "application/json" },
  });
  if (!r.ok) throw new ApiError(`/v1/narratives ${r.status}`, r.status);
  return r.json() as Promise<NarrativeOut>;
}

export default async function NarrativesPage() {
  let report24: NarrativeOut | null = null;
  let report168: NarrativeOut | null = null;
  let error: string | null = null;
  try {
    [report24, report168] = await Promise.all([
      fetchNarrative(24),
      fetchNarrative(168),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown";
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
          Narratives macro
        </h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1 max-w-2xl">
          Mots-clés dominants extraits des discours banques centrales et
          des news des 24h / 7j. Chaque keyword affiche son nombre de
          documents et sa part du corpus. Doublons (24h dans 7j) =
          narrative récurrente, écart 24h vs 7j ≫ 0 = narrative émergente.
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {report24 && <Panel report={report24} title="Dernières 24h" />}
          {report168 && <Panel report={report168} title="7 derniers jours" />}
        </div>
      )}
    </div>
  );
}

function Panel({ report, title }: { report: NarrativeOut; title: string }) {
  const maxShare = Math.max(0.0001, ...report.topics.map((t) => t.share));
  return (
    <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">{title}</h2>
        <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
          {report.n_documents} docs · {report.n_tokens} tokens
        </p>
      </header>
      {report.topics.length === 0 ? (
        <p className="text-sm text-[var(--color-ichor-text-subtle)]">
          Pas assez de documents dans la fenêtre.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {report.topics.map((t) => {
            const pct = (t.share / maxShare) * 100;
            return (
              <li key={t.keyword} className="group">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-mono text-[var(--color-ichor-text)] capitalize">
                    {t.keyword}
                  </span>
                  <span className="text-[11px] text-[var(--color-ichor-text-subtle)] font-mono whitespace-nowrap">
                    {t.count} doc · {(t.share * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-1.5 rounded bg-[var(--color-ichor-surface-2)] overflow-hidden mt-1">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500/70 to-sky-400/70 transition-all"
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
                {t.sample_title && (
                  <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mt-1 line-clamp-1 italic">
                    “{t.sample_title}”
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
