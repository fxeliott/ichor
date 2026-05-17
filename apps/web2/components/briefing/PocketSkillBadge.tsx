/**
 * PocketSkillBadge — the system's HONEST self-assessment (ADR-099 2.2).
 *
 * Surfaces the Phase-D Vovk-AA aggregator's historical discrimination
 * skill for THIS asset's current-regime pocket (LIVE at /v1/phase-d/*
 * but never shown to the trader until now). `skill_delta` =
 * prod_predictor_weight − equal_weight_weight :
 *   > 0  the LLM forecaster has beaten a no-info baseline here
 *   < 0  ANTI-SKILL — historically WORSE than equal-weight (the famous
 *        EUR/usd_complacency n=13 case) → weight this read DOWN.
 *
 * Calibrated-refusal doctrine (the project's core philosophy): with a
 * SMALL sample the verdict is "calibration en cours, non concluant"
 * REGARDLESS of sign — we never over-claim skill on n=13. Directly
 * serves Eliot's verbatim "savoir si je dois prendre plus ou moins de
 * risque". ADR-017: pure calibration metadata, not an order.
 */

"use client";

import { m } from "motion/react";

import type { PocketSummary, PocketSummaryList } from "@/lib/api";

const _MIN_SIGNIFICANT_N = 30; // below this, sign is not conclusive
const _SKILL_EPS = 0.02; // |skill_delta| below this = neutral

function pickPocket(rows: PocketSummary[], regime: string | null): PocketSummary | null {
  if (rows.length === 0) return null;
  if (regime) {
    const match = rows.find((r) => r.regime === regime);
    if (match) return match;
  }
  // No current-regime pocket → the most-observed pocket for the asset.
  return rows.reduce((a, b) => (b.n_observations > a.n_observations ? b : a));
}

export function PocketSkillBadge({
  data,
  regime,
}: {
  data: PocketSummaryList | null;
  regime: string | null;
}) {
  const pocket = data ? pickPocket(data.rows, regime) : null;
  if (!pocket) return null;

  const exactRegime = regime !== null && pocket.regime === regime;
  const conclusive = pocket.n_observations >= _MIN_SIGNIFICANT_N;
  const sd = pocket.skill_delta;

  let verdict: string;
  let tone: string;
  if (!conclusive) {
    verdict = `Calibration en cours · n=${pocket.n_observations} — non concluant`;
    tone = "text-[--color-text-muted]";
  } else if (sd <= -_SKILL_EPS) {
    verdict = "Anti-skill historique — pondère ce biais à la baisse";
    tone = "text-[--color-bear]";
  } else if (sd >= _SKILL_EPS) {
    verdict = "Skill historique confirmé sur ce pocket";
    tone = "text-[--color-bull]";
  } else {
    verdict = "Skill neutre — pas d'edge historique mesurable";
    tone = "text-[--color-text-secondary]";
  }

  const drift = pocket.latest_drift_event_at
    ? new Date(pocket.latest_drift_event_at).toLocaleDateString("fr-FR", {
        timeZone: "Europe/Paris",
        day: "2-digit",
        month: "2-digit",
      })
    : null;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-[--color-border-subtle] px-6 py-4">
        <div>
          <h3 className="font-serif text-lg text-[--color-text-primary]">
            Calibration du système · pocket {pocket.regime}
          </h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            Vovk-AA · skill historique du forecaster vs baseline equal-weight
            {exactRegime ? "" : " · (régime courant non calibré — pocket le plus observé)"}
          </p>
        </div>
        {drift ? (
          <span className="rounded-full border border-[--color-bear]/40 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[--color-bear]">
            ⚠ drift régime · {drift}
          </span>
        ) : null}
      </header>

      <div className="px-6 py-5">
        <div className="flex items-end gap-4">
          <span
            className={`font-mono text-3xl font-semibold tabular-nums ${
              sd >= 0 ? "text-[--color-bull]" : "text-[--color-bear]"
            }`}
          >
            {sd >= 0 ? "+" : "−"}
            {Math.abs(sd).toFixed(3)}
          </span>
          <span className="pb-1 font-mono text-xs tabular-nums text-[--color-text-muted]">
            skill_delta · n={pocket.n_observations}
          </span>
        </div>
        <p className={`mt-2 text-sm ${tone}`}>{verdict}</p>
      </div>

      <dl className="grid grid-cols-3 gap-x-6 gap-y-2 border-t border-[--color-border-subtle]/60 px-6 py-4 text-sm">
        {[
          ["Predictor", pocket.prod_predictor_weight],
          ["Climatology", pocket.climatology_weight],
          ["Equal-weight", pocket.equal_weight_weight],
        ].map(([k, v]) => (
          <div key={k as string} className="flex flex-col">
            <dt className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">{k}</dt>
            <dd className="font-mono tabular-nums text-[--color-text-secondary]">
              {(v as number).toFixed(3)}
            </dd>
          </div>
        ))}
      </dl>

      <p className="border-t border-[--color-border-subtle]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Auto-évaluation de calibration (Vovk-AA) — contexte d&apos;honnêteté, pas un ordre (ADR-017)
      </p>
    </m.section>
  );
}
