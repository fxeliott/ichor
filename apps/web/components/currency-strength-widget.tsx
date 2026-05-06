/**
 * CurrencyStrengthWidget — ranked basket strength with diverging bars.
 *
 * Each currency rendered as a centered diverging bar : positive →
 * emerald right of the axis, negative → rose left. Magnitude is the
 * fraction of the largest |score| in the basket.
 */

import { ApiError, getCurrencyStrength, type CurrencyStrength } from "../lib/api";
import { GlassCard } from "./ui/glass-card";

export const revalidate = 60;

const FX_FLAGS: Record<string, string> = {
  USD: "🇺🇸",
  EUR: "🇪🇺",
  GBP: "🇬🇧",
  JPY: "🇯🇵",
  AUD: "🇦🇺",
  CAD: "🇨🇦",
  CHF: "🇨🇭",
  NZD: "🇳🇿",
};

export async function CurrencyStrengthWidget() {
  let report: CurrencyStrength | null = null;
  let error: string | null = null;
  try {
    report = await getCurrencyStrength(24);
  } catch (err) {
    error =
      err instanceof ApiError ? err.message : err instanceof Error ? err.message : "unknown error";
  }

  if (error || !report || report.entries.length === 0) {
    return (
      <GlassCard variant="glass" className="p-4">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">
          Force des devises (24h)
        </h2>
        <p className="text-xs text-[var(--color-ichor-text-subtle)]">
          {error ? `Indisponible : ${error}` : "En attente de bars polygon."}
        </p>
      </GlassCard>
    );
  }

  const maxAbs = Math.max(0.5, ...report.entries.map((e) => Math.abs(e.score)));

  return (
    <GlassCard variant="glass" className="p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">
            Force des devises
          </h2>
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-faint)] font-mono">
            24h · basket
          </span>
        </div>
        <span className="text-[10px] text-[var(--color-ichor-text-subtle)] font-mono">
          {new Date(report.generated_at).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "Europe/Paris",
          })}
        </span>
      </header>

      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        {report.entries.map((e, i) => {
          const pct = (Math.abs(e.score) / maxAbs) * 100;
          const positive = e.score >= 0;
          return (
            <li
              key={e.currency}
              className="flex items-center gap-2 text-xs ichor-fade-in"
              data-stagger={Math.min(6, i + 1)}
            >
              <span className="w-12 font-mono text-[var(--color-ichor-text)] flex items-center gap-1">
                <span className="text-base" aria-hidden="true">
                  {FX_FLAGS[e.currency] ?? "·"}
                </span>
                {e.currency}
              </span>
              <div className="flex-1 h-2.5 rounded bg-[var(--color-ichor-deep)] relative overflow-hidden border border-[var(--color-ichor-border)]">
                <div
                  className={`absolute top-0 bottom-0 ${
                    positive
                      ? "left-1/2 bg-gradient-to-r from-[var(--color-ichor-long-deep)] to-[var(--color-ichor-long)]"
                      : "right-1/2 bg-gradient-to-l from-[var(--color-ichor-short-deep)] to-[var(--color-ichor-short)]"
                  }`}
                  style={{ width: `${pct / 2}%` }}
                />
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-[var(--color-ichor-border-strong)]" />
              </div>
              <span
                className={`w-16 text-right font-mono ${positive ? "ichor-text-long" : "ichor-text-short"}`}
              >
                {positive ? "+" : ""}
                {e.score.toFixed(2)}%
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-[10px] text-[var(--color-ichor-text-subtle)] leading-snug">
        Moyenne des % de variation 24h des paires USD-quotées. Positif = devise forte, négatif =
        faible.
      </p>
    </GlassCard>
  );
}
