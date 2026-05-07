// /today — Pre-session checklist + best opportunities ranked.
//
// Cf SPEC.md §3.8 + §5 Phase A item #2:
//   - Best opportunities ranked du jour selon conviction × régime fit × confluence
//   - Calendrier d'events filtré sur fenêtre H-4h → H+1h sessions Londres + NY
//   - Checklist pre-session « go / no-go » 5 lignes
//
// Wiring status :
//   - CalendarSection ← GET /v1/calendar/upcoming?horizon_days=2 (live).
//   - ChecklistSection : derived locally from the upcoming calendar
//     (catalyst-surprise question is auto-flagged if a high-impact event
//     falls within the next 2 hours).
//   - BestOppsSection : 3 mock SessionCards (real wiring waits for the
//     SessionCardOut schema to expose trade plan + confluence drivers).

import { MetricTooltip, SessionCard, type Trigger } from "@/components/ui";
import {
  apiGet,
  isLive,
  type CalendarUpcoming,
  type EconomicEventListOut,
  type TodaySessionPreview,
  type TodaySnapshotOut,
} from "@/lib/api";
import {
  adaptCalendarToTriggers,
  adaptFFEventsToTriggers,
  adaptTodayBundleToTriggers,
  dedupeAndSortTriggers,
} from "@/lib/today-adapters";
// Phase A.9.1 — replaces the previously hardcoded NOW that froze /today
// on a single fixed moment (2026-05-04T07:42:00Z). Computed server-side
// per request — the page is `revalidate: 30` (cf SessionCard fetches
// below) so the value refreshes at most every 30s, fast enough to
// reflect a session window transition (boundaries are 06:00 / 08:30 /
// 12:00 / 13:30 / 16:30 / 18:00 / 21:00 / 22:30 Paris).
const NOW = new Date().toISOString();

const MOCK_TRIGGERS: Trigger[] = [
  {
    id: "ec1",
    label: "ECB Lagarde speech",
    scheduledAt: "2026-05-04T08:30:00.000Z",
    importance: "high",
  },
  {
    id: "ec2",
    label: "EU CPI Flash",
    scheduledAt: "2026-05-04T09:00:00.000Z",
    importance: "high",
  },
  {
    id: "ec3",
    label: "US ISM Mfg",
    scheduledAt: "2026-05-04T14:00:00.000Z",
    importance: "medium",
  },
  {
    id: "ec4",
    label: "Powell @Brookings",
    scheduledAt: "2026-05-04T17:00:00.000Z",
    importance: "high",
  },
];

interface ChecklistItem {
  id: string;
  question: string;
  status: "go" | "caution" | "no_go";
  detail: string;
}

const CHECKLIST: ChecklistItem[] = [
  {
    id: "regime",
    question: "Régime fit ?",
    status: "go",
    detail: "Risk-on, désinflation modérée — favorable aux setups longs cycliques",
  },
  {
    id: "conviction",
    question: "Conviction > 60 % sur ≥ 1 actif ?",
    status: "go",
    detail: "EUR/USD long 72%, XAU/USD short 64%",
  },
  {
    id: "confluence",
    question: "Confluence cohérente avec le régime ?",
    status: "go",
    detail: "DXY weakness + real yields favorable EUR + ECB hawkish bias",
  },
  {
    id: "calendar",
    question: "Pas de catalyst surprise ?",
    status: "caution",
    detail: "Lagarde 8h30 + EU CPI 9h00 — fenêtre serrée, prendre position après 9h15",
  },
  {
    id: "polymarket",
    question: "Polymarket pas en désaccord majeur ?",
    status: "go",
    detail: "Fed-cut probability stable +1pp 24h — pas de divergence cross-venue",
  },
];

