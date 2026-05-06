import Link from "next/link";
import { EmptyState } from "@ichor/ui";
import { ApiError, listBriefings, type Briefing, type BriefingType } from "../../lib/api";

const TYPE_OPTIONS: { value: BriefingType | "all"; label: string }[] = [
  { value: "all", label: "Tous types" },
  { value: "pre_londres", label: "Pré-Londres" },
  { value: "pre_ny", label: "Pré-NY" },
  { value: "ny_mid", label: "NY mid" },
  { value: "ny_close", label: "NY close" },
  { value: "weekly", label: "Weekly" },
  { value: "crisis", label: "Crisis Mode" },
];

const STATUS_COLORS: Record<Briefing["status"], string> = {
  pending: "bg-[var(--color-ichor-surface-2)] text-[var(--color-ichor-text-muted)]",
  context_assembled: "bg-sky-900/40 text-sky-200",
  claude_running: "bg-amber-900/40 text-amber-200",
  completed: "bg-emerald-900/40 text-emerald-200",
  failed: "bg-red-900/40 text-red-200",
};

const STATUS_LABELS: Record<Briefing["status"], string> = {
  pending: "en attente",
  context_assembled: "contexte prêt",
  claude_running: "Claude en cours",
  completed: "terminé",
  failed: "échoué",
};

const TYPE_LABELS: Record<BriefingType, string> = {
  pre_londres: "Pré-Londres",
  pre_ny: "Pré-NY",
  ny_mid: "NY mid",
  ny_close: "NY close",
  weekly: "Weekly",
  crisis: "Crisis Mode",
};

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export const metadata = {
  title: "Briefings",
};

export const dynamic = "force-dynamic";
export const revalidate = 30;

interface PageProps {
  searchParams: Promise<{ type?: string; asset?: string }>;
}

export default async function BriefingsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const briefingType =
    params.type && params.type !== "all" ? (params.type as BriefingType) : undefined;
  const asset = params.asset?.trim().toUpperCase() || undefined;

  let items: Briefing[] = [];
  let total = 0;
  let error: string | null = null;
  try {
    const list = await listBriefings({
      limit: 50,
      ...(briefingType ? { briefingType } : {}),
      ...(asset ? { asset } : {}),
    });
    items = list.items;
    total = list.total;
  } catch (err) {
    error =
      err instanceof ApiError ? err.message : err instanceof Error ? err.message : "unknown error";
  }

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)] mb-1">Briefings</h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)]">
          Historique complet des analyses générées par la chaîne Ichor.
        </p>
      </header>

      <form
        method="get"
        className="flex flex-wrap items-end gap-3 mb-6 p-3 rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40"
      >
        <label
          htmlFor="briefing-type"
          className="flex flex-col text-xs text-[var(--color-ichor-text-muted)] gap-1"
        >
          <span>Type</span>
          <select
            id="briefing-type"
            name="type"
            defaultValue={params.type ?? "all"}
            className="bg-[var(--color-ichor-surface)] border border-[var(--color-ichor-border-strong)] rounded px-2 py-1 text-sm text-[var(--color-ichor-text)]"
          >
            {TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label
          htmlFor="briefing-asset"
          className="flex flex-col text-xs text-[var(--color-ichor-text-muted)] gap-1"
        >
          <span>Actif (code)</span>
          <input
            id="briefing-asset"
            type="text"
            name="asset"
            defaultValue={params.asset ?? ""}
            placeholder="EUR_USD"
            pattern="[A-Z0-9_]{3,16}"
            title="Code en majuscules, lettres / chiffres / souligné, 3 à 16 caractères. Exemple : EUR_USD"
            aria-describedby="briefing-asset-help"
            className="bg-[var(--color-ichor-surface)] border border-[var(--color-ichor-border-strong)] rounded px-2 py-1 text-sm font-mono text-[var(--color-ichor-text)] w-32"
          />
          <span
            id="briefing-asset-help"
            className="text-[10px] text-[var(--color-ichor-text-muted)]"
          >
            Format : 3–16 caractères majuscules, ex. EUR_USD
          </span>
        </label>
        <button
          type="submit"
          className="px-3 py-1 rounded border border-emerald-700/60 bg-emerald-950/40 text-emerald-200 text-sm hover:bg-emerald-900/40 transition"
        >
          Filtrer
        </button>
        {(briefingType || asset) && (
          <Link
            href="/briefings"
            className="text-xs text-[var(--color-ichor-text-subtle)] hover:text-[var(--color-ichor-text-muted)]"
          >
            Réinitialiser
          </Link>
        )}
        <span className="ml-auto text-[11px] text-[var(--color-ichor-text-subtle)] font-mono">
          {total} résultat{total > 1 ? "s" : ""}
        </span>
      </form>

      {error ? (
        <EmptyState title="API injoignable" description={`Détails techniques : ${error}`} />
      ) : items.length === 0 ? (
        <EmptyState
          title="Aucun briefing trouvé"
          description="Ajustez les filtres ou attendez le prochain cron systemd (06h, 12h, 17h, 22h Paris)."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((b) => (
            <li key={b.id}>
              <Link
                href={`/briefings/${b.id}`}
                className="block rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 px-4 py-3 hover:border-[var(--color-ichor-border-strong)] transition"
              >
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <span className="text-sm text-[var(--color-ichor-text)]">
                    {TYPE_LABELS[b.briefing_type]}
                  </span>
                  <span
                    className={
                      "text-[11px] font-mono px-1.5 py-0.5 rounded " + STATUS_COLORS[b.status]
                    }
                    aria-label={`Statut : ${STATUS_LABELS[b.status]}`}
                  >
                    {STATUS_LABELS[b.status]}
                  </span>
                </div>
                <div className="flex items-baseline gap-3 text-xs text-[var(--color-ichor-text-subtle)]">
                  <time dateTime={b.triggered_at} className="font-mono">
                    {fmtAt(b.triggered_at)}
                  </time>
                  <span>·</span>
                  <span className="font-mono">
                    {b.assets.map((a) => a.replace("_", "/")).join(", ")}
                  </span>
                  {b.claude_duration_ms != null && (
                    <>
                      <span>·</span>
                      <span className="font-mono">{(b.claude_duration_ms / 1000).toFixed(1)}s</span>
                    </>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
