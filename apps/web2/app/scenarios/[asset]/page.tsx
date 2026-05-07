// /scenarios/[asset] — 7 scénarios (mechanism × stress × invalidation matrix)
// + Pass 5 counterfactual trigger.
//
// Cf SPEC.md §5 Phase A item #4 + §6.1 (counterfactual button flow).
//
// Wiring : calls `/v1/sessions/{asset}/scenarios` (Pass 4 typed tree).
// When `n_scenarios > 0` the live tree replaces the static mock. When
// the runner hasn't populated the structured shape yet, falls back to
// the static `SCENARIOS_EUR_USD` seed and surfaces "scenario tree mock"
// in the pill.

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import { MobileGate } from "@/components/ui/mobile-gate";
import {
  apiGet,
  isLive,
  type Pass4ScenarioTree,
  type ScenariosResponse,
  type SessionCardList,
} from "@/lib/api";

interface Scenario {
  id: string;
  label: string;
  probability: number;
  bias: "bull" | "bear" | "neutral";
  magnitude_pips: { low: number; high: number };
  primary_mechanism: string;
  invalidation: string;
  counterfactual_anchor?: string;
}

const SCENARIOS_EUR_USD: Scenario[] = [
  {
    id: "s1",
    label: "ECB hawkish + DXY breakdown",
    probability: 0.32,
    bias: "bull",
    magnitude_pips: { low: 22, high: 38 },
    primary_mechanism: "Lagarde 8h30 confirms restrictive bias + US PCE fade",
    invalidation: "close H1 < 1.0820",
  },
  {
    id: "s2",
    label: "Range étroit Pré-Londres",
    probability: 0.24,
    bias: "neutral",
    magnitude_pips: { low: 5, high: 15 },
    primary_mechanism: "Asian range expansion < 0.4 ATR + low vol calendar",
    invalidation: "breakout > 0.6 ATR",
  },
  {
    id: "s3",
    label: "Squeeze short EUR via UST 10Y > 4.30",
    probability: 0.16,
    bias: "bear",
    magnitude_pips: { low: 18, high: 30 },
    primary_mechanism: "Real yield differential US fastrunning EUR",
    invalidation: "UST 10Y < 4.20",
  },
  {
    id: "s4",
    label: "Lagarde dovish surprise",
    probability: 0.12,
    bias: "bear",
    magnitude_pips: { low: 25, high: 50 },
    primary_mechanism: "Inflation slowdown speech triggers EUR sell",
    invalidation: "rebound 1.0850 H1",
    counterfactual_anchor: "lagarde_dovish",
  },
  {
    id: "s5",
    label: "Geopolitical shock (Mid-East / Russia)",
    probability: 0.08,
    bias: "bear",
    magnitude_pips: { low: 30, high: 80 },
    primary_mechanism: "Risk-off bid USD; gold + JPY co-move",
    invalidation: "VIX < 18 reverts",
    counterfactual_anchor: "geopol_shock",
  },
  {
    id: "s6",
    label: "Fed hawkish reprice (Powell @Brookings)",
    probability: 0.05,
    bias: "bear",
    magnitude_pips: { low: 20, high: 45 },
    primary_mechanism: "OIS reprice +1 hike → DXY rally",
    invalidation: "DXY < 105.0",
    counterfactual_anchor: "powell_hawkish",
  },
  {
    id: "s7",
    label: "Continuation slow drift haut",
    probability: 0.03,
    bias: "bull",
    magnitude_pips: { low: 8, high: 18 },
    primary_mechanism: "No catalyst, technical drift on real-yield path",
    invalidation: "S/R break",
  },
];

interface PageProps {
  params: Promise<{ asset: string }>;
}

