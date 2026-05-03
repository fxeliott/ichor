import Link from "next/link";
import { EmptyState, SourceBadge } from "@ichor/ui";
import {
  ApiError,
  listNews,
  type NewsItem,
  type NewsSourceKind,
  type NewsTone,
} from "../../lib/api";

const KIND_OPTIONS: { value: NewsSourceKind | "all"; label: string }[] = [
  { value: "all", label: "Toutes sources" },
  { value: "central_bank", label: "Banques centrales" },
  { value: "regulator", label: "Régulateurs" },
  { value: "news", label: "News finance" },
  { value: "social", label: "Social" },
  { value: "academic", label: "Académique" },
];

const TONE_OPTIONS: { value: NewsTone | "all"; label: string }[] = [
  { value: "all", label: "Tous tons" },
  { value: "positive", label: "Positif" },
  { value: "neutral", label: "Neutre" },
  { value: "negative", label: "Négatif" },
];

const KIND_TO_BADGE: Record<NewsSourceKind, "central_bank" | "news" | "internal"> = {
  central_bank: "central_bank",
  regulator: "internal",
  news: "news",
  social: "news",
  academic: "internal",
};

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export const metadata = { title: "News" };
export const dynamic = "force-dynamic";
export const revalidate = 60;

interface PageProps {
  searchParams: Promise<{ kind?: string; tone?: string; source?: string }>;
}

export default async function NewsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const sourceKind =
    params.kind && params.kind !== "all"
      ? (params.kind as NewsSourceKind)
      : undefined;
  const tone =
    params.tone && params.tone !== "all" ? (params.tone as NewsTone) : undefined;
  const source = params.source?.trim() || undefined;

  let items: NewsItem[] = [];
  let error: string | null = null;
  try {
    items = await listNews({
      ...(sourceKind ? { sourceKind } : {}),
      ...(tone ? { tone } : {}),
      ...(source ? { source } : {}),
      sinceMinutes: 24 * 60,
      limit: 100,
    });
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100 mb-1">News</h1>
        <p className="text-sm text-neutral-400">
          Dépêches collectées en continu (Fed, ECB, BoE, BBC, SEC) — refresh
          toutes les 15 min.
        </p>
      </header>

      <form
        method="get"
        className="flex flex-wrap items-end gap-3 mb-6 p-3 rounded border border-neutral-800 bg-neutral-900/30"
      >
        <label className="flex flex-col text-xs text-neutral-400 gap-1">
          <span>Type de source</span>
          <select
            name="kind"
            defaultValue={params.kind ?? "all"}
            className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-neutral-100"
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-neutral-400 gap-1">
          <span>Source (slug)</span>
          <input
            type="text"
            name="source"
            defaultValue={params.source ?? ""}
            placeholder="ecb_press"
            pattern="[a-z0-9_]{1,64}"
            className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm font-mono text-neutral-100 w-40"
          />
        </label>
        <label className="flex flex-col text-xs text-neutral-400 gap-1">
          <span>Ton (FinBERT)</span>
          <select
            name="tone"
            defaultValue={params.tone ?? "all"}
            className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-neutral-100"
          >
            {TONE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="px-3 py-1 rounded border border-emerald-700/60 bg-emerald-950/40 text-emerald-200 text-sm hover:bg-emerald-900/40 transition"
        >
          Filtrer
        </button>
        {(sourceKind || source || tone) && (
          <Link
            href="/news"
            className="text-xs text-neutral-500 hover:text-neutral-300"
          >
            Réinitialiser
          </Link>
        )}
        <span className="ml-auto text-[11px] text-neutral-500 font-mono">
          {items.length} dépêches
        </span>
      </form>

      {error ? (
        <EmptyState
          title="API injoignable"
          description={`Détails techniques : ${error}`}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Aucune dépêche"
          description="Les collectors RSS tournent toutes les 15 min. Premières dépêches dans la prochaine fenêtre."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((it) => (
            <li
              key={it.id}
              className="rounded border border-neutral-800 bg-neutral-900/40 p-3"
            >
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <SourceBadge
                  citedText={it.source}
                  source={it.source_kind}
                  url={it.url}
                  kind={KIND_TO_BADGE[it.source_kind]}
                />
                <time
                  dateTime={it.published_at}
                  className="text-[11px] text-neutral-500 font-mono"
                >
                  {fmtAt(it.published_at)}
                </time>
              </div>
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-base font-medium text-neutral-100 hover:text-emerald-300"
              >
                {it.title}
              </a>
              {it.summary && (
                <p className="mt-1 text-sm text-neutral-400 leading-relaxed line-clamp-3">
                  {it.summary}
                </p>
              )}
              {it.tone_label && (
                <span
                  className={
                    "mt-2 inline-block text-[11px] font-mono px-1.5 py-0.5 rounded " +
                    (it.tone_label === "positive"
                      ? "bg-emerald-900/40 text-emerald-200"
                      : it.tone_label === "negative"
                        ? "bg-red-900/40 text-red-200"
                        : "bg-neutral-800 text-neutral-400")
                  }
                >
                  ton {it.tone_label}
                  {it.tone_score != null
                    ? ` (${(it.tone_score * 100).toFixed(0)}%)`
                    : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
