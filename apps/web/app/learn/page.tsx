/**
 * /learn — pédagogie visuelle des concepts utilisés par Ichor.
 *
 * Diagrammes inline SVG : PDH/PDL + Asian range, plan RR, scénarios SMC,
 * VIX term structure, régime quadrant, confluence engine. Pas de lib
 * externe : tout est SVG composé à la main pour rester rapide + SSR-safe.
 *
 * Structure : 6 sections, chacune avec un titre, un schéma, et 3 phrases
 * d'explication. Ambient orbs en hero, glass cards par section.
 */

import Link from "next/link";
import { AmbientOrbs } from "../../components/ui/ambient-orbs";
import { GlassCard } from "../../components/ui/glass-card";

export const metadata = { title: "Apprendre — Ichor" };

export default function LearnPage() {
  return (
    <div className="relative">
      <div className="absolute inset-x-0 top-0 h-[500px] pointer-events-none">
        <AmbientOrbs variant="default" />
        <div className="absolute inset-0 ichor-grid-bg opacity-40" />
      </div>

      <main className="relative max-w-5xl mx-auto px-4 py-8">
        <header className="mb-8 ichor-fade-in">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[var(--color-ichor-accent-bright)] mb-1">
            Apprendre · 6 chapitres
          </p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[var(--color-ichor-text)]">
            Comment <span className="bg-gradient-to-r from-[var(--color-ichor-accent-bright)] to-[var(--color-ichor-accent-muted)] bg-clip-text text-transparent">lire</span> Ichor
          </h1>
          <p className="text-sm text-[var(--color-ichor-text-muted)] mt-2 max-w-2xl">
            Les concepts macro / SMC / RR utilisés partout dans l&apos;app,
            illustrés en 1 schéma + 3 phrases. Tout est cliquable pour
            drill-down vers la page live.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ChapterCard
            id="ch-1"
            number={1}
            title="Régime macro · 4 quadrants"
            chip="Pass 1"
            href="/macro-pulse"
            description={[
              "Tout commence par lire le quadrant macro courant. Ichor classifie en 4 régimes selon DXY + VIX + HY OAS + courbe taux.",
              "Goldilocks = vol basse + risk-on = trends. Haven bid = USD↑ XAU↑ JPY↑. Funding stress = squeeze. USD complacency = DXY↑ sans stress.",
              "Le régime tilt automatiquement les confluences : goldilocks +0.10 sur les paires risk-on, funding_stress -0.10 (mean-revert friendly).",
            ]}
            stagger={1}
          >
            <RegimeQuadrantDiagram />
          </ChapterCard>

          <ChapterCard
            id="ch-2"
            number={2}
            title="Daily levels SMC"
            chip="Toolbox"
            href="/scenarios/EUR_USD"
            description={[
              "Les niveaux que tu watches sur TradingView : PDH/PDL (Previous Day H/L), Asian range (00-07 UTC), Pivots floor-trader, weekly H/L, round numbers psychologiques.",
              "Ces niveaux deviennent des aimants institutionnels. La sweep d'un PDH suivie d'un MSS (Market Structure Shift) → opportunité reversal classique.",
              "Le service daily_levels.py les pré-calcule sur les 8 actifs et les sert à chaque pré-Londres / pré-NY / NY-mid.",
            ]}
            stagger={2}
          >
            <DailyLevelsDiagram />
          </ChapterCard>

          <ChapterCard
            id="ch-3"
            number={3}
            title="Scénarios session · 3 issues"
            chip="Probabilités"
            href="/scenarios/EUR_USD"
            description={[
              "Chaque session se résout en Continuation (le move précédent prolonge) / Reversal (sweep + MSS = flip) / Sideways (consolidation).",
              "Ichor probabilise les 3 issues à partir de la position de spot vs PDH/PDL, du régime, de la conviction post-stress et de la session courante.",
              "P(reversal) gagne +0.25 quand spot a sweep PDH/PDL. P(sideways) augmente avec basse conviction + spot mid-range.",
            ]}
            stagger={3}
          >
            <ScenariosDiagram />
          </ChapterCard>

          <ChapterCard
            id="ch-4"
            number={4}
            title="Plan RR · target 3"
            chip="Exécution"
            href="/scenarios/EUR_USD"
            description={[
              "Ton playbook : RR≥3, BE à RR=1, close 90% à RR=3, runner 10% en trail jusqu'à RR=15+. Ichor calcule l'entry zone, le SL, TP1/TP3/TP-extended.",
              "Risk = magnitude_pips_low / 2 (un stop serré, floor à 5 pips). Reward TP3 = risk × 3. TP_extended = max(magnitude_pips_high, risk × 5).",
              "Le bouton 🎯 Scénarios+RR sur chaque session card te donne le plan opérationnel d'un clic, avec sanity check vs PDL/PDH.",
            ]}
            stagger={4}
          >
            <RRPlanDiagram />
          </ChapterCard>

          <ChapterCard
            id="ch-5"
            number={5}
            title="VIX term structure"
            chip="Vol forward"
            href="/macro-pulse"
            description={[
              "VIX 1M / VIX 3M ratio te dit si le marché price plus de vol forward (contango ratio<1) ou near-term (backwardation ratio>1).",
              "Backwardation ≈ panique short-term : historiquement les périodes les plus payantes pour mean-revert long equity 1-3 mois.",
              "Stretched contango (ratio<0.80) = complacence : signal d'avertissement, vigilance sur les vol-spike events.",
            ]}
            stagger={5}
          >
            <VixTermDiagram />
          </ChapterCard>

          <ChapterCard
            id="ch-6"
            number={6}
            title="Confluence engine · 10 facteurs"
            chip="Synthèse"
            href="/confluence"
            description={[
              "10 drivers évalués indépendamment, chacun signe leur contribution dans [-1, +1]. Score long/short = clamp(50 + 8 × Σ contributions, 0, 100).",
              "Dominante émerge si le score ≥ 60 ET écart ≥ 5 pts vs autre direction. Le confluence_count est le nombre de facteurs aligné > |0.2|.",
              "Eliot's rule : un trade backé par ≥ 5 confluences vaut mieux qu'un trade backé par 2. Le sparkline 30j te montre la persistence du score.",
            ]}
            stagger={6}
          >
            <ConfluenceDiagram />
          </ChapterCard>
        </div>

        <footer className="mt-10 text-center ichor-fade-in" data-stagger="6">
          <p className="text-xs text-[var(--color-ichor-text-subtle)]">
            Pour aller plus loin :{" "}
            <Link href="/sources" className="text-[var(--color-ichor-accent-bright)] hover:underline">
              Sources data
            </Link>{" "}
            ·{" "}
            <Link href="/admin" className="text-[var(--color-ichor-accent-bright)] hover:underline">
              Health snapshot
            </Link>{" "}
            ·{" "}
            <Link href="/calibration" className="text-[var(--color-ichor-accent-bright)] hover:underline">
              Calibration Brier
            </Link>
          </p>
        </footer>
      </main>
    </div>
  );
}

