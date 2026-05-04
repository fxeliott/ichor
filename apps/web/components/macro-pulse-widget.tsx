/**
 * MacroPulseWidget — compact 4-tile macro snapshot for the home page.
 *
 * Single fetch (/v1/macro-pulse) renders 4 large tiles : VIX regime,
 * risk appetite band, curve shape, funding stress score. Each tile
 * is colored by intensity so Eliot reads the macro weather in one
 * second.
 *
 * VISION_2026 — closes the "I open the dashboard and immediately know
 * the macro climate" gap.
 */

import Link from "next/link";
import { ApiError, getMacroPulse, type MacroPulse } from "../lib/api";

export const revalidate = 60;

export async function MacroPulseWidget() {
  let pulse: MacroPulse | null = null;
  let error: string | null = null;
  try {
    pulse = await getMacroPulse();
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  if (error || !pulse) {
    return (
      <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
        <h2 className="text-sm font-semibold text-neutral-200 mb-2">
          Macro pulse
        </h2>
        <p className="text-xs text-neutral-500">
          {error ?? "Indisponible."}
        </p>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="macro-pulse-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="macro-pulse-heading"
          className="text-sm font-semibold text-neutral-200"
        >
          Macro pulse
        </h2>
        <Link
          href="/macro-pulse"
          className="text-[11px] text-neutral-400 hover:text-neutral-200"
        >
          Détail →
        </Link>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile
          label="VIX term"
          primary={pulse.vix_term.regime.replace(/_/g, " ")}
          secondary={
            pulse.vix_term.ratio != null
              ? `ratio ${pulse.vix_term.ratio.toFixed(2)}`
              : "n/a"
          }
          tone={vixTone(pulse.vix_term.regime)}
        />
        <Tile
          label="Risk appetite"
          primary={pulse.risk_appetite.band.replace(/_/g, " ")}
          secondary={`${pulse.risk_appetite.composite >= 0 ? "+" : ""}${pulse.risk_appetite.composite.toFixed(2)}`}
          tone={riskTone(pulse.risk_appetite.band)}
        />
        <Tile
          label="Yield curve"
          primary={pulse.yield_curve.shape}
          secondary={
            pulse.yield_curve.slope_2y_10y != null
              ? `2Y-10Y ${pulse.yield_curve.slope_2y_10y >= 0 ? "+" : ""}${pulse.yield_curve.slope_2y_10y.toFixed(2)}pp`
              : "n/a"
          }
          tone={curveTone(pulse.yield_curve.shape)}
        />
        <Tile
          label="Funding stress"
          primary={
            pulse.funding_stress.stress_score >= 0.5
              ? "elevated"
              : pulse.funding_stress.stress_score >= 0.2
                ? "moderate"
                : "relaxed"
          }
          secondary={`score ${pulse.funding_stress.stress_score >= 0 ? "+" : ""}${pulse.funding_stress.stress_score.toFixed(2)}`}
          tone={
            pulse.funding_stress.stress_score >= 0.5
              ? "rose"
              : pulse.funding_stress.stress_score >= 0.2
                ? "amber"
                : "emerald"
          }
        />
      </div>
    </section>
  );
}

type Tone = "emerald" | "amber" | "rose" | "neutral";

function Tile({
  label,
  primary,
  secondary,
  tone,
}: {
  label: string;
  primary: string;
  secondary: string;
  tone: Tone;
}) {
  // Static class strings so Tailwind JIT can detect them.
  const toneCls: Record<Tone, string> = {
    emerald: "border-emerald-700/40 bg-emerald-900/15 text-emerald-200",
    amber: "border-amber-700/40 bg-amber-900/15 text-amber-200",
    rose: "border-rose-700/40 bg-rose-900/15 text-rose-200",
    neutral: "border-neutral-700 bg-neutral-900/40 text-neutral-300",
  };
  return (
    <div className={`rounded border ${toneCls[tone]} p-2.5`}>
      <div className="text-[10px] uppercase tracking-wide opacity-70">
        {label}
      </div>
      <div className="text-sm font-mono mt-1 truncate">{primary}</div>
      <div className="text-[11px] opacity-60 font-mono mt-0.5">
        {secondary}
      </div>
    </div>
  );
}

function vixTone(regime: string): Tone {
  if (regime.includes("backwardation")) return "rose";
  if (regime === "stretched_contango") return "amber";
  if (regime === "contango" || regime === "normal") return "emerald";
  return "neutral";
}

function riskTone(band: string): Tone {
  if (band.includes("extreme_risk_off")) return "rose";
  if (band === "risk_off") return "rose";
  if (band === "neutral") return "neutral";
  if (band === "risk_on") return "emerald";
  if (band === "extreme_risk_on") return "emerald";
  return "neutral";
}

function curveTone(shape: string): Tone {
  if (shape === "inverted_full") return "rose";
  if (shape === "inverted_short") return "amber";
  if (shape === "steep") return "amber";
  if (shape === "normal") return "emerald";
  return "neutral";
}
