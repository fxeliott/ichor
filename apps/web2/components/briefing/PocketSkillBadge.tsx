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
import type { ReactElement } from "react";

import type { PocketSummaryList } from "@/lib/api";
// r143 doctrine #4 SSOT — pre-r143 the thresholds + pickPocket were
// inlined here ; ConvictionGroundingPanel 4th tile (r142+r143 YELLOW-2)
// also needs them so we extracted to lib/pocketSkill.ts. Drift between
// consumers is CI-pinned by `test_r143_pocket_skill_constants_pinned`.
import { classifyPocketSkill, pickPocketForRegime } from "@/lib/pocketSkill";

export function PocketSkillBadge({
  data,
  regime,
}: {
  data: PocketSummaryList | null;
  regime: string | null;
}): ReactElement | null {
  const pocket = pickPocketForRegime(data?.rows ?? null, regime);
  if (!pocket) return null;

  const exactRegime = regime !== null && pocket.regime === regime;
  const sd = pocket.skill_delta;
  const skillVerdict = classifyPocketSkill(sd, pocket.n_observations);

  let verdict: string;
  let tone: string;
  if (skillVerdict === "non_conclusive") {
    verdict = `Pas encore assez de recul · ${pocket.n_observations} cas observés — à confirmer`;
    tone = "text-[var(--color-text-muted)]";
  } else if (skillVerdict === "anti_skill") {
    verdict = "Ce type de lecture s'est souvent trompé par le passé — à prendre avec prudence";
    tone = "text-[var(--color-bear)]";
  } else if (skillVerdict === "high_skill") {
    verdict = "Ce type de lecture a fait ses preuves dans ce contexte";
    tone = "text-[var(--color-bull)]";
  } else {
    verdict = "Fiabilité moyenne — pas d'avantage historique mesurable";
    tone = "text-[var(--color-text-secondary)]";
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
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div>
          <h3 className="font-serif text-lg text-[var(--color-text-primary)]">
            À quel point se fier à ce verdict
          </h3>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Fiabilité historique de ce type de lecture dans ce contexte
            {exactRegime ? "" : " · (contexte du jour peu observé — référence la plus proche)"}
          </p>
        </div>
        {drift ? (
          <span className="rounded-full border border-[var(--color-bear)]/40 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[var(--color-bear)]">
            ⚠ changement de contexte · {drift}
          </span>
        ) : null}
      </header>

      <div className="px-6 py-5">
        <div className="flex items-end gap-4">
          <span
            className={`font-mono text-3xl font-semibold tabular-nums ${
              sd >= 0 ? "text-[var(--color-bull)]" : "text-[var(--color-bear)]"
            }`}
          >
            {sd >= 0 ? "+" : "−"}
            {Math.abs(sd).toFixed(3)}
          </span>
          <span className="pb-1 font-mono text-xs tabular-nums text-[var(--color-text-muted)]">
            avantage historique · {pocket.n_observations} cas observés
          </span>
        </div>
        <p className={`mt-2 text-sm ${tone}`}>{verdict}</p>
      </div>

      <dl className="grid grid-cols-3 gap-x-6 gap-y-2 border-t border-[var(--color-border-subtle)]/60 px-6 py-4 text-sm">
        {[
          ["Analyse du jour", pocket.prod_predictor_weight],
          ["Historique moyen", pocket.climatology_weight],
          ["Hasard (référence)", pocket.equal_weight_weight],
        ].map(([k, v]) => (
          <div key={k as string} className="flex flex-col">
            <dt className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              {k}
            </dt>
            <dd className="font-mono tabular-nums text-[var(--color-text-secondary)]">
              {(v as number).toFixed(3)}
            </dd>
          </div>
        ))}
      </dl>

      <p className="border-t border-[var(--color-border-subtle)]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Fiabilité historique en toute transparence — contexte d&apos;aide à la décision, pas un
        signal d&apos;achat ou de vente
      </p>
    </m.section>
  );
}