// ─────────────────────── Wrapper ───────────────────────

function ChapterCard({
  id,
  number,
  title,
  chip,
  href,
  description,
  children,
  stagger,
}: {
  id: string;
  number: number;
  title: string;
  chip: string;
  href: string;
  description: string[];
  children: React.ReactNode;
  stagger: number;
}) {
  return (
    <GlassCard
      variant="glass"
      lift
      className="p-5 ichor-fade-in"
      data-stagger={stagger}
    >
      <header className="flex items-baseline justify-between mb-3 gap-2">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-[var(--color-ichor-accent-bright)] text-lg">
            0{number}
          </span>
          <h2 id={id} className="text-base font-semibold text-[var(--color-ichor-text)]">
            {title}
          </h2>
        </div>
        <span className="text-[10px] uppercase font-mono tracking-wider px-1.5 py-0.5 rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)]/40 text-[var(--color-ichor-text-faint)]">
          {chip}
        </span>
      </header>

      <div className="mb-4 flex justify-center rounded-lg bg-[var(--color-ichor-deep)]/40 border border-[var(--color-ichor-border)] p-3">
        {children}
      </div>

      <ul className="space-y-2 text-xs text-[var(--color-ichor-text-muted)] leading-relaxed">
        {description.map((d, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-[var(--color-ichor-accent)] mt-0.5">▸</span>
            <span>{d}</span>
          </li>
        ))}
      </ul>

      <Link
        href={href}
        className="inline-flex items-center gap-1 mt-4 text-xs text-[var(--color-ichor-accent-bright)] hover:underline transition"
      >
        Voir live <span aria-hidden="true">→</span>
      </Link>
    </GlassCard>
  );
}