export default async function TodayPage() {
  // First try the bundled /v1/today endpoint (single fetch, server-merged
  // calendar). If unavailable, fall back to co-fetching the two source
  // endpoints and merging client-side — the existing path stays as a
  // safety net during rollout.
  const bundle = await apiGet<TodaySnapshotOut>("/v1/today?horizon_days=2&top_n=3", {
    revalidate: 30,
  });
  const bundleOnline = isLive(bundle);

  let calTriggers: Trigger[] = [];
  let ffTriggers: Trigger[] = [];
  let calOnline = false;
  let ffOnline = false;
  let merged: Trigger[];
  let sourceLabel: string;

  if (bundleOnline) {
    merged = adaptTodayBundleToTriggers(bundle);
    sourceLabel = "Today bundle";
  } else {
    const [cal, ffEvents] = await Promise.all([
      apiGet<CalendarUpcoming>("/v1/calendar/upcoming?horizon_days=2", { revalidate: 30 }),
      apiGet<EconomicEventListOut>("/v1/economic-events?since_minutes=60&horizon_minutes=2880", {
        revalidate: 30,
      }),
    ]);
    calOnline = isLive(cal);
    ffOnline = isLive(ffEvents);
    calTriggers = isLive(cal) ? adaptCalendarToTriggers(cal) : [];
    ffTriggers = isLive(ffEvents) ? adaptFFEventsToTriggers(ffEvents) : [];
    merged = dedupeAndSortTriggers([...calTriggers, ...ffTriggers]).slice(0, 12);
    sourceLabel =
      calOnline && ffOnline
        ? "FRED + ForexFactory"
        : calOnline
          ? "FRED only"
          : ffOnline
            ? "ForexFactory only"
            : "mock";
  }

  const apiOnline = bundleOnline || calOnline || ffOnline;
  const triggers: Trigger[] = merged.length > 0 ? merged : MOCK_TRIGGERS;
  const eventsCount = apiOnline ? merged.length : null;
  const topSessions: TodaySessionPreview[] | null = bundleOnline ? bundle.top_sessions : null;

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <Header apiOnline={apiOnline} eventsCount={eventsCount} sourceLabel={sourceLabel} />
      <ChecklistSection triggers={triggers} />
      <BestOppsSection triggers={triggers} topSessions={topSessions} />
      <CalendarSection events={triggers} />
    </div>
  );
}

function Header({
  apiOnline,
  eventsCount,
  sourceLabel,
}: {
  apiOnline: boolean;
  eventsCount: number | null;
  sourceLabel: string;
}) {
  return (
    <header className="mb-10 space-y-3">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Pré-Londres · 2026-05-04 · 07:42 UTC{" "}
        <span
          aria-label={apiOnline ? "API online" : "API offline"}
          className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
          style={{
            color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
          }}
        >
          <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
          {apiOnline
            ? eventsCount !== null
              ? `live · ${eventsCount} events · ${sourceLabel}`
              : `live · ${sourceLabel}`
            : "offline · mock"}
        </span>
      </p>
      <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
        Aujourd&apos;hui
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Checklist pré-session, top 3 opportunités ranked par conviction × régime fit × confluence,
        et calendrier d&apos;events sur la fenêtre H-4h → H+1h des sessions Londres et NY.
      </p>
    </header>
  );
}

function LiveSessionCard({
  session,
  triggers,
}: {
  session: TodaySessionPreview;
  triggers: Trigger[];
}) {
  // Map backend session-preview shape to the SessionCard component contract.
  // Missing typed fields fall back to neutral / sensible defaults so the
  // card stays dense even when claude_raw_response hasn't been populated
  // (older runs / cold-start). The real data wins as soon as the runner
  // emits the typed sub-objects.
  const display = session.asset.replace("_", "/");
  const tp = session.trade_plan;
  const ideas = session.ideas;
  const drivers = session.confluence_drivers;
  const confluenceScore = drivers
    ? Math.max(0, Math.min(10, 5 + drivers.reduce((s, d) => s + d.contribution * 5, 0)))
    : 5.0;
  return (
    <SessionCard
      asset={display}
      session="london"
      timestamp={session.generated_at}
      conviction={{
        bias:
          session.bias_direction === "long"
            ? "bull"
            : session.bias_direction === "short"
              ? "bear"
              : "neutral",
        value: Math.round(session.conviction_pct),
      }}
      magnitude={{
        low: Math.round(session.magnitude_pips_low ?? 0),
        high: Math.round(session.magnitude_pips_high ?? 0),
        unit: "pips",
      }}
      thesis={
        session.thesis ??
        `Card ${display} · ${session.bias_direction} ${Math.round(session.conviction_pct)} % — détail dans /sessions/${session.asset.toLowerCase()}.`
      }
      triggers={triggers}
      invalidation={{
        level: tp?.invalidation_level ?? 0,
        condition: tp?.invalidation_condition ?? "voir card détail",
      }}
      crossAsset={[]}
      ideas={
        ideas
          ? { top: ideas.top, supporting: ideas.supporting, risks: ideas.risks }
          : { top: "Voir card détail", supporting: [], risks: [] }
      }
      confluence={{
        score: Math.round(confluenceScore * 10) / 10,
        drivers: drivers
          ? drivers.map((d) => ({ factor: d.factor, contribution: d.contribution }))
          : [],
      }}
      calibration={{ brier: 0, sampleSize: 0, trend: "neutral" }}
      trade={
        tp
          ? {
              entryLow: tp.entry_low,
              entryHigh: tp.entry_high,
              invalidationLevel: tp.invalidation_level,
              invalidationCondition: tp.invalidation_condition,
              tpRR3: tp.tp_rr3,
              tpRR15: tp.tp_rr15 ?? tp.tp_rr3 * 1.4,
              partialScheme: tp.partial_scheme,
            }
          : {
              entryLow: 0,
              entryHigh: 0,
              invalidationLevel: 0,
              invalidationCondition: "voir card détail",
              tpRR3: 0,
              tpRR15: 0,
              partialScheme: "—",
            }
      }
    />
  );
}

