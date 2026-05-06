/**
 * /calibration — Public Brier-score track-record.
 *
 * Renders the global reliability diagram + per-asset and per-régime
 * breakdown of mean Brier, skill score, hit/miss count.
 *
 * Honest calibration UI = ADR-017 capability #8 + Anthropic Usage
 * Policy "research material to inform a human decision" : Eliot can
 * see exactly how good the system was on EUR/USD pré-Londres in
 * funding_stress over the last 90 days.
 *
 * VISION_2026 delta H.
 */

import {
  ApiError,
  getCalibrationByAsset,
  getCalibrationByRegime,
  getCalibrationOverall,
} from "../../lib/api";
import { ReliabilityDiagram } from "../../components/reliability-diagram";

export const metadata = {
  title: "Calibration",
};

export const dynamic = "force-dynamic";
export const revalidate = 300;

const REGIME_LABEL: Record<string, string> = {
  haven_bid: "Haven bid",
  funding_stress: "Funding stress",
  goldilocks: "Goldilocks",
  usd_complacency: "USD complacency",
  unknown: "Régime non classé",
};

const fmtPct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)} %`;
const fmtSigned = (v: number, digits = 2) => (v >= 0 ? `+${v.toFixed(digits)}` : v.toFixed(digits));

const skillBadge = (skill: number) => {
  if (skill >= 0.5) return "bg-emerald-900/50 text-emerald-200 border-emerald-700/50";
  if (skill >= 0.1) return "bg-emerald-950/40 text-emerald-300 border-emerald-800/40";
  if (skill >= -0.1)
    return "bg-[var(--color-ichor-surface-2)] text-[var(--color-ichor-text-muted)] border-[var(--color-ichor-border-strong)]/60";
  return "bg-red-900/50 text-red-200 border-red-700/50";
};

export default async function CalibrationPage() {
  let overall, byAsset, byRegime;
  let error: string | null = null;
  try {
    [overall, byAsset, byRegime] = await Promise.all([
      getCalibrationOverall({ windowDays: 90 }),
      getCalibrationByAsset(90),
      getCalibrationByRegime(90),
    ]);
  } catch (err) {
    error = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "unknown";
  }

  if (error || !overall) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)] mb-3">Calibration</h1>
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          Calibration indisponible : {error ?? "données manquantes"}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
          Calibration · {overall.window_days} derniers jours
        </h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1 max-w-2xl">
          Track-record honnête du pipeline 4-pass. Score de Brier moyen sur les {overall.n_cards}{" "}
          cartes de session déjà réconciliées (cf.
          <em> services/brier.py</em>). Plus c&apos;est bas, mieux c&apos;est — 0 = parfait, 0,25 =
          pile/face, 1 = anti-parfait. Le score skill compare à la baseline 50/50 : positif = on bat
          le hasard.
        </p>
      </header>

      {/* Overall summary */}
      <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-5">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,400px)_1fr] gap-6 items-start">
          <div>
            <ReliabilityDiagram bins={overall.reliability} />
            <p className="mt-2 text-[11px] text-[var(--color-ichor-text-subtle)] leading-snug">
              Diagonale verte = parfaitement calibré. Bulles bleues = la fréquence réalisée dépasse
              la prédiction (sous-confiant). Bulles rouges = on prédit plus que ce qui s&apos;est
              passé (sur-confiant). Taille bulle = nombre de cartes dans le bin.
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <dt className="text-[var(--color-ichor-text-muted)]">Cartes réconciliées</dt>
            <dd className="text-[var(--color-ichor-text)] font-semibold">{overall.n_cards}</dd>
            <dt className="text-[var(--color-ichor-text-muted)]">Brier moyen</dt>
            <dd className="text-[var(--color-ichor-text)] font-semibold font-mono">
              {overall.mean_brier.toFixed(4)}
            </dd>
            <dt className="text-[var(--color-ichor-text-muted)]">Skill vs 50/50</dt>
            <dd>
              <span
                className={[
                  "inline-flex px-2 py-0.5 rounded text-xs font-medium border font-mono",
                  skillBadge(overall.skill_vs_naive),
                ].join(" ")}
              >
                {fmtSigned(overall.skill_vs_naive)}
              </span>
            </dd>
            <dt className="text-[var(--color-ichor-text-muted)]">Hits / misses</dt>
            <dd className="text-[var(--color-ichor-text)] font-mono">
              <span className="text-emerald-300">{overall.hits}</span>
              {" / "}
              <span className="text-red-300">{overall.misses}</span>
              <span className="text-[var(--color-ichor-text-subtle)] ml-2">
                ({overall.n_cards > 0 ? fmtPct(overall.hits / overall.n_cards) : "—"})
              </span>
            </dd>
          </dl>
        </div>
      </section>

      {/* Per-asset breakdown */}
      <section>
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3">Par actif</h2>
        {byAsset && byAsset.groups.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-[var(--color-ichor-border)]">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-ichor-surface)]/60 text-[var(--color-ichor-text-muted)] text-xs">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Actif</th>
                  <th className="px-3 py-2 text-right font-medium">Cartes</th>
                  <th className="px-3 py-2 text-right font-medium">Brier moyen</th>
                  <th className="px-3 py-2 text-right font-medium">Skill</th>
                  <th className="px-3 py-2 text-right font-medium">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {byAsset.groups.map((g) => (
                  <tr
                    key={g.group_key}
                    className="border-t border-[var(--color-ichor-border)] text-[var(--color-ichor-text)]"
                  >
                    <td className="px-3 py-2 font-mono">{g.group_key.replace(/_/g, "/")}</td>
                    <td className="px-3 py-2 text-right">{g.summary.n_cards}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {g.summary.mean_brier.toFixed(4)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span
                        className={[
                          "inline-flex px-1.5 py-0.5 rounded text-[11px] font-medium border font-mono",
                          skillBadge(g.summary.skill_vs_naive),
                        ].join(" ")}
                      >
                        {fmtSigned(g.summary.skill_vs_naive)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[var(--color-ichor-text-muted)]">
                      {g.summary.n_cards > 0 ? fmtPct(g.summary.hits / g.summary.n_cards, 0) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-ichor-text-subtle)]">
            Pas encore de carte réconciliée par actif sur la fenêtre.
          </p>
        )}
      </section>

      {/* Per-régime breakdown */}
      <section>
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3">Par régime</h2>
        {byRegime && byRegime.groups.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {byRegime.groups.map((g) => (
              <div
                key={g.group_key}
                className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-3"
              >
                <p className="text-xs text-[var(--color-ichor-text-muted)]">
                  {REGIME_LABEL[g.group_key] ?? g.group_key}
                </p>
                <p className="mt-1 text-lg font-semibold text-[var(--color-ichor-text)] font-mono">
                  {g.summary.mean_brier.toFixed(3)}
                </p>
                <div className="mt-1 flex items-baseline gap-2 text-[11px]">
                  <span
                    className={[
                      "inline-flex px-1.5 py-0.5 rounded font-medium border font-mono",
                      skillBadge(g.summary.skill_vs_naive),
                    ].join(" ")}
                  >
                    {fmtSigned(g.summary.skill_vs_naive)}
                  </span>
                  <span className="text-[var(--color-ichor-text-subtle)]">
                    {g.summary.n_cards} cartes
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-ichor-text-subtle)]">
            Pas encore de carte réconciliée par régime sur la fenêtre.
          </p>
        )}
      </section>
    </div>
  );
}
