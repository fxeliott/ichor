/**
 * InstitutionalPositioningPanel — CFTC "acteurs du marché" (ADR-099 1.4b).
 *
 * The smart-money half of Eliot's positioning axis (distinct from the
 * MyFXBook RETAIL contrarian panel). Surfaces the SAME institutional
 * read the 4-pass LLM sees (data_pool._section_tff_positioning /
 * _section_cot) via /v1/positioning/institutional.
 *
 *  - TFF : 4-class net positions (Dealer / AssetMgr / LevFunds / Other),
 *    diverging bars from a true 0 (net long = bull/right, net short =
 *    bear/left), Δw/w, + the descriptive smart-money-divergence flag
 *    (LevFunds vs AssetMgr opposite sides).
 *  - COT : managed-money net + 1w/4w/12w trend + accelerating/reversal
 *    pattern (null for assets the COT collector doesn't cover — honest
 *    "non couvert", ADR-093 degraded-explicit, not a scary error).
 *
 * Honest: CFTC is weekly, data cut-off Tuesday — a `report_date`
 * staleness badge surfaces the lag (no fake freshness). ADR-017: pure
 * positioning facts + a descriptive divergence flag, no BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { InstitutionalPositioning } from "@/lib/api";

const NF = new Intl.NumberFormat("fr-FR");

function signed(n: number): string {
  return `${n >= 0 ? "+" : "−"}${NF.format(Math.abs(n))}`;
}

function deltaLabel(d: number | null): string {
  return d === null ? "" : ` (Δw ${signed(d)})`;
}

export function InstitutionalPositioningPanel({ data }: { data: InstitutionalPositioning | null }) {
  if (!data || (data.tff === null && data.cot === null)) {
    return (
      <m.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
      >
        <header className="border-b border-[--color-border-subtle] px-6 py-4">
          <h3 className="font-serif text-lg text-[--color-text-primary]">
            Positionnement institutionnel
          </h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            CFTC TFF / COT — non disponible pour cet actif.
          </p>
        </header>
        <p className="px-6 py-8 text-center text-sm text-[--color-text-muted]">
          Pas de données CFTC pour {data?.asset ?? "cet actif"}.
        </p>
      </m.section>
    );
  }

  const { tff, cot } = data;
  const tffRows = tff
    ? ([
        ["Dealer", tff.dealer_net, tff.dealer_dw],
        ["Asset Mgr", tff.asset_mgr_net, tff.asset_mgr_dw],
        ["Lev Funds", tff.lev_money_net, tff.lev_money_dw],
        ["Other", tff.other_net, null],
      ] as const)
    : [];
  const tffMax = tffRows.length ? Math.max(...tffRows.map(([, n]) => Math.abs(n)), 1) : 1;

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
            Positionnement institutionnel
          </h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            CFTC · net long (+) / short (−) en contrats · {data.cadence}
          </p>
        </div>
        <span className="rounded-full border border-[--color-border-default] px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[--color-text-muted]">
          Rapport {tff?.report_date ?? cot?.report_date}
        </span>
      </header>

      {tff ? (
        <div className="border-b border-[--color-border-subtle]/60 px-6 py-4">
          <p className="mb-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            TFF 4 classes · OI {NF.format(tff.open_interest)}
          </p>
          <ul className="space-y-2.5">
            {tffRows.map(([label, net, dw], i) => {
              const pos = net >= 0;
              const magPct = Math.min((Math.abs(net) / tffMax) * 100, 100);
              return (
                <m.li
                  key={label}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2, delay: i * 0.05 }}
                  className="flex items-center gap-3"
                >
                  <span className="w-20 shrink-0 font-mono text-xs text-[--color-text-secondary]">
                    {label}
                  </span>
                  <div className="relative h-2 flex-1">
                    <div className="absolute left-1/2 top-0 h-full w-px bg-[--color-border-default]" />
                    <m.div
                      initial={{ width: 0 }}
                      animate={{ width: `${magPct / 2}%` }}
                      transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 + i * 0.05 }}
                      className={`absolute top-0 h-full rounded-full ${
                        pos ? "left-1/2 bg-[--color-bull]" : "right-1/2 bg-[--color-bear]"
                      }`}
                    />
                  </div>
                  <span
                    className={`w-40 shrink-0 text-right font-mono text-xs tabular-nums ${
                      pos ? "text-[--color-bull]" : "text-[--color-bear]"
                    }`}
                  >
                    {signed(net)}
                    <span className="text-[--color-text-muted]">{deltaLabel(dw)}</span>
                  </span>
                </m.li>
              );
            })}
          </ul>
          {tff.smart_money_divergence ? (
            <p className="mt-3 rounded-lg border border-[--color-bear]/40 px-3 py-2 text-xs text-[--color-bear]">
              ⚠ Divergence smart-money : Lev Funds et Asset Mgr à contre-sens — lecture
              institutionnelle non consensuelle (contexte, pas un ordre).
            </p>
          ) : null}
        </div>
      ) : null}

      {cot ? (
        <div className="px-6 py-4">
          <p className="mb-2 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            COT Disaggregated · pattern&nbsp;
            <span
              className={
                cot.pattern === "reversal"
                  ? "text-[--color-bear]"
                  : cot.pattern === "accelerating"
                    ? "text-[--color-text-secondary]"
                    : "text-[--color-text-muted]"
              }
            >
              {cot.pattern}
            </span>
          </p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
            {[
              ["Managed money", signed(cot.managed_money_net)],
              ["Swap dealer", signed(cot.swap_dealer_net)],
              ["Producer", signed(cot.producer_net)],
              ["Δ 1 sem.", cot.delta_1w === null ? "—" : signed(cot.delta_1w)],
              ["Δ 4 sem.", cot.delta_4w === null ? "—" : signed(cot.delta_4w)],
              ["Δ 12 sem.", cot.delta_12w === null ? "—" : signed(cot.delta_12w)],
            ].map(([k, v]) => (
              <div key={k} className="flex flex-col">
                <dt className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
                  {k}
                </dt>
                <dd className="font-mono tabular-nums text-[--color-text-secondary]">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <p className="px-6 py-3 text-xs text-[--color-text-muted]">
          COT Disaggregated : non couvert pour cet actif (TFF ci-dessus reste la lecture
          institutionnelle de référence).
        </p>
      )}
    </m.section>
  );
}