function ChecklistSection({ triggers }: { triggers: Trigger[] }) {
  // The catalyst-surprise question is auto-flagged based on the live
  // calendar : if a high-impact event lands in the next 2h, downgrade to
  // "caution" with a derived detail line ; else "go".
  const now = Date.now();
  const next2h = triggers.filter((t) => {
    const ts = new Date(t.scheduledAt).getTime();
    return t.importance === "high" && ts >= now && ts - now < 2 * 3600 * 1000;
  });
  const calendarItem: ChecklistItem =
    next2h.length > 0
      ? {
          id: "calendar",
          question: "Pas de catalyst surprise ?",
          status: "caution",
          detail: `${next2h.length} high-impact event${next2h.length > 1 ? "s" : ""} dans les 2h : ${next2h
            .map((t) => t.label)
            .slice(0, 2)
            .join(" · ")}`,
        }
      : {
          id: "calendar",
          question: "Pas de catalyst surprise ?",
          status: "go",
          detail: "Pas de high-impact event dans les 2h prochaines",
        };
  const checklist: ChecklistItem[] = CHECKLIST.map((c) => (c.id === "calendar" ? calendarItem : c));
  const goCount = checklist.filter((c) => c.status === "go").length;
  const verdict = goCount >= 4 ? "GO" : goCount >= 3 ? "GO conditional" : "NO-GO";
  const verdictBias = goCount >= 4 ? "bull" : goCount >= 3 ? "neutral" : "bear";

  return (
    <section className="mb-16 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-md)]">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Checklist pré-session · 5 questions
        </h2>
        <span
          className="font-mono text-sm uppercase tracking-widest"
          style={{
            color:
              verdictBias === "bull"
                ? "var(--color-bull)"
                : verdictBias === "bear"
                  ? "var(--color-bear)"
                  : "var(--color-warn)",
          }}
        >
          {verdict} · {goCount}/{checklist.length}
        </span>
      </div>
      <ol className="space-y-3">
        {checklist.map((c, i) => (
          <li
            key={c.id}
            className="flex items-start gap-3 border-l-2 border-[var(--color-border-default)] pl-3"
            style={{
              borderColor:
                c.status === "go"
                  ? "var(--color-bull)"
                  : c.status === "caution"
                    ? "var(--color-warn)"
                    : "var(--color-bear)",
            }}
          >
            <span className="font-mono text-xs text-[var(--color-text-muted)]">{i + 1}.</span>
            <div className="flex-1">
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                {c.question} <StatusBadge status={c.status} />
              </p>
              <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{c.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StatusBadge({ status }: { status: ChecklistItem["status"] }) {
  const map = {
    go: { label: "GO", glyph: "▲", color: "var(--color-bull)" },
    caution: { label: "PRUDENCE", glyph: "━", color: "var(--color-warn)" },
    no_go: { label: "NO-GO", glyph: "▼", color: "var(--color-bear)" },
  } as const;
  const m = map[status];
  return (
    <span
      role="status"
      aria-label={`Status: ${m.label}`}
      className="ml-2 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest"
      style={{ color: m.color }}
    >
      <span aria-hidden="true">{m.glyph}</span>
      {m.label}
    </span>
  );
}

function BestOppsSection({
  triggers,
  topSessions,
}: {
  triggers: Trigger[];
  topSessions: TodaySessionPreview[] | null;
}) {
  const cardTriggers = triggers.slice(0, 3);
  const hasLive = topSessions !== null && topSessions.length > 0;

  return (
    <section className="mb-16 space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Top {hasLive ? topSessions.length : 3} opportunities · ranked
        </h2>
        <p className="text-xs text-[var(--color-text-muted)]">
          Score{" "}
          <MetricTooltip
            term="conviction × régime fit × confluence"
            title="Best-opp score"
            definition="Multiplie 3 scalaires en [0,1]: conviction du Pass-2 asset, régime fit (corrobore le quadrant macro courant), score de confluence (poids du factor mix). Range [0, 1]."
            glossaryAnchor="best-opp-score"
            density="compact"
          >
            (conviction × régime fit × confluence)
          </MetricTooltip>
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {hasLive ? (
          topSessions.map((s) => (
            <LiveSessionCard
              key={`${s.asset}-${s.generated_at}`}
              session={s}
              triggers={cardTriggers}
            />
          ))
        ) : (
          <SessionCard
            asset="EUR/USD"
            session="london"
            timestamp={NOW}
            conviction={{ bias: "bull", value: 72 }}
            magnitude={{ low: 18, high: 32, unit: "pips" }}
            thesis="EUR support 1.0820 + ECB hawkish bias 8h30 + DXY weakness post-PCE faible. Long sur retest 1.0850–1.0860 H1."
            triggers={cardTriggers}
            invalidation={{ level: 1.082, condition: "close H1 sous low Asian" }}
            crossAsset={[
              { symbol: "DXY", bias: "bear", value: 0.32 },
              { symbol: "US10Y", bias: "bull", value: 4.18 },
              { symbol: "VIX", bias: "neutral", value: 0.04 },
              { symbol: "XAU", bias: "bull", value: 1.21 },
              { symbol: "BRENT", bias: "bear", value: 0.55 },
              { symbol: "SPX", bias: "bull", value: 0.42 },
            ]}
            ideas={{
              top: "Long zone 1.0850–1.0860 retest",
              supporting: ["DXY breakdown 105.20", "Real yield diff favorable"],
              risks: ["Surprise dovish Lagarde", "US10Y >4.30 squeeze"],
            }}
            confluence={{
              score: 7.2,
              drivers: [
                { factor: "DXY directional alignment", contribution: 0.28 },
                { factor: "Real yields differential", contribution: 0.22 },
                { factor: "Polymarket Fed-cut shift", contribution: 0.15 },
                { factor: "Asian range expansion", contribution: 0.09 },
                { factor: "GDELT sentiment EU", contribution: -0.06 },
              ],
            }}
            calibration={{ brier: 0.142, sampleSize: 87, trend: "bull" }}
            trade={{
              entryLow: 1.085,
              entryHigh: 1.086,
              invalidationLevel: 1.082,
              invalidationCondition: "close H1",
              tpRR3: 1.094,
              tpRR15: 1.13,
              partialScheme: "90 % @ RR3 · trail 10 % vers RR15+",
            }}
          />
        )}
      </div>

      {!hasLive ? (
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          Seed data — la section affiche le top 3 réel dès que{" "}
          <code className="font-mono">/v1/today</code> renvoie au moins une session card.
        </p>
      ) : null}
    </section>
  );
}

function CalendarSection({ events }: { events: Trigger[] }) {
  return (
    <section>
      <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Calendrier · fenêtre H-4h → H+1h sessions
      </h2>
      <ol className="space-y-2">
        {events.map((e) => {
          const date = new Date(e.scheduledAt);
          const time = date.toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
          });
          return (
            <li
              key={e.id}
              className="flex items-baseline gap-3 rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)] px-3 py-2"
            >
              <span className="font-mono text-sm tabular-nums text-[var(--color-text-primary)]">
                {time}
              </span>
              <span className="text-sm text-[var(--color-text-secondary)]">{e.label}</span>
              {e.importance === "high" && (
                <span
                  aria-hidden="true"
                  className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-warn)]"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-warn)]" />
                  high impact
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