export default async function ScenariosPage({ params }: PageProps) {
  const { asset } = await params;
  const slug = asset.toUpperCase().replace("-", "_");
  const display = asset.toUpperCase().replace("_", "/").replace("-", "/");
  // totalProb is recomputed below from whichever source ends up rendering.
  const [history, live3Model, livePass4Tree] = await Promise.all([
    apiGet<SessionCardList>(`/v1/sessions/${slug}?limit=1`, { revalidate: 60 }),
    apiGet<ScenariosResponse>(`/v1/scenarios/${slug}?session_type=pre_londres`, {
      revalidate: 30,
    }),
    apiGet<Pass4ScenarioTree>(`/v1/sessions/${slug}/scenarios`, {
      revalidate: 60,
    }),
  ]);
  const apiOnline = isLive(history) || isLive(live3Model) || isLive(livePass4Tree);
  const cardsCount = isLive(history) ? history.total : null;
  const pass4Live = isLive(livePass4Tree) && livePass4Tree.n_scenarios > 0;
  // Use the live Pass 4 tree when populated, else the asset-specific mock.
  const renderedScenarios: Scenario[] = pass4Live
    ? livePass4Tree.scenarios.map((s) => {
        const base: Scenario = {
          id: s.id,
          label: s.label,
          probability: s.probability,
          bias: s.bias,
          magnitude_pips: { low: s.magnitude_pips.low, high: s.magnitude_pips.high },
          primary_mechanism: s.primary_mechanism,
          invalidation: s.invalidation,
        };
        return s.counterfactual_anchor !== null
          ? { ...base, counterfactual_anchor: s.counterfactual_anchor }
          : base;
      })
    : SCENARIOS_EUR_USD;
  const totalProb = renderedScenarios.reduce((s, sc) => s + sc.probability, 0);

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <MobileGate feature="le comparateur de scénarios 3-pannes" />
      <header className="mb-8 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Scénarios · arbre probabiliste{" "}
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
                ? pass4Live
                  ? cardsCount !== null
                    ? `live · ${cardsCount} cards · Pass 4 tree`
                    : "live · Pass 4 tree"
                  : cardsCount !== null
                    ? `live · ${cardsCount} cards · scenario tree mock`
                    : "live · scenario tree mock"
                : "offline · mock"}
            </span>
          </p>
          <h1 className="mt-1 flex items-baseline gap-3 text-4xl tracking-tight text-[var(--color-text-primary)]">
            <span className="font-mono">{display}</span>
            <span className="font-mono text-sm uppercase tracking-widest text-[var(--color-text-muted)]">
              7 scénarios · Pré-Londres
            </span>
          </h1>
        </div>
        <CounterfactualButton />
      </header>

      <p className="mb-6 max-w-prose text-sm text-[var(--color-text-secondary)]">
        Le pipeline brain Pass 4 énumère 7 scénarios mutuellement exclusifs + leurs probabilités
        calibrées (somme ≈ 100%). Pass 5 (counterfactual) permet d&apos;injecter un scénario {""}
        <MetricTooltip
          term="anchor"
          definition="Hypothèse alternative à tester : un scénario faiblement probable mais à fort impact (queue de distribution)."
          glossaryAnchor="counterfactual-anchor"
          density="compact"
        >
          anchor
        </MetricTooltip>{" "}
        et de générer une lecture sous cette hypothèse.
      </p>

      {isLive(live3Model) && <Live3ScenarioModel data={live3Model} />}

      <ScenarioBars scenarios={SCENARIOS_EUR_USD} totalProb={totalProb} />

      <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {SCENARIOS_EUR_USD.map((s) => (
          <ScenarioCard key={s.id} scenario={s} />
        ))}
      </div>

      <p className="mt-8 text-xs text-[var(--color-text-muted)]">
        Probabilités calibrées par Pass 4 · invalidation = condition qui élimine le scénario. Si
        Pass 4 produit moins de 7 scénarios significatifs, un placeholder « low-probability tail »
        est ajouté pour somme ≈ 100%.
      </p>
    </div>
  );
}

