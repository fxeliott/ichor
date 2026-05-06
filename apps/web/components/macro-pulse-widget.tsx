/**
 * MacroPulseWidget — compact 4-tile macro snapshot for the home page.
 *
 * Sleek tone-coded tiles with mini-bar. Single fetch /v1/macro-pulse,
 * instant macro-weather read at-a-glance.
 */

import Link from "next/link";
import { ApiError, getMacroPulse, type MacroPulse } from "../lib/api";
import { GlassCard } from "./ui/glass-card";

export const revalidate = 60;

type TileTone = "emerald" | "amber" | "rose" | "neutral" | "accent";

interface TileSpec {
  label: string;
  primary: string;
  secondary: string;
  tone: TileTone;
  icon: string;
}

export async function MacroPulseWidget() {
  let pulse: MacroPulse | null = null;
  let error: string | null = null;
  try {
    pulse = await getMacroPulse();
  } catch (err) {
    error =
      err instanceof ApiError ? err.message : err instanceof Error ? err.message : "unknown error";
  }

  if (error || !pulse) {
    return (
      <GlassCard variant="glass" className="p-4">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">Macro pulse</h2>
        <p className="text-xs text-[var(--color-ichor-text-subtle)]">{error ?? "Indisponible."}</p>
      </GlassCard>
    );
  }

  const tiles: TileSpec[] = [
    {
      label: "VIX term",
      primary: pulse.vix_term.regime.replace(/_/g, " "),
      secondary:
        pulse.vix_term.ratio != null
          ? `ratio ${pulse.vix_term.ratio.toFixed(2)}${pulse.vix_term.vix_1m != null ? ` · VIX ${pulse.vix_term.vix_1m.toFixed(1)}` : ""}`
          : "n/a",
      tone: vixTone(pulse.vix_term.regime),
      icon: "📊",
    },
    {
      label: "Risk appetite",
      primary: pulse.risk_appetite.band.replace(/_/g, " "),
      secondary: `composite ${pulse.risk_appetite.composite >= 0 ? "+" : ""}${pulse.risk_appetite.composite.toFixed(2)}`,
      tone: riskTone(pulse.risk_appetite.band),
      icon: "⚡",
    },
    {
      label: "Yield curve",
      primary: pulse.yield_curve.shape,
      secondary:
        pulse.yield_curve.slope_2y_10y != null
          ? `2Y-10Y ${pulse.yield_curve.slope_2y_10y >= 0 ? "+" : ""}${pulse.yield_curve.slope_2y_10y.toFixed(2)}pp`
          : "n/a",
      tone: curveTone(pulse.yield_curve.shape),
      icon: "📈",
    },
    {
      label: "Funding stress",
      primary:
        pulse.funding_stress.stress_score >= 0.5
          ? "elevated"
          : pulse.funding_stress.stress_score >= 0.2
            ? "moderate"
            : "relaxed",
      secondary: `score ${pulse.funding_stress.stress_score >= 0 ? "+" : ""}${pulse.funding_stress.stress_score.toFixed(2)}`,
      tone:
        pulse.funding_stress.stress_score >= 0.5
          ? "rose"
          : pulse.funding_stress.stress_score >= 0.2
            ? "amber"
            : "emerald",
      icon: "💧",
    },
  ];

  return (
    <GlassCard variant="glass" className="p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">Macro pulse</h2>
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-faint)] font-mono">
            FRED + modèles
          </span>
        </div>
        <Link
          href="/macro-pulse"
          className="text-[11px] text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-accent-bright)] transition flex items-center gap-1"
        >
          Détail <span aria-hidden="true">→</span>
        </Link>
      </header>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {tiles.map((t, i) => (
          <PulseTile key={t.label} tile={t} stagger={i + 1} />
        ))}
      </div>
    </GlassCard>
  );
}

function PulseTile({ tile, stagger }: { tile: TileSpec; stagger: number }) {
  const TONE_CLS: Record<TileTone, string> = {
    emerald:
      "bg-[var(--color-ichor-long)]/8 border-[var(--color-ichor-long)]/30 text-[var(--color-ichor-long)]",
    amber: "bg-amber-500/8 border-amber-500/30 text-amber-200",
    rose: "bg-[var(--color-ichor-short)]/8 border-[var(--color-ichor-short)]/30 text-[var(--color-ichor-short)]",
    accent:
      "bg-[var(--color-ichor-accent)]/8 border-[var(--color-ichor-accent)]/30 text-[var(--color-ichor-accent-bright)]",
    neutral:
      "bg-[var(--color-ichor-surface-2)]/40 border-[var(--color-ichor-border)] text-[var(--color-ichor-text-muted)]",
  };
  const STRIPE: Record<TileTone, string> = {
    emerald: "from-emerald-700 to-emerald-400",
    amber: "from-amber-700 to-amber-400",
    rose: "from-rose-700 to-rose-400",
    accent: "from-[var(--color-ichor-accent-deep)] to-[var(--color-ichor-accent-bright)]",
    neutral: "from-slate-700 to-slate-500",
  };
  return (
    <div
      className={`relative overflow-hidden rounded-lg border p-2.5 ichor-lift ichor-fade-in ${TONE_CLS[tile.tone]}`}
      data-stagger={stagger}
    >
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-gradient-to-b ${STRIPE[tile.tone]}`}
      />
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-subtle)]">
          {tile.label}
        </span>
        <span className="text-sm opacity-60" aria-hidden="true">
          {tile.icon}
        </span>
      </div>
      <div className="font-mono text-sm truncate">{tile.primary}</div>
      <div className="text-[10px] text-[var(--color-ichor-text-muted)] mt-0.5 truncate">
        {tile.secondary}
      </div>
    </div>
  );
}

function vixTone(regime: string): TileTone {
  if (regime.includes("backwardation")) return "rose";
  if (regime === "stretched_contango") return "amber";
  if (regime === "contango" || regime === "normal") return "emerald";
  return "neutral";
}

function riskTone(band: string): TileTone {
  if (band.includes("extreme_risk_off")) return "rose";
  if (band === "risk_off") return "rose";
  if (band === "neutral") return "neutral";
  if (band === "risk_on" || band === "extreme_risk_on") return "emerald";
  return "neutral";
}

function curveTone(shape: string): TileTone {
  if (shape === "inverted_full") return "rose";
  if (shape === "inverted_short") return "amber";
  if (shape === "steep") return "amber";
  if (shape === "normal") return "emerald";
  return "neutral";
}
