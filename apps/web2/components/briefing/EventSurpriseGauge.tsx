/**
 * EventSurpriseGauge — anticipation-vs-surprise reading (ADR-099 2.3).
 *
 * Crosses the top high-impact calendar catalyst with the asset's
 * prediction-market narrative backdrop into a calibrated "how much
 * RESIDUAL surprise potential" gauge. Pure presentational — all logic
 * is `deriveEventSurprise` in lib/eventSurprise.ts (the synthesis
 * SSOT). Renders nothing when there is no catalyst at the horizon
 * (honest absence — the rest of the briefing still stands).
 *
 * HONEST by construction (r88 lesson) : it never claims a prediction
 * market prices the specific data print — it presents two explicitly
 * separate axes (calendar consensus substrate × narrative backdrop)
 * and their qualitative cross. ADR-017 : pure pre-trade context,
 * explicitly NOT an order, NOT sizing.
 */

"use client";

import { m } from "motion/react";

import type { EventReading, EventSurpriseSummary } from "@/lib/eventSurprise";

const IMPACT_DOT: Record<EventSurpriseSummary["catalyst"]["impact"], string> = {
  high: "bg-[--color-alert]",
  medium: "bg-[--color-warn]",
  low: "bg-[--color-text-muted]",
};

const IMPACT_LABEL: Record<EventSurpriseSummary["catalyst"]["impact"], string> = {
  high: "HAUT",
  medium: "MOYEN",
  low: "BAS",
};

interface Zone {
  key: EventReading;
  label: string;
  text: string;
  fill: string;
  ring: string;
}

// Left → right = escalating attention : anticipated → partial → surprise.
const ZONES: Zone[] = [
  {
    key: "priced_in",
    label: "Anticipé",
    text: "text-[--color-bull]",
    fill: "bg-[--color-bull]/15",
    ring: "ring-[--color-bull]/40",
  },
  {
    key: "mixed",
    label: "Partiel",
    text: "text-[--color-text-secondary]",
    fill: "bg-[--color-text-muted]/10",
    ring: "ring-[--color-border-default]",
  },
  {
    key: "surprise_risk",
    label: "Surprise",
    text: "text-[--color-warn]",
    fill: "bg-[--color-warn]/15",
    ring: "ring-[--color-warn]/40",
  },
];

const WEEKDAY_FR = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];

function fmtWhen(isoDate: string, timeUtc: string | null): string {
  const [y, mo, d] = isoDate.split("-").map(Number);
  if (!y || !mo || !d) return timeUtc ? `${isoDate} ${timeUtc} UTC` : isoDate;
  const dt = new Date(Date.UTC(y, mo - 1, d));
  const day = `${WEEKDAY_FR[dt.getUTCDay()]} ${d}/${String(mo).padStart(2, "0")}`;
  return timeUtc ? `${day} · ${timeUtc} UTC` : day;
}

export function EventSurpriseGauge({
  data,
  assetPair,
}: {
  data: EventSurpriseSummary | null;
  assetPair: string;
}) {
  if (!data) return null;

  const activeIdx = ZONES.findIndex((z) => z.key === data.reading);
  const active = ZONES[activeIdx] ?? ZONES[1]!;
  const dom =
    data.market.impliedYes === null
      ? null
      : Math.round(
          (data.market.impliedYes >= 0.5 ? data.market.impliedYes : 1 - data.market.impliedYes) *
            100,
        );

  const marketLine =
    data.market.source === "none"
      ? `Aucun thème de marché de prédiction matériel pour ${assetPair}`
      : `Backdrop prédiction : ${data.market.label} · ${
          data.market.nMarkets ?? 0
        } marché${(data.market.nMarkets ?? 0) > 1 ? "s" : ""} · issue dominante ~${dom}%${
          data.market.impactOnAsset !== null
            ? ` · impact ${assetPair} ${
                data.market.impactOnAsset >= 0 ? "+" : "−"
              }${Math.abs(data.market.impactOnAsset).toFixed(2)}`
            : ""
        }`;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Anticipation vs surprise</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Catalyseur calendrier × backdrop marché de prédiction · potentiel de surprise résiduel
        </p>
      </header>

      {/* 3-zone gauge — escalating attention left→right */}
      <div className="px-6 pt-5">
        <div className="flex gap-1.5">
          {ZONES.map((z, i) => {
            const on = i === activeIdx;
            return (
              <div
                key={z.key}
                className={`flex-1 rounded-lg px-3 py-2 text-center ring-1 transition-colors ${
                  on
                    ? `${z.fill} ${z.ring}`
                    : "bg-[--color-bg-base]/30 ring-[--color-border-subtle]/50"
                }`}
              >
                <span
                  className={`font-mono text-[10px] uppercase tracking-widest ${
                    on ? z.text : "text-[--color-text-muted]"
                  }`}
                >
                  {z.label}
                </span>
              </div>
            );
          })}
        </div>
        <p className={`mt-3 font-serif text-base ${active.text}`}>{data.headline}</p>
        <p className="mt-1 text-sm leading-relaxed text-[--color-text-secondary]">{data.detail}</p>
      </div>

      {/* Catalyst row */}
      <div className="mt-4 flex items-start gap-3 border-t border-[--color-border-subtle]/60 px-6 py-4">
        <span
          className={`mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full ${IMPACT_DOT[data.catalyst.impact]}`}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-medium text-[--color-text-primary]">
              {data.catalyst.label}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-wider text-[--color-text-muted]">
              {data.catalyst.region} · {IMPACT_LABEL[data.catalyst.impact]}
              {data.catalyst.forAsset ? "" : " · marché-large"}
            </span>
          </div>
          <p className="mt-0.5 font-mono text-[11px] tabular-nums text-[--color-text-muted]">
            {fmtWhen(data.catalyst.when, data.catalyst.whenTimeUtc)} ·{" "}
            {data.consensus.forecast
              ? `attendu ${data.consensus.forecast}${
                  data.consensus.previous ? ` (préc. ${data.consensus.previous})` : ""
                }`
              : "lecture qualitative"}
          </p>
        </div>
      </div>

      <p className="border-t border-[--color-border-subtle]/60 px-6 py-3 text-xs text-[--color-text-secondary]">
        {marketLine}
      </p>

      <p className="border-t border-[--color-border-subtle]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Lecture anticipation vs surprise — contexte pré-trade, pas un ordre (ADR-017)
      </p>
    </m.section>
  );
}
