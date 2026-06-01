"use client";

/**
 * StirPanel — mission-7 — surfaces the market-implied Fed-funds path that was
 * previously buried in Pass-2 markdown. Renders the ZQ-futures implied EFFR
 * curve (front month → Jan-2027), the cumulative basis points priced vs the
 * front month per contract, and the ~5-session repricing delta (the actual
 * anticipation signal). Data via the page-level SSR `getStir()` fetch (prop),
 * mirroring DxyCorrelationPanel's thin-view contract.
 *
 * ADR-017 : market-implied path, NOT a forecast and NOT a trade signal — the
 * footer + backend note say so explicitly. No directional vocabulary.
 */

import { m } from "motion/react";

import type { StirData } from "@/lib/api";

const BAR_W = 240;
const BAR_H = 8;
// Minimum full-scale (bp). The ACTUAL scale grows to the curve's widest |cum|
// (computed per-render), so a deep easing cycle (e.g. −150 bp by the horizon)
// never clips to the bar edge — the floor only stops a tiny curve from looking
// exaggerated.
const BAR_BP_MIN_FULLSCALE = 40;

const TONE_FR: Record<string, string> = {
  easing_priced: "Assouplissement pricé",
  tightening_priced: "Resserrement pricé",
  flat: "Statu quo pricé",
};
const TONE_TOKEN: Record<string, string> = {
  easing_priced: "var(--color-accent-bull)",
  tightening_priced: "var(--color-accent-bear)",
  flat: "var(--color-text-muted)",
};

function bpBar(
  bps: number | null,
  fullscale: number,
): { x: number; w: number; token: string } | null {
  if (bps === null || Number.isNaN(bps)) return null;
  const half = BAR_W / 2;
  const frac = Math.max(-1, Math.min(1, bps / fullscale));
  const w = Math.abs(frac) * half;
  // Negative bps = easing priced (rates lower) → extend LEFT (bull token).
  const x = frac >= 0 ? half : half - w;
  const token = frac < 0 ? "var(--color-accent-bull)" : "var(--color-accent-bear)";
  return { x, w, token };
}

function fmtBps(bps: number | null): string {
  if (bps === null || Number.isNaN(bps)) return "—";
  return `${bps >= 0 ? "+" : "−"}${Math.abs(bps).toFixed(0)} pb`;
}

interface Props {
  stir: StirData | null;
}

