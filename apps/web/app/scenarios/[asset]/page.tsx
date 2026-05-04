import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiError,
  getConfluence,
  getDataPool,
  getTradePlan,
  getUpcomingCalendar,
  type CalendarUpcoming,
  type Confluence,
  type DataPoolResponse,
  type TradePlan,
} from "../../../lib/api";
import { findAsset, isValidAssetCode } from "../../../lib/assets";

export const dynamic = "force-dynamic";
export const revalidate = 30;

type SessionType =
  | "pre_londres"
  | "pre_ny"
  | "ny_mid"
  | "ny_close"
  | "event_driven";

const VALID_SESSIONS: ReadonlyArray<readonly [SessionType, string]> = [
  ["pre_londres", "Pré-Londres"],
  ["pre_ny", "Pré-NY"],
  ["ny_mid", "NY mid"],
  ["ny_close", "NY close"],
  ["event_driven", "Event driven"],
] as const;

const VALID_REGIMES = [
  "haven_bid",
  "funding_stress",
  "goldilocks",
  "usd_complacency",
] as const;
type Regime = (typeof VALID_REGIMES)[number];

export async function generateMetadata({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  return { title: `Scénarios · ${asset.replace(/_/g, "/")}` };
}

interface SearchParams {
  session_type?: string;
  regime?: string;
  conviction?: string;
}

function pickSessionType(raw: string | undefined): SessionType {
  const found = VALID_SESSIONS.find(([code]) => code === raw);
  return found ? found[0] : "pre_londres";
}

function pickRegime(raw: string | undefined): Regime | undefined {
  return VALID_REGIMES.find((r) => r === raw);
}

function parseConviction(raw: string | undefined): number {
  if (!raw) return 50;
  const n = Number(raw);
  if (!Number.isFinite(n)) return 50;
  return Math.max(0, Math.min(100, n));
}

/** Pulls the rendered "Session scenarios" markdown block out of the full pool. */
function extractSection(markdown: string, heading: string): string | null {
  const start = markdown.indexOf(`## ${heading}`);
  if (start < 0) return null;
  // Stop at the next "## " heading
  const tail = markdown.slice(start + 1);
  const next = tail.indexOf("\n## ");
  return next < 0
    ? markdown.slice(start)
    : markdown.slice(start, start + 1 + next);
}

function parseScenarios(
  pool: DataPoolResponse,
): { cont: number; rev: number; side: number; rationale: string } | null {
  const md = extractSection(pool.markdown, "Session scenarios");
  if (!md) return null;
  // Lines look like: `- Continuation : **41%** · Reversal : **27%** · Sideways : **32%**`
  const m = md.match(
    /Continuation\s*:\s*\*\*(\d+)%\*\*.*Reversal\s*:\s*\*\*(\d+)%\*\*.*Sideways\s*:\s*\*\*(\d+)%\*\*/,
  );
  if (!m) return null;
  const rationaleMatch = md.match(/Rationale\s*:\s*(.+)/);
  return {
    cont: Number(m[1]),
    rev: Number(m[2]),
    side: Number(m[3]),
    rationale: rationaleMatch?.[1]?.trim() ?? "",
  };
}

function parseTriggers(
  pool: DataPoolResponse,
  kind: "continuation" | "reversal",
): string[] {
  const md = extractSection(pool.markdown, "Session scenarios");
  if (!md) return [];
  const heading =
    kind === "continuation"
      ? "Triggers continuation :"
      : "Triggers reversal :";
  const idx = md.indexOf(heading);
  if (idx < 0) return [];
  const tail = md.slice(idx + heading.length);
  // Next "- " at top-level closes the block
  const lines = tail.split("\n");
  const out: string[] = [];
  for (const ln of lines.slice(1)) {
    if (ln.startsWith("  · ")) {
      out.push(ln.slice(4).trim());
    } else if (ln.startsWith("- ")) {
      break;
    }
  }
  return out;
}

function extractDailyLevels(
  pool: DataPoolResponse,
): Record<string, string> | null {
  const md = extractSection(pool.markdown, "Daily levels");
  if (!md) return null;
  const out: Record<string, string> = {};
  const patterns: ReadonlyArray<readonly [string, RegExp]> = [
    ["Spot", /Spot\s*=\s*([\d.]+)/],
    ["PDH/PDL", /Previous day H\/L\s*=\s*([\d.]+)\s*\/\s*([\d.]+)/],
    ["PD close", /close\s*([\d.]+)\)/],
    ["Asian H/L", /Asian range H\/L\s*=\s*([\d.]+)\s*\/\s*([\d.]+)/],
    ["Weekly H/L", /Weekly H\/L \(7d\)\s*=\s*([\d.]+)\s*\/\s*([\d.]+)/],
    ["Pivot", /Pivots PP \/ R1-R3 \/ S1-S3\s*=\s*([\d.]+)/],
  ] as const;
  for (const [k, re] of patterns) {
    const m = md.match(re);
    if (m && m[1]) {
      out[k] = m.length > 2 && m[2] ? `${m[1]} / ${m[2]}` : m[1];
    }
  }
  return Object.keys(out).length > 0 ? out : null;
}