// ─────────────────────── Diagrams (inline SVG) ───────────────────────

function RegimeQuadrantDiagram() {
  const quadrants = [
    { x: 0, y: 0, label: "Haven\nbid", color: "#06B6D4", desc: "USD↑ XAU↑" },
    { x: 1, y: 0, label: "Funding\nstress", color: "#EF4444", desc: "HY OAS↑" },
    { x: 0, y: 1, label: "Goldi-\nlocks", color: "#10B981", desc: "trends" },
    { x: 1, y: 1, label: "USD\ncomplac.", color: "#F59E0B", desc: "DXY↑" },
  ];
  return (
    <svg
      viewBox="0 0 240 160"
      width="240"
      height="160"
      className="overflow-visible"
      aria-label="4-quadrant régime macro diagram"
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#3B82F6" />
        </marker>
      </defs>
      {/* Axes labels */}
      <text x="120" y="10" fill="#5A6E89" fontSize="9" textAnchor="middle">stress macro →</text>
      <text x="0" y="80" fill="#5A6E89" fontSize="9" transform="rotate(-90, 0, 80)" textAnchor="middle">conviction →</text>

      {quadrants.map((q, i) => (
        <g key={i} transform={`translate(${20 + q.x * 110}, ${20 + q.y * 65})`}>
          <rect
            width="100"
            height="55"
            rx="8"
            fill={q.color}
            fillOpacity="0.15"
            stroke={q.color}
            strokeOpacity="0.5"
            strokeWidth="1"
          />
          <text
            x="50"
            y="22"
            fill={q.color}
            fontSize="10"
            fontWeight="600"
            textAnchor="middle"
          >
            {q.label.split("\n")[0]}
          </text>
          <text x="50" y="34" fill={q.color} fontSize="10" fontWeight="600" textAnchor="middle">
            {q.label.split("\n")[1]}
          </text>
          <text x="50" y="48" fill={q.color} fillOpacity="0.7" fontSize="9" textAnchor="middle">
            {q.desc}
          </text>
        </g>
      ))}
    </svg>
  );
}

