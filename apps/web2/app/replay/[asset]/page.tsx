// /replay/[asset] — time-machine slider for past sessions.
//
// Cf SPEC.md §5 Phase A item #5 + §3.7 (RAG temporal anti-leakage).
//
// Live: GET /v1/sessions/{asset}?limit=10 → SessionCard history. Each
// row maps to a ReplaySnapshot via `adaptSession`. The slider state is
// in the client child `ReplayClient`. Falls back to a 7-day mock if the
// API is unreachable.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type SessionCard, type SessionCardList } from "@/lib/api";

import { ReplayClient, type ReplaySnapshot } from "./replay-client";

const MOCK_SNAPSHOTS: ReplaySnapshot[] = [
  {
    ts: "2026-04-28T07:00:00Z",
    conviction: 58,
    bias: "bull",
    thesis_excerpt: "ECB hawkish bias + DXY weakness post-PCE",
    realized_outcome: 1,
    brier_contribution: 0.176,
  },
  {
    ts: "2026-04-29T07:00:00Z",
    conviction: 62,
    bias: "bull",
    thesis_excerpt: "Continuation EUR strength on real-yield differential",
    realized_outcome: 1,
    brier_contribution: 0.144,
  },
  {
    ts: "2026-04-30T07:00:00Z",
    conviction: 51,
    bias: "neutral",
    thesis_excerpt: "Range tight pré-Lagarde, low vol calendar",
    realized_outcome: 0,
    brier_contribution: 0.26,
  },
  {
    ts: "2026-05-01T07:00:00Z",
    conviction: 41,
    bias: "bear",
    thesis_excerpt: "Profit-taking sur la dérive haussière",
    realized_outcome: 0,
    brier_contribution: 0.168,
  },
  {
    ts: "2026-05-02T07:00:00Z",
    conviction: 56,
    bias: "bull",
    thesis_excerpt: "Re-entry après pullback technique 1.0840",
    realized_outcome: 1,
    brier_contribution: 0.194,
  },
  {
    ts: "2026-05-03T07:00:00Z",
    conviction: 67,
    bias: "bull",
    thesis_excerpt: "DXY failure 105.20 + PMI eurozone surprise",
    realized_outcome: 1,
    brier_contribution: 0.108,
  },
  {
    ts: "2026-05-04T07:00:00Z",
    conviction: 72,
    bias: "bull",
    thesis_excerpt: "Setup long retest 1.0850–1.0860 post-ECB",
    realized_outcome: null,
    brier_contribution: null,
  },
];

interface PageProps {
  params: Promise<{ asset: string }>;
}

function biasFromDirection(d: SessionCard["bias_direction"]): "bull" | "bear" | "neutral" {
  if (d === "long") return "bull";
  if (d === "short") return "bear";
  return "neutral";
}

function deriveOutcome(c: SessionCard): number | null {
  // Brier_contribution is set by the reconciler once the session closes.
  // Without it we can't infer hit vs miss reliably.
  if (c.realized_close_session === null || c.realized_at === null) return null;
  // direction = long + brier < 0.25 → hit ; > 0.25 → miss. Same logic
  // as in routers/calibration.py:_aggregate.
  if (c.brier_contribution === null) return null;
  return c.brier_contribution < 0.25 ? 1 : 0;
}

function deriveExcerpt(c: SessionCard): string {
  // SessionCardOut doesn't expose `thesis` directly — derive a short
  // excerpt from regime + bias + magnitude. Honest fallback until the
  // schema delta surfaces the brain's narrative.
  const dir = c.bias_direction;
  const reg = c.regime_quadrant ?? "regime n/a";
  const mag =
    c.magnitude_pips_low !== null && c.magnitude_pips_high !== null
      ? `${c.magnitude_pips_low.toFixed(0)}-${c.magnitude_pips_high.toFixed(0)} pips`
      : "magnitude n/a";
  return `${dir.toUpperCase()} · ${reg} · target ${mag}`;
}

function adaptSession(c: SessionCard): ReplaySnapshot {
  return {
    ts: c.generated_at,
    conviction: Math.round(c.conviction_pct),
    bias: biasFromDirection(c.bias_direction),
    thesis_excerpt: deriveExcerpt(c),
    realized_outcome: deriveOutcome(c),
    brier_contribution: c.brier_contribution,
  };
}

export default async function ReplayPage({ params }: PageProps) {
  const { asset } = await params;
  const slug = asset.toUpperCase().replace("-", "_");
  const display = asset.toUpperCase().replace("_", "/").replace("-", "/");
  const data = await apiGet<SessionCardList>(`/v1/sessions/${slug}?limit=10`, {
    revalidate: 60,
  });
  const apiOnline = isLive(data);
  // History endpoint returns newest-first ; replay slider expects oldest-first.
  const snapshots: ReplaySnapshot[] =
    apiOnline && data.items.length > 0
      ? [...data.items].reverse().map(adaptSession)
      : MOCK_SNAPSHOTS;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Time-machine replay · {display}{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? `live · ${snapshots.length} snapshots` : "offline · mock"}
          </span>
        </p>
        <h1 className="text-4xl tracking-tight text-[var(--color-text-primary)]">
          <span className="font-mono">{display}</span>{" "}
          <span className="font-mono text-sm uppercase tracking-widest text-[var(--color-text-muted)]">
            replay {snapshots.length}j
          </span>
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Re-joue les cards passées avec{" "}
          <MetricTooltip
            term="anti-leakage temporel"
            definition="Le rendu pour timestamp T n'utilise QUE les données disponibles à T (created_at < T). Aucune fuite du futur dans l'analyse historique. Cf RAG §1.5."
            glossaryAnchor="anti-leakage"
            density="compact"
          >
            anti-leakage temporel
          </MetricTooltip>{" "}
          strict — le rendu à T n&apos;utilise que les données disponibles jusqu&apos;à T. Idéal
          pour évaluer les framings sans biais de rétrospection.
        </p>
      </header>

      <ReplayClient snapshots={snapshots} />
    </div>
  );
}