export default async function ScenariosPage({
  params,
  searchParams,
}: {
  params: Promise<{ asset: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { asset } = await params;
  if (!isValidAssetCode(asset)) notFound();
  const meta = findAsset(asset);

  const sp = await searchParams;
  const sessionType = pickSessionType(sp.session_type);
  const regime = pickRegime(sp.regime);
  const conviction = parseConviction(sp.conviction);

  let pool: DataPoolResponse | null = null;
  let plan: TradePlan | null = null;
  let confluence: Confluence | null = null;
  let calendar: CalendarUpcoming | null = null;
  let error: string | null = null;
  try {
    const dataPoolOpts: Parameters<typeof getDataPool>[1] = {
      session_type: sessionType,
      conviction_pct: conviction,
    };
    if (regime) dataPoolOpts.regime = regime;
    const [poolR, planR, confR, calR] = await Promise.allSettled([
      getDataPool(asset, dataPoolOpts),
      getTradePlan(asset, 3.0),
      getConfluence(asset),
      getUpcomingCalendar({ horizonDays: 14, asset }),
    ]);
    if (poolR.status === "fulfilled") pool = poolR.value;
    if (planR.status === "fulfilled") plan = planR.value;
    if (confR.status === "fulfilled") confluence = confR.value;
    if (calR.status === "fulfilled") calendar = calR.value;
    if (poolR.status === "rejected") {
      const r = poolR.reason;
      error =
        r instanceof ApiError
          ? r.message
          : r instanceof Error
            ? r.message
            : "unknown error";
    }
  } catch (e) {
    error =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "unknown error";
  }

  const scenarios = pool ? parseScenarios(pool) : null;
  const continuationTriggers = pool ? parseTriggers(pool, "continuation") : [];
  const reversalTriggers = pool ? parseTriggers(pool, "reversal") : [];
  const dailyLevels = pool ? extractDailyLevels(pool) : null;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <nav aria-label="Fil d'Ariane" className="text-xs text-[var(--color-ichor-text-subtle)] mb-4">
        <Link href="/" className="hover:text-[var(--color-ichor-text-muted)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link
          href={`/sessions/${asset}`}
          className="hover:text-[var(--color-ichor-text-muted)] underline"
        >
          Sessions
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-ichor-text-muted)]">
          Scénarios — {meta?.display ?? asset}
        </span>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
          Scénarios de session — {meta?.display ?? asset}
        </h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1">
          SMC framework : Continuation / Reversal / Sideways pour la fenêtre
          de session sélectionnée. Ajusté par le régime macro et la conviction.
        </p>
      </header>

      {/* Filter form (server-rendered) */}
      <form
        method="GET"
        className="mb-6 flex flex-wrap items-end gap-3 rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-3"
      >
        <div className="flex flex-col">
          <label
            htmlFor="session_type"
            className="text-[11px] uppercase tracking-wide text-[var(--color-ichor-text-muted)]"
          >
            Session
          </label>
          <select
            id="session_type"
            name="session_type"
            defaultValue={sessionType}
            className="mt-1 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] px-2 py-1 text-sm text-[var(--color-ichor-text)]"
          >
            {VALID_SESSIONS.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col">
          <label
            htmlFor="regime"
            className="text-[11px] uppercase tracking-wide text-[var(--color-ichor-text-muted)]"
          >
            Régime
          </label>
          <select
            id="regime"
            name="regime"
            defaultValue={regime ?? ""}
            className="mt-1 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] px-2 py-1 text-sm text-[var(--color-ichor-text)]"
          >
            <option value="">(auto / inconnu)</option>
            {VALID_REGIMES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col">
          <label
            htmlFor="conviction"
            className="text-[11px] uppercase tracking-wide text-[var(--color-ichor-text-muted)]"
          >
            Conviction (%)
          </label>
          <input
            id="conviction"
            name="conviction"
            type="number"
            min={0}
            max={100}
            step={5}
            defaultValue={conviction}
            className="mt-1 w-24 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] px-2 py-1 text-sm text-[var(--color-ichor-text)]"
          />
        </div>
        <button
          type="submit"
          className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-emerald-50 hover:bg-emerald-600"
        >
          Recalculer
        </button>
      </form>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200 mb-4"
        >
          Impossible de charger : {error}
        </div>
      ) : null}

      {/* Scenarios grid */}
      <section
        aria-labelledby="scenarios-heading"
        className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6"
      >
        <h2
          id="scenarios-heading"
          className="text-lg font-semibold text-[var(--color-ichor-text)] mb-4"
        >
          Probabilités de scénario
        </h2>
        {scenarios ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <ScenarioBar
              label="Continuation"
              pct={scenarios.cont}
              color="emerald"
            />
            <ScenarioBar
              label="Reversal"
              pct={scenarios.rev}
              color="rose"
            />
            <ScenarioBar
              label="Sideways"
              pct={scenarios.side}
              color="amber"
            />
          </div>
        ) : (
          <p className="text-sm text-[var(--color-ichor-text-subtle)]">
            Données insuffisantes (PDH/PDL manquants) — re-essayer après
            ingestion polygon.
          </p>
        )}
        {scenarios?.rationale ? (
          <p className="text-xs text-[var(--color-ichor-text-muted)] mt-4">
            {scenarios.rationale}
          </p>
        ) : null}
      </section>

      {/* Triggers */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TriggerList
          title="Triggers · Continuation"
          tone="emerald"
          items={continuationTriggers}
        />
        <TriggerList
          title="Triggers · Reversal"
          tone="rose"
          items={reversalTriggers}
        />
      </section>

      {/* Confluence engine */}
      <ConfluenceCard confluence={confluence} />

      {/* Economic calendar */}
      <CalendarCard calendar={calendar} />

      {/* Daily levels */}
      {dailyLevels ? (
        <section
          aria-labelledby="levels-heading"
          className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6"
        >
          <h2
            id="levels-heading"
            className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3"
          >
            Niveaux journaliers (SMC toolbox)
          </h2>
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-sm">
            {Object.entries(dailyLevels).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs uppercase tracking-wide text-[var(--color-ichor-text-subtle)]">
                  {k}
                </dt>
                <dd className="font-mono text-[var(--color-ichor-text)]">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {/* Trade plan */}
      <TradePlanCard plan={plan} />
    </div>
  );
}

// ─────────────────────────── components ───────────────────────────

function ScenarioBar({
  label,
  pct,
  color,
}: {
  label: string;
  pct: number;
  color: "emerald" | "rose" | "amber";
}) {
  const colorMap: Record<typeof color, { bar: string; text: string }> = {
    emerald: { bar: "bg-emerald-500", text: "ichor-text-long" },
    rose: { bar: "bg-rose-500", text: "ichor-text-short" },
    amber: { bar: "bg-amber-500", text: "text-amber-300" },
  };
  const styles = colorMap[color];
  return (
    <div className="rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)] p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wide text-[var(--color-ichor-text-muted)]">
          {label}
        </span>
        <span className={`text-xl font-semibold ${styles.text}`}>{pct}%</span>
      </div>
      <div className="mt-2 h-2 rounded bg-[var(--color-ichor-surface-2)] overflow-hidden">
        <div
          className={`h-full ${styles.bar}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}

function TriggerList({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "emerald" | "rose";
  items: string[];
}) {
  const borderClass =
    tone === "emerald" ? "border-emerald-800/50" : "border-rose-800/50";
  return (
    <div
      className={`rounded-lg border ${borderClass} bg-[var(--color-ichor-surface)]/60 p-4`}
    >
      <h3 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-[var(--color-ichor-text-subtle)]">Aucun trigger calculé.</p>
      ) : (
        <ul className="text-xs text-[var(--color-ichor-text)] space-y-1.5">
          {items.map((it, i) => (
            <li key={i} className="leading-snug">
              {it}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TradePlanCard({ plan }: { plan: TradePlan | null }) {
  if (!plan) {
    return (
      <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5">
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-2">
          Plan RR
        </h2>
        <p className="text-sm text-[var(--color-ichor-text-subtle)]">
          Pas de plan disponible (API trade-plan indisponible).
        </p>
      </section>
    );
  }
  if (plan.bias === "neutral" || plan.entry_zone_low == null) {
    return (
      <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5">
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-2">
          Plan RR — bias neutre
        </h2>
        <p className="text-sm text-[var(--color-ichor-text-muted)]">
          Pas de plan d&apos;entrée pour le moment — soit aucune carte
          n&apos;a encore été générée, soit le verdict est neutre. Lancer un{" "}
          <code className="ichor-text-long">--live</code> pour rafraîchir.
        </p>
      </section>
    );
  }
  const biasLabel = plan.bias === "long" ? "LONG" : "SHORT";
  const biasClass =
    plan.bias === "long"
      ? "ichor-text-long border-emerald-700/50"
      : "ichor-text-short border-rose-700/50";

  return (
    <section
      aria-labelledby="rr-heading"
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <h2 id="rr-heading" className="text-lg font-semibold text-[var(--color-ichor-text)]">
          Plan RR (target {plan.rr_target.toFixed(0)})
        </h2>
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-xs font-mono uppercase ${biasClass}`}
        >
          {biasLabel} · {plan.conviction_pct.toFixed(0)}% conviction
        </span>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-sm">
        <PlanLine
          label="Entry zone"
          value={`${fmt(plan.entry_zone_low)} → ${fmt(plan.entry_zone_high)}`}
        />
        <PlanLine
          label="Stop loss"
          value={fmt(plan.stop_loss)}
          tone="rose"
          subline={
            plan.risk_pips != null ? `${plan.risk_pips.toFixed(0)} pips` : null
          }
        />
        <PlanLine
          label="TP1 (BE)"
          value={fmt(plan.tp1)}
          tone="amber"
          subline="RR=1"
        />
        <PlanLine
          label="TP3 (90%)"
          value={fmt(plan.tp3)}
          tone="emerald"
          subline={
            plan.reward_pips_tp3 != null
              ? `RR=${plan.rr_target.toFixed(0)} · ${plan.reward_pips_tp3.toFixed(0)} pips`
              : null
          }
        />
        <PlanLine
          label="TP étendu (10%)"
          value={fmt(plan.tp_extended)}
          tone="emerald"
          subline="trail"
        />
        <PlanLine label="Spot" value={fmt(plan.spot)} />
      </div>

      {plan.notes ? (
        <p className="mt-4 rounded border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-xs text-amber-100">
          ⚠ {plan.notes}
        </p>
      ) : null}
    </section>
  );
}

function PlanLine({
  label,
  value,
  tone,
  subline,
}: {
  label: string;
  value: string;
  tone?: "emerald" | "amber" | "rose";
  subline?: string | null;
}) {
  const valueClass =
    tone === "emerald"
      ? "ichor-text-long"
      : tone === "amber"
        ? "text-amber-300"
        : tone === "rose"
          ? "ichor-text-short"
          : "text-[var(--color-ichor-text)]";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-[var(--color-ichor-text-subtle)]">
        {label}
      </div>
      <div className={`font-mono ${valueClass}`}>{value}</div>
      {subline ? (
        <div className="text-[10px] text-[var(--color-ichor-text-subtle)]">{subline}</div>
      ) : null}
    </div>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "n/a";
  // Trim trailing zeros: 1.07340 → 1.0734
  return n.toFixed(5).replace(/\.?0+$/, (s) => (s.startsWith(".") ? "" : s));
}

function ConfluenceCard({ confluence }: { confluence: Confluence | null }) {
  if (!confluence) {
    return (
      <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6">
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-2">
          Confluence engine
        </h2>
        <p className="text-sm text-[var(--color-ichor-text-subtle)]">
          Indisponible (endpoint /v1/confluence non joignable).
        </p>
      </section>
    );
  }
  const dom = confluence.dominant_direction;
  const domClass =
    dom === "long"
      ? "ichor-text-long border-emerald-700/50"
      : dom === "short"
        ? "ichor-text-short border-rose-700/50"
        : "text-[var(--color-ichor-text-muted)] border-[var(--color-ichor-border-strong)]/50";
  return (
    <section
      aria-labelledby="confluence-heading"
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <h2
          id="confluence-heading"
          className="text-lg font-semibold text-[var(--color-ichor-text)]"
        >
          Confluence engine — {confluence.drivers.length} drivers
        </h2>
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-xs font-mono uppercase ${domClass}`}
        >
          {dom} · {confluence.confluence_count} confluences
        </span>
      </header>

      <div className="grid grid-cols-3 gap-3 mb-5">
        <ScenarioBar label="Score LONG" pct={confluence.score_long} color="emerald" />
        <ScenarioBar label="Score SHORT" pct={confluence.score_short} color="rose" />
        <ScenarioBar label="Neutre" pct={confluence.score_neutral} color="amber" />
      </div>

      {confluence.drivers.length === 0 ? (
        <p className="text-xs text-[var(--color-ichor-text-subtle)]">
          Aucun driver disponible — données insuffisantes.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {confluence.drivers.map((d, i) => {
            const sign = d.contribution >= 0 ? "+" : "";
            const tone =
              d.contribution > 0.2
                ? "ichor-text-long"
                : d.contribution < -0.2
                  ? "ichor-text-short"
                  : "text-[var(--color-ichor-text-muted)]";
            return (
              <li
                key={i}
                className="rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)] p-2.5"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-xs uppercase text-[var(--color-ichor-text-muted)]">
                    {d.factor}
                  </span>
                  <span className={`font-mono text-sm ${tone}`}>
                    {sign}
                    {d.contribution.toFixed(2)}
                  </span>
                </div>
                <p className="text-xs text-[var(--color-ichor-text-muted)] mt-1 leading-snug">
                  {d.evidence}
                </p>
                {d.source ? (
                  <p className="text-[10px] text-[var(--color-ichor-text-subtle)] mt-0.5 font-mono">
                    {d.source}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function CalendarCard({ calendar }: { calendar: CalendarUpcoming | null }) {
  if (!calendar || calendar.events.length === 0) {
    return (
      <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6">
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-2">
          Calendrier économique (14 jours)
        </h2>
        <p className="text-sm text-[var(--color-ichor-text-subtle)]">
          Aucun événement projeté pour cet actif sur la fenêtre.
        </p>
      </section>
    );
  }
  const impactClass: Record<CalendarUpcoming["events"][number]["impact"], string> = {
    high: "ichor-text-short bg-rose-900/30 border-rose-800/50",
    medium: "text-amber-300 bg-amber-900/30 border-amber-800/50",
    low: "text-[var(--color-ichor-text-muted)] bg-[var(--color-ichor-surface)]/60 border-[var(--color-ichor-border-strong)]/40",
  };
  return (
    <section
      aria-labelledby="calendar-heading"
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6"
    >
      <h2
        id="calendar-heading"
        className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3"
      >
        Calendrier économique (14 jours)
      </h2>
      <ul className="divide-y divide-[var(--color-ichor-border)] text-sm">
        {calendar.events.slice(0, 10).map((e, i) => (
          <li
            key={`${e.when}-${e.label}-${i}`}
            className="py-2 flex items-baseline gap-3"
          >
            <span className="font-mono text-xs text-[var(--color-ichor-text-muted)] w-28 shrink-0">
              {e.when}
              {e.when_time_utc ? ` ${e.when_time_utc}` : ""}
            </span>
            <span
              className={`text-[10px] uppercase font-mono px-1.5 py-0.5 border rounded ${impactClass[e.impact]}`}
            >
              {e.impact}
            </span>
            <span className="text-xs text-[var(--color-ichor-text-muted)] w-12 shrink-0">
              [{e.region}]
            </span>
            <span className="text-[var(--color-ichor-text)] leading-snug">{e.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
