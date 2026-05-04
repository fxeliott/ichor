/**
 * CurrencyStrengthWidget — ranked basket strength widget for the home page.
 *
 * Server component : pulls /v1/currency-strength?window_hours=24 and renders
 * a ranked horizontal bar list (strongest at top). Each bar has the
 * currency code, the % score (signed), and a colored fill.
 *
 * Color encoding :
 *   - score > 0  → emerald (strong)
 *   - score < 0  → rose (weak)
 *   - magnitude scales bar length, capped at ±2%.
 *
 * VISION_2026 — closes the "what's the basket picture?" gap. Critical
 * for FX traders who watch one pair at a time.
 */

import { ApiError, getCurrencyStrength, type CurrencyStrength } from "../lib/api";

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
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  if (error || !report || report.entries.length === 0) {
    return (
      <section
        aria-labelledby="currency-strength-heading"
        className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4"
      >
        <h2
          id="currency-strength-heading"
          className="text-sm font-semibold text-neutral-200 mb-2"
        >
          Force des devises (24h)
        </h2>
        <p className="text-xs text-neutral-500">
          {error
            ? `Indisponible : ${error}`
            : "En attente de bars polygon suffisamment longs."}
        </p>
      </section>
    );
  }

  const maxAbs = Math.max(0.5, ...report.entries.map((e) => Math.abs(e.score)));

  return (
    <section
      aria-labelledby="currency-strength-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="currency-strength-heading"
          className="text-sm font-semibold text-neutral-200"
        >
          Force des devises (24h)
        </h2>
        <span className="text-[10px] text-neutral-500 font-mono">
          {new Date(report.generated_at).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "Europe/Paris",
          })}
        </span>
      </header>
      <ul className="space-y-1.5">
        {report.entries.map((e) => {
          const pct = (Math.abs(e.score) / maxAbs) * 100;
          const positive = e.score >= 0;
          return (
            <li
              key={e.currency}
              className="flex items-center gap-2 text-xs"
            >
              <span className="w-12 font-mono text-neutral-300">
                <span className="mr-1" aria-hidden="true">
                  {FX_FLAGS[e.currency] ?? "·"}
                </span>
                {e.currency}
              </span>
              <div className="flex-1 h-3 rounded bg-neutral-950 relative overflow-hidden border border-neutral-800">
                <div
                  className={`absolute top-0 bottom-0 ${positive ? "left-1/2 bg-emerald-500/80" : "right-1/2 bg-rose-500/80"}`}
                  style={{ width: `${pct / 2}%` }}
                />
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-neutral-700" />
              </div>
              <span
                className={`font-mono w-16 text-right ${positive ? "text-emerald-300" : "text-rose-300"}`}
              >
                {positive ? "+" : ""}
                {e.score.toFixed(2)}%
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-[10px] text-neutral-500 leading-snug">
        Scores moyens des % de variation 24h des paires USD-quotées.
        Positif = devise forte, négatif = faible.
      </p>
    </section>
  );
}