function DailyLevelsDiagram() {
  // Mock candle chart with PDH / PDL / Asian range overlays
  const candles = [
    { x: 30, h: 90, l: 130 },
    { x: 50, h: 70, l: 110 },
    { x: 70, h: 60, l: 100 },
    { x: 90, h: 80, l: 120 },
    { x: 110, h: 50, l: 90 },
    { x: 130, h: 65, l: 105 },
    { x: 150, h: 55, l: 100 },
    { x: 170, h: 75, l: 115 },
    { x: 190, h: 85, l: 125 },
    { x: 210, h: 45, l: 95 },
  ];
  return (
    <svg viewBox="0 0 240 160" width="240" height="160" aria-label="Daily levels SMC diagram">
      {/* PDH line */}
      <line x1="10" y1="55" x2="230" y2="55" stroke="#F87171" strokeWidth="1" strokeDasharray="3 2" />
      <text x="232" y="58" fill="#F87171" fontSize="9">PDH</text>
      {/* PDL */}
      <line x1="10" y1="125" x2="230" y2="125" stroke="#34D399" strokeWidth="1" strokeDasharray="3 2" />
      <text x="232" y="128" fill="#34D399" fontSize="9">PDL</text>
      {/* Asian range box */}
      <rect x="10" y="75" width="60" height="30" fill="#3B82F6" fillOpacity="0.10" stroke="#3B82F6" strokeOpacity="0.5" strokeDasharray="2 2" />
      <text x="14" y="86" fill="#60A5FA" fontSize="8">Asian range</text>
      {/* Pivot */}
      <line x1="10" y1="90" x2="230" y2="90" stroke="#94A3B8" strokeWidth="0.5" strokeOpacity="0.6" />
      <text x="232" y="93" fill="#94A3B8" fontSize="8">PP</text>
      {/* Candles */}
      {candles.map((c, i) => (
        <g key={i}>
          <line x1={c.x} y1={c.h - 6} x2={c.x} y2={c.l + 6} stroke="#8FA3BF" strokeWidth="0.8" />
          <rect
            x={c.x - 4}
            y={Math.min(c.h, c.l)}
            width="8"
            height={Math.abs(c.h - c.l)}
            fill={i % 2 === 0 ? "#34D399" : "#F87171"}
            fillOpacity="0.8"
          />
        </g>
      ))}
    </svg>
  );
}

function ScenariosDiagram() {
  return (
    <svg viewBox="0 0 240 160" width="240" height="160" aria-label="Scenarios SMC diagram">
      {/* Spot in center */}
      <circle cx="60" cy="80" r="4" fill="#60A5FA" />
      <text x="40" y="74" fill="#60A5FA" fontSize="9">spot</text>

      {/* 3 paths : Continuation up, Reversal down, Sideways */}
      <path
        d="M 60 80 Q 120 60 180 30"
        stroke="#34D399"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <text x="190" y="32" fill="#34D399" fontSize="10" fontWeight="600">Cont. ↑</text>

      <path
        d="M 60 80 Q 120 130 180 140"
        stroke="#F87171"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <text x="190" y="144" fill="#F87171" fontSize="10" fontWeight="600">Rev. ↓</text>

      <path
        d="M 60 80 Q 120 80 180 80 M 90 75 L 90 85 M 110 75 L 110 85 M 130 75 L 130 85 M 150 75 L 150 85 M 170 75 L 170 85"
        stroke="#94A3B8"
        strokeWidth="1.2"
        fill="none"
        strokeDasharray="2 3"
        strokeLinecap="round"
      />
      <text x="190" y="84" fill="#94A3B8" fontSize="10" fontWeight="600">Side. ↔</text>

      {/* Probabilities */}
      <text x="180" y="50" fill="#34D399" fontSize="8" textAnchor="end">35%</text>
      <text x="180" y="100" fill="#94A3B8" fontSize="8" textAnchor="end">28%</text>
      <text x="180" y="125" fill="#F87171" fontSize="8" textAnchor="end">37%</text>
    </svg>
  );
}

function RRPlanDiagram() {
  return (
    <svg viewBox="0 0 240 160" width="240" height="160" aria-label="RR plan diagram">
      {/* Vertical timeline */}
      <line x1="40" y1="20" x2="40" y2="140" stroke="#1A2435" strokeWidth="1" />
      {/* Markers : SL, Entry, TP1, TP3, TPext */}
      {[
        { y: 130, label: "SL", color: "#F87171", note: "−1 R" },
        { y: 100, label: "Entry zone", color: "#60A5FA", note: "spot ±5p" },
        { y: 80, label: "TP1 = BE", color: "#F59E0B", note: "+1 R" },
        { y: 50, label: "TP3 = close 90%", color: "#34D399", note: "+3 R" },
        { y: 25, label: "TP ext (trail 10%)", color: "#34D399", note: "+5 R+" },
      ].map((m, i) => (
        <g key={i}>
          <circle cx="40" cy={m.y} r="3.5" fill={m.color} />
          <text x="50" y={m.y + 3} fill={m.color} fontSize="9" fontWeight="600">
            {m.label}
          </text>
          <text x="200" y={m.y + 3} fill="#5A6E89" fontSize="8" textAnchor="end">
            {m.note}
          </text>
        </g>
      ))}
      {/* Risk arrow */}
      <line x1="22" y1="100" x2="22" y2="130" stroke="#F87171" strokeWidth="1" markerEnd="url(#arrow)" />
      <text x="6" y="118" fill="#F87171" fontSize="8">risk</text>
    </svg>
  );
}

