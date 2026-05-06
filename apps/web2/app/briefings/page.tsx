// /briefings — list of recent session briefings + post-mortems.
//
// Live: GET /v1/briefings (paginated, newest-first).
// Falls back to a mock list with a visible "API offline" pill if unreachable.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type Briefing, type BriefingList } from "@/lib/api";

interface BriefingItem {
  id: string;
  kind: "session" | "post_mortem" | "crisis";
  asset?: string | undefined;
  title: string;
  excerpt: string;
  generated_at: string;
}

const MOCK_FALLBACK: BriefingItem[] = [
  {
    id: "b1",
    kind: "session",
    asset: "EUR_USD",
    title: "Pré-Londres EUR/USD · 2026-05-04",
    excerpt: "ECB hawkish bias 8h30 + DXY weakness post-PCE. Setup long retest 1.0850.",
    generated_at: "2026-05-04T07:00:00Z",
  },
  {
    id: "b3",
    kind: "crisis",
    title: "Crisis Mode · VIX +28 % en 90 min",
    excerpt:
      "VIX spot 24.8. Briefing ad-hoc Opus 4.7 généré. Cross-asset stress en haut du dashboard.",
    generated_at: "2026-05-04T13:42:00Z",
  },
  {
    id: "b4",
    kind: "post_mortem",
    title: "Post-mortem semaine ISO 2026-W18",
    excerpt:
      "Top hits 5 (EUR/USD bull 67% hit). Top miss 5 (NAS100 bear 41% miss). Drift ADWIN détecté sur USD/JPY.",
    generated_at: "2026-05-04T18:00:00Z",
  },
];

const KIND_BADGE: Record<BriefingItem["kind"], { label: string; color: string }> = {
  session: { label: "Session card", color: "var(--color-accent-cobalt-bright)" },
  post_mortem: { label: "Post-mortem", color: "var(--color-accent-warm)" },
  crisis: { label: "Crisis Mode", color: "var(--color-critical)" },
};

function classifyKind(briefingType: string): BriefingItem["kind"] {
  if (briefingType === "crisis") return "crisis";
  if (briefingType === "weekly") return "post_mortem";
  return "session";
}

function deriveTitle(b: Briefing): string {
  const date = new Date(b.triggered_at).toISOString().slice(0, 10);
  const asset = b.assets[0]?.replace("_", "/") ?? "multi-asset";
  if (b.briefing_type === "crisis") return `Crisis Mode · ${date}`;
  if (b.briefing_type === "weekly") return `Post-mortem hebdo · ${date}`;
  const phase =
    b.briefing_type === "pre_londres"
      ? "Pré-Londres"
      : b.briefing_type === "pre_ny"
        ? "Pré-NY"
        : b.briefing_type === "ny_mid"
          ? "NY mid"
          : b.briefing_type === "ny_close"
            ? "NY close"
            : b.briefing_type;
  return `${phase} ${asset} · ${date}`;
}

function deriveExcerpt(b: Briefing): string {
  const md = b.briefing_markdown ?? "";
  // First non-empty paragraph, stripped of markdown headers + code fences.
  const paragraph =
    md
      .split("\n\n")
      .map((p) => p.trim())
      .find((p) => p && !p.startsWith("#") && !p.startsWith("```")) ?? "";
  if (paragraph) {
    return paragraph.length > 200 ? paragraph.slice(0, 197) + "…" : paragraph;
  }
  return b.status === "completed"
    ? "(briefing markdown vide — voir le détail)"
    : `Status: ${b.status}`;
}

function adapt(b: Briefing): BriefingItem {
  return {
    id: b.id,
    kind: classifyKind(b.briefing_type),
    asset: b.assets[0],
    title: deriveTitle(b),
    excerpt: deriveExcerpt(b),
    generated_at: b.triggered_at,
  };
}

export default async function BriefingsPage() {
  const data = await apiGet<BriefingList>("/v1/briefings?limit=30", { revalidate: 30 });
  const apiOnline = isLive(data);
  const briefings: BriefingItem[] =
    apiOnline && data.items.length > 0 ? data.items.map(adapt) : MOCK_FALLBACK;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Briefings · session cards + post-mortems + crisis briefings{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? `live · ${data.total}` : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Briefings
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Toutes les{" "}
          <MetricTooltip
            term="cards persistées"
            definition="Chaque session card (Pré-Londres / Pré-NY) est stockée dans la table briefings + indexée RAG pour rétroaction. Le Brier est annoté par le reconciler nightly."
            glossaryAnchor="cards-persistees"
            density="compact"
          >
            cards persistées
          </MetricTooltip>{" "}
          (sessions, post-mortems hebdo, crisis briefings) ordonnées par date décroissante.
          Cliquable → détail markdown + sources citées.
        </p>
      </header>

      <ul className="space-y-3">
        {briefings.map((b) => {
          const kindMeta = KIND_BADGE[b.kind];
          return (
            <li
              key={b.id}
              className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5 shadow-[var(--shadow-sm)]"
            >
              <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span
                    className="inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                    style={{
                      color: kindMeta.color,
                      borderColor: kindMeta.color,
                    }}
                  >
                    {kindMeta.label}
                  </span>
                  {b.asset && (
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                      {b.asset.replace("_", "/")}
                    </span>
                  )}
                </div>
                <time
                  dateTime={b.generated_at}
                  className="font-mono text-[10px] text-[var(--color-text-muted)]"
                >
                  {new Date(b.generated_at).toLocaleString("fr-FR", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </time>
              </header>
              <h2 className="mb-1 text-lg font-semibold text-[var(--color-text-primary)]">
                {b.title}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]">{b.excerpt}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
