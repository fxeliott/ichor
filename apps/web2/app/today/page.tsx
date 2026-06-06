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
import { biasFr, impactFr } from "@/lib/coachLabels";
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

// Plain-FR coach labels for the macro risk-appetite band (mirror of the SSOT
// in app/briefing/page.tsx — the backend RiskBand domain).
const RISK_BAND_FR: Record<string, string> = {
  extreme_risk_on: "Fort appétit pour le risque",
  risk_on: "Appétit pour le risque",
  neutral: "Régime neutre",
  risk_off: "Aversion au risque",
  extreme_risk_off: "Forte aversion au risque",
};

/**
 * Derive the pre-session checklist from REAL data (the /v1/today bundle + the
 * live calendar) instead of the previously hardcoded fake answers
 * ("EUR/USD long 72%", "Lagarde 8h30", "Fed-cut +1pp") that contradicted
 * reality (e.g. claimed conviction > 60 % while the real top read was ~25 %).
 * Each line is now traceable to a live value or honestly flagged as
 * unavailable — never fabricated. Items whose data the bundle does not carry
 * (per-asset confluence detail / Polymarket) are intentionally omitted rather
 * than faked.
 */
function buildChecklist(
  bundle: TodaySnapshotOut | null,
  realTriggers: Trigger[],
  apiOnline: boolean,
): ChecklistItem[] {
  const items: ChecklistItem[] = [];
  const sessions = bundle?.top_sessions ?? [];

  // 1. Régime — real macro risk band + VIX regime.
  if (bundle) {
    const band = bundle.macro.risk_band;
    items.push({
      id: "regime",
      question: "Régime de marché lisible ?",
      status: band !== "neutral" ? "go" : "caution",
      detail:
        `${RISK_BAND_FR[band] ?? band} (composite ${bundle.macro.risk_composite.toFixed(2)})` +
        (bundle.macro.vix_1m !== null
          ? ` · VIX ${bundle.macro.vix_1m.toFixed(1)} (${bundle.macro.vix_regime})`
          : ""),
    });
  } else {
    items.push({
      id: "regime",
      question: "Régime de marché lisible ?",
      status: "caution",
      detail: "Pouls macro indisponible pour le moment.",
    });
  }

  // 2. Conviction — real top_sessions strongest conviction vs the 60 % bar.
  if (sessions.length > 0) {
    const top = sessions.reduce((a, b) => (b.conviction_pct > a.conviction_pct ? b : a));
    const maxConv = Math.round(top.conviction_pct);
    items.push({
      id: "conviction",
      question: "Conviction ≥ 60 % sur ≥ 1 actif ?",
      status: maxConv >= 60 ? "go" : maxConv >= 45 ? "caution" : "no_go",
      detail: `Conviction la plus forte : ${maxConv} % (${top.asset.replace("_", "/")} ${biasFr(
        top.bias_direction,
      )}) — ${maxConv >= 60 ? "au-dessus" : "en-dessous"} du seuil de 60 %.`,
    });
  } else {
    items.push({
      id: "conviction",
      question: "Conviction ≥ 60 % sur ≥ 1 actif ?",
      status: "caution",
      detail: "Aucune carte de session disponible pour le moment.",
    });
  }

  // 3. Direction — at least one non-neutral bias among the real top reads.
  if (sessions.length > 0) {
    const directional = sessions.filter((s) => s.bias_direction !== "neutral");
    items.push({
      id: "direction",
      question: "Au moins un biais directionnel net ?",
      status: directional.length >= 1 ? "go" : "caution",
      detail:
        directional.length > 0
          ? `${directional.length} actif${directional.length > 1 ? "s" : ""} directionnel${
              directional.length > 1 ? "s" : ""
            } : ${directional
              .map((s) => `${s.asset.replace("_", "/")} ${biasFr(s.bias_direction)}`)
              .join(" · ")}`
          : "Tous les biais sont neutres — pas de direction tranchée aujourd'hui.",
    });
  }

  // 4. Catalyst surprise — live calendar (real events only, next 2 h high-impact).
  if (!apiOnline) {
    items.push({
      id: "calendar",
      question: "Pas de catalyst surprise ?",
      status: "caution",
      detail: "Calendrier indisponible — impossible de confirmer l'absence d'événement.",
    });
  } else {
    const now = Date.now();
    const next2h = realTriggers.filter((t) => {
      const ts = new Date(t.scheduledAt).getTime();
      return t.importance === "high" && ts >= now && ts - now < 2 * 3600 * 1000;
    });
    items.push(
      next2h.length > 0
        ? {
            id: "calendar",
            question: "Pas de catalyst surprise ?",
            status: "caution",
            detail: `${next2h.length} événement${next2h.length > 1 ? "s" : ""} à fort impact dans les 2 h : ${next2h
              .map((t) => t.label)
              .slice(0, 2)
              .join(" · ")}`,
          }
        : {
            id: "calendar",
            question: "Pas de catalyst surprise ?",
            status: "go",
            detail: "Pas d'événement à fort impact dans les 2 h prochaines.",
          },
    );
  }

  return items;
}

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
    sourceLabel = "flux du jour";
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
          ? "FRED seul"
          : ffOnline
            ? "ForexFactory seul"
            : "données de démo";
  }

  const apiOnline = bundleOnline || calOnline || ffOnline;
  const triggers: Trigger[] = merged.length > 0 ? merged : MOCK_TRIGGERS;
  const eventsCount = apiOnline ? merged.length : null;
  const topSessions: TodaySessionPreview[] | null = bundleOnline ? bundle.top_sessions : null;
  // Checklist derived from REAL data only — `merged` is the real calendar
  // triggers (possibly empty), never the MOCK_TRIGGERS display fallback.
  const checklist = buildChecklist(bundleOnline ? bundle : null, merged, apiOnline);

  // Honest, per-request Europe/Paris date + time for the header eyebrow —
  // replaces a hardcoded "Pré-Londres · 2026-05-04 · 07:42 UTC" string that
  // lied a fixed stale date to every visitor. Page is revalidate:30, so this
  // refreshes at least twice a minute.
  const renderNow = new Date();
  const dateLabel = renderNow.toLocaleDateString("fr-FR", {
    timeZone: "Europe/Paris",
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
  const timeLabel = renderNow.toLocaleTimeString("fr-FR", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <Header
        apiOnline={apiOnline}
        eventsCount={eventsCount}
        sourceLabel={sourceLabel}
        dateLabel={dateLabel}
        timeLabel={timeLabel}
      />
      <ChecklistSection checklist={checklist} />
      <BestOppsSection triggers={triggers} topSessions={topSessions} />
      <CalendarSection events={triggers} />
    </div>
  );
}

function Header({
  apiOnline,
  eventsCount,
  sourceLabel,
  dateLabel,
  timeLabel,
}: {
  apiOnline: boolean;
  eventsCount: number | null;
  sourceLabel: string;
  dateLabel: string;
  timeLabel: string;
}) {
  return (
    <header className="mb-10 space-y-3">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        {dateLabel} · {timeLabel} Paris{" "}
        <span
          aria-label={apiOnline ? "Données en direct" : "Données hors ligne"}
          className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
          style={{
            color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
          }}
        >
          <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
          {apiOnline
            ? eventsCount !== null
              ? `en direct · ${eventsCount} événements · ${sourceLabel}`
              : `en direct · ${sourceLabel}`
            : "hors ligne · données de démo"}
        </span>
      </p>
      <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
        Aujourd&apos;hui
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Checklist pré-session, top 3 opportunités classées par conviction × adéquation au régime ×
        confluence, et calendrier d&apos;événements sur la fenêtre H-4h → H+1h des sessions Londres
        et NY.
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
        `Carte ${display} · ${biasFr(session.bias_direction)} ${Math.round(session.conviction_pct)} % — détail dans /sessions/${session.asset.toLowerCase()}.`
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
    />
  );
}

function ChecklistSection({ checklist }: { checklist: ChecklistItem[] }) {
  // Verdict derived from the REAL checklist (built upstream from the /v1/today
  // bundle) : any "no_go" (e.g. conviction below the 60 % threshold) blocks the
  // day ; all-go = clear ; otherwise conditional. No fabricated answers.
  const total = checklist.length;
  const goCount = checklist.filter((c) => c.status === "go").length;
  const noGoCount = checklist.filter((c) => c.status === "no_go").length;
  const verdict =
    noGoCount > 0
      ? "À éviter aujourd'hui"
      : goCount === total
        ? "Feu vert"
        : "Feu vert sous conditions";
  const verdictBias = noGoCount > 0 ? "bear" : goCount === total ? "bull" : "neutral";

  return (
    <section className="mb-16 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-md)]">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Checklist pré-session · {total} points
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
    go: { label: "Feu vert", glyph: "▲", color: "var(--color-bull)" },
    caution: { label: "Prudence", glyph: "━", color: "var(--color-warn)" },
    no_go: { label: "À éviter", glyph: "▼", color: "var(--color-bear)" },
  } as const;
  const m = map[status];
  return (
    <span
      role="status"
      aria-label={`Statut : ${m.label}`}
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
          Top {hasLive ? topSessions.length : 3} opportunités · classées
        </h2>
        <p className="text-xs text-[var(--color-text-muted)]">
          Score{" "}
          <MetricTooltip
            term="conviction × adéquation au régime × confluence"
            title="Score des meilleures opportunités"
            definition="Multiplie 3 scalaires entre 0 et 1 : conviction de l'analyse par actif, adéquation au régime (corrobore le quadrant macro courant), score de confluence. Plage [0, 1]."
            glossaryAnchor="best-opp-score"
            density="compact"
          >
            (conviction × adéquation au régime × confluence)
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
            thesis="Support EUR à 1.0820 + ton ECB plutôt restrictif à 8h30 + dollar affaibli après un PCE faible. Zone 1.0850–1.0860 à surveiller en H1."
            triggers={cardTriggers}
            invalidation={{ level: 1.082, condition: "clôture H1 sous le plus bas asiatique" }}
            crossAsset={[
              { symbol: "DXY", bias: "bear", value: 0.32 },
              { symbol: "US10Y", bias: "bull", value: 4.18 },
              { symbol: "VIX", bias: "neutral", value: 0.04 },
              { symbol: "XAU", bias: "bull", value: 1.21 },
              { symbol: "BRENT", bias: "bear", value: 0.55 },
              { symbol: "SPX", bias: "bull", value: 0.42 },
            ]}
            ideas={{
              top: "Zone 1.0850–1.0860 à surveiller (retest H1)",
              supporting: [
                "Cassure du dollar sous 105.20",
                "Écart de taux réels favorable à l'euro",
              ],
              risks: ["Surprise accommodante de Lagarde", "Tension si le 10 ans US dépasse 4,30 %"],
            }}
            confluence={{
              score: 7.2,
              drivers: [
                { factor: "Alignement directionnel du dollar", contribution: 0.28 },
                { factor: "Différentiel de taux réels", contribution: 0.22 },
                { factor: "Bascule Polymarket sur une baisse Fed", contribution: 0.15 },
                { factor: "Expansion du range asiatique", contribution: 0.09 },
                { factor: "Sentiment GDELT zone euro", contribution: -0.06 },
              ],
            }}
            calibration={{ brier: 0.142, sampleSize: 87, trend: "bull" }}
          />
        )}
      </div>

      {!hasLive ? (
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          Données de démonstration — la section affiche le vrai top 3 dès que{" "}
          <code className="font-mono">/v1/today</code> renvoie au moins une carte de session.
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
                  {impactFr(e.importance)} impact
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