function VixTermDiagram() {
  return (
    <svg viewBox="0 0 240 160" width="240" height="160" aria-label="VIX term structure diagram">
      {/* Axis */}
      <line x1="30" y1="130" x2="220" y2="130" stroke="#3F526E" strokeWidth="0.8" />
      <line x1="30" y1="20" x2="30" y2="130" stroke="#3F526E" strokeWidth="0.8" />
      <text x="215" y="145" fill="#5A6E89" fontSize="8">tenor</text>
      <text x="6" y="22" fill="#5A6E89" fontSize="8">VIX</text>

      {/* Three curves : contango, normal, backwardation */}
      <path
        d="M 50 100 Q 120 70 200 40"
        stroke="#34D399"
        strokeWidth="1.5"
        fill="none"
      />
      <text x="190" y="45" fill="#34D399" fontSize="9" fontWeight="600">contango</text>

      <path
        d="M 50 80 L 200 80"
        stroke="#94A3B8"
        strokeWidth="1.2"
        strokeDasharray="3 3"
        fill="none"
      />
      <text x="180" y="76" fill="#94A3B8" fontSize="9">flat</text>

      <path
        d="M 50 50 Q 120 80 200 110"
        stroke="#F87171"
        strokeWidth="1.5"
        fill="none"
      />
      <text x="160" y="120" fill="#F87171" fontSize="9" fontWeight="600">backwardation</text>

      {/* Tick labels */}
      {[
        ["1M", 50],
        ["3M", 95],
        ["6M", 140],
        ["1Y", 200],
      ].map(([l, x], i) => (
        <text key={i} x={x as number} y="140" fill="#5A6E89" fontSize="8" textAnchor="middle">
          {l}
        </text>
      ))}
    </svg>
  );
}

function ConfluenceDiagram() {
  const factors = [
    { label: "rate diff", value: 0.35 },
    { label: "COT", value: -0.20 },
    { label: "OFI", value: 0.45 },
    { label: "daily lvl", value: 0.30 },
    { label: "polymkt", value: 0.10 },
    { label: "fund. stress", value: -0.15 },
    { label: "surprise", value: 0.25 },
    { label: "VIX term", value: 0.40 },
    { label: "risk app.", value: 0.55 },
    { label: "BTC proxy", value: 0.20 },
  ];
  return (
    <svg viewBox="0 0 240 200" width="240" height="200" aria-label="Confluence engine diagram">
      {/* Central axis */}
      <line x1="120" y1="10" x2="120" y2="190" stroke="#1A2435" strokeWidth="1" />
      {factors.map((f, i) => {
        const y = 18 + i * 18;
        const w = Math.abs(f.value) * 90;
        const x = f.value >= 0 ? 120 : 120 - w;
        return (
          <g key={i}>
            <text
              x={f.value >= 0 ? 115 : 125}
              y={y + 4}
              fill="#8FA3BF"
              fontSize="9"
              textAnchor={f.value >= 0 ? "end" : "start"}
            >
              {f.label}
            </text>
            <rect
              x={x}
              y={y - 4}
              width={w}
              height="9"
              rx="2"
              fill={f.value >= 0 ? "#34D399" : "#F87171"}
              fillOpacity="0.85"
            />
          </g>
        );
      })}
    </svg>
  );
}