function Live3ScenarioModel({ data }: { data: ScenariosResponse }) {
  const KIND_META: Record<
    ScenariosResponse["scenarios"][number]["kind"],
    { label: string; color: string }
  > = {
    continuation: { label: "Continuation", color: "var(--color-bull)" },
    reversal: { label: "Reversal", color: "var(--color-bear)" },
    sideways: { label: "Sideways", color: "var(--color-neutral)" },
  };
  return (
    <section
      aria-label="Live 3-scenario empirical model"
      className="mb-8 rounded-xl border border-[var(--color-bull)]/30 bg-[var(--color-bull)]/5 p-6"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-bull)]">
          ▲ Live · 3-scenario model · session {data.session_type}
        </p>
        <p className="font-mono text-[10px] text-[var(--color-text-muted)]">
          regime {data.regime ?? "—"} · conviction {data.conviction_pct.toFixed(0)}%
          {data.sources.includes("latest_session_card") && " · ← latest card"}
        </p>
      </header>
      <div className="mb-3 flex h-7 w-full overflow-hidden rounded">
        {data.scenarios.map((s) => (
          <span
            key={s.kind}
            role="img"
            aria-label={`${KIND_META[s.kind].label}: ${(s.probability * 100).toFixed(0)}%`}
            title={`${KIND_META[s.kind].label} — ${(s.probability * 100).toFixed(0)}%`}
            className="block h-full"
            style={{
              width: `${s.probability * 100}%`,
              background: KIND_META[s.kind].color,
              opacity: 0.55 + 0.45 * s.probability,
            }}
          />
        ))}
      </div>
      <ul className="grid gap-2 sm:grid-cols-3 text-xs">
        {data.scenarios.map((s) => (
          <li key={s.kind} className="rounded border border-[var(--color-border-subtle)] p-2">
            <p
              className="font-mono text-[10px] uppercase tracking-widest"
              style={{ color: KIND_META[s.kind].color }}
            >
              {KIND_META[s.kind].label} · {(s.probability * 100).toFixed(0)}%
            </p>
            {s.triggers.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-[var(--color-text-secondary)]">
                {s.triggers.slice(0, 2).map((t) => (
                  <li key={t} className="font-mono text-[10px]">
                    · {t}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[10px] text-[var(--color-text-muted)]">{data.rationale}</p>
      {data.notes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[10px] text-[var(--color-text-muted)]">
          {data.notes.map((n) => (
            <li key={n}>· {n}</li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[10px] text-[var(--color-text-muted)]">
        Modèle empirique 3 scénarios (SMC + régime + conviction). Le 7-arbre Pass 4 ci-dessous reste
        mock — son schéma backend est en attente.
      </p>
    </section>
  );
}

function CounterfactualButton() {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-2 rounded-md bg-[var(--color-accent-cobalt)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-bull)]"
    >
      <span aria-hidden="true">⟁</span>
      Counterfactual Pass 5
    </button>
  );
}

function ScenarioBars({ scenarios, totalProb }: { scenarios: Scenario[]; totalProb: number }) {
  return (
    <section
      aria-label="Probability distribution bar"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6"
    >
      <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Distribution de probabilité · somme {(totalProb * 100).toFixed(0)} %
      </p>
      <div className="flex h-8 w-full overflow-hidden rounded">
        {scenarios.map((s) => {
          const color =
            s.bias === "bull"
              ? "var(--color-bull)"
              : s.bias === "bear"
                ? "var(--color-bear)"
                : "var(--color-neutral)";
          const widthPct = (s.probability / totalProb) * 100;
          return (
            <span
              key={s.id}
              role="img"
              aria-label={`${s.label}: ${(s.probability * 100).toFixed(0)}%, bias ${s.bias}`}
              title={`${s.label} — ${(s.probability * 100).toFixed(0)}%`}
              className="block h-full"
              style={{
                width: `${widthPct}%`,
                background: color,
                opacity: 0.4 + 0.6 * (s.probability / 0.32),
              }}
            />
          );
        })}
      </div>
    </section>
  );
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  return (
    <article
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 shadow-[var(--shadow-sm)]"
      data-bias={scenario.bias}
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{scenario.label}</h2>
        <BiasIndicator
          bias={scenario.bias}
          value={scenario.probability * 100}
          unit="%"
          variant="compact"
          size="xs"
        />
      </div>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        {scenario.primary_mechanism}
      </p>
      <dl className="space-y-1 text-xs">
        <div className="flex justify-between">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Magnitude
          </dt>
          <dd className="font-mono tabular-nums">
            {scenario.magnitude_pips.low}–{scenario.magnitude_pips.high} pips
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Invalidation
          </dt>
          <dd className="font-mono text-[var(--color-bear)]">{scenario.invalidation}</dd>
        </div>
        {scenario.counterfactual_anchor && (
          <div className="mt-2 flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-accent-cobalt-bright)]"
            />
            <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-accent-cobalt-bright)]">
              Pass 5 anchor: {scenario.counterfactual_anchor}
            </span>
          </div>
        )}
      </dl>
    </article>
  );
}