export function StirPanel({ stir }: Props) {
  if (!stir || stir.front_implied_effr === null) {
    return (
      <m.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-6 py-8 text-center text-sm text-[var(--color-text-muted)] backdrop-blur-xl"
        role="region"
        aria-label="Trajectoire Fed implicite"
      >
        Trajectoire des taux Fed indisponible — le collecteur des futures sur les taux Fed n'a pas
        encore de données fraîches.
      </m.section>
    );
  }

  const tone = stir.tone ?? "flat";
  const cuts = stir.cuts_priced_to_horizon;
  const cutsLabel =
    cuts !== null && Math.abs(cuts) >= 0.2
      ? `${Math.abs(cuts).toFixed(1)} ${cuts > 0 ? "baisses" : "hausses"} de 25 pb`
      : "trajectoire quasi-plate";
  // Dynamic bar scale = widest |cum bp| in the curve (floored), so the bars
  // never clip on a deep easing/tightening cycle (code-review RED-2).
  const barScale = Math.max(
    BAR_BP_MIN_FULLSCALE,
    ...stir.points.map((p) => Math.abs(p.cum_bps_vs_front ?? 0)),
  );

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      role="region"
      aria-labelledby="stir-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h3
            id="stir-heading"
            className="font-serif text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Trajectoire Fed implicite
          </h3>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            marché des taux Fed · futures sur les taux Fed
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span
            className="rounded-sm px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide"
            style={{ color: TONE_TOKEN[tone] ?? "var(--color-text-muted)" }}
          >
            {TONE_FR[tone] ?? "—"}
          </span>
          {stir.policy_rate_effr !== null && (
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              EFFR {stir.policy_rate_effr.toFixed(2)} %
            </span>
          )}
          {stir.horizon_label && (
            <span className="font-mono text-xs text-[var(--color-text-secondary)] tabular-nums">
              → {stir.horizon_label} : {fmtBps(stir.net_bps_to_horizon)} ({cutsLabel})
            </span>
          )}
        </div>
      </header>

      <ul className="divide-y divide-[var(--color-border-subtle)]">
        {stir.points.map((p) => {
          const bar = bpBar(p.cum_bps_vs_front, barScale);
          const reprice = p.repricing_bps;
          const showReprice = reprice !== null && Math.abs(reprice) >= 0.5;
          const repriceDown = reprice !== null && reprice < 0;
          return (
            <li key={p.series_id} className="px-6 py-2.5">
              <div className="flex items-center justify-between gap-4">
                <span className="font-mono text-sm text-[var(--color-text-secondary)]">
                  {p.month_label}
                </span>
                <div className="flex items-baseline gap-3 tabular-nums">
                  <span className="font-mono text-sm text-[var(--color-text-primary)]">
                    {p.implied_effr !== null ? `${p.implied_effr.toFixed(3)} %` : "—"}
                  </span>
                  <span className="w-16 text-right font-mono text-xs text-[var(--color-text-muted)]">
                    {fmtBps(p.cum_bps_vs_front)}
                  </span>
                  {showReprice && (
                    <span
                      className="font-mono text-[10px] uppercase tracking-wide"
                      style={{
                        color: repriceDown
                          ? "var(--color-accent-bull)"
                          : "var(--color-accent-bear)",
                      }}
                      aria-label={`Repricing 5 séances ${fmtBps(reprice)}`}
                    >
                      {repriceDown ? "▼" : "▲"} {fmtBps(reprice)}/5j
                    </span>
                  )}
                </div>
              </div>
              <svg
                viewBox={`0 0 ${BAR_W} ${BAR_H}`}
                preserveAspectRatio="none"
                className="mt-1.5 h-2 w-full"
                aria-hidden="true"
              >
                <line
                  x1={BAR_W / 2}
                  x2={BAR_W / 2}
                  y1={0}
                  y2={BAR_H}
                  stroke="var(--color-border-subtle)"
                  strokeWidth={1}
                />
                {bar && <rect x={bar.x} y={0} width={bar.w} height={BAR_H} fill={bar.token} />}
              </svg>
            </li>
          );
        })}
      </ul>

      {stir.meetings.some((mt) => mt.implied_change_bps !== null) && (
        <div className="border-t border-[var(--color-border-subtle)] px-6 py-4">
          <h4 className="mb-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Par réunion FOMC · probabilités implicites (CME FedWatch)
          </h4>
          <ul className="space-y-2.5">
            {stir.meetings.map((mt) => {
              const chg = mt.implied_change_bps;
              if (chg === null) return null;
              const pCut = Math.round((mt.p_cut ?? 0) * 100);
              const pHold = Math.round((mt.p_hold ?? 0) * 100);
              const pHike = Math.round((mt.p_hike ?? 0) * 100);
              const verdict =
                pCut >= 50
                  ? `baisse ${pCut} %`
                  : pHike >= 50
                    ? `hausse ${pHike} %`
                    : `maintien ${pHold} %`;
              return (
                <li key={mt.label} className="flex items-center gap-3">
                  <span className="w-20 font-mono text-xs text-[var(--color-text-secondary)]">
                    {mt.label}
                  </span>
                  <div
                    className="flex h-2 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-base)]"
                    role="img"
                    aria-label={`${mt.label} : baisse ${pCut} %, maintien ${pHold} %, hausse ${pHike} %`}
                  >
                    <div style={{ width: `${pCut}%`, background: "var(--color-accent-bull)" }} />
                    <div style={{ width: `${pHold}%`, background: "var(--color-text-muted)" }} />
                    <div style={{ width: `${pHike}%`, background: "var(--color-accent-bear)" }} />
                  </div>
                  <span className="w-32 text-right font-mono text-[11px] tabular-nums text-[var(--color-text-secondary)]">
                    {fmtBps(chg)} · {verdict}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[10px] leading-relaxed text-[var(--color-text-muted)]">
            Baisse (vert) / maintien (gris) / hausse (rouge), pricées par les futures sur les taux
            Fed — pas une prévision.
          </p>
        </div>
      )}

      {stir.note && (
        <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-xs leading-relaxed text-[var(--color-text-secondary)]">
          {stir.note}
        </p>
      )}

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        trajectoire anticipée par le marché monétaire · contexte d&apos;aide à la décision, pas un
        signal d&apos;achat ou de vente
      </p>
    </m.section>
  );
}
