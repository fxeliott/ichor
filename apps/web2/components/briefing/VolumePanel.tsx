/**
 * VolumePanel — intraday market-activity microchart (ADR-099 Tier 1.1).
 *
 * Eliot's "volume" axis. Hand-rolled SSR-safe SVG (no charting dep, no
 * ResizeObserver — fixed viewBox, RSC-clean per the r72 web-research).
 * Volume bars from a true 0 baseline (no truncated axis) tinted by the
 * bar's own up/down close, with a thin close-price polyline overlay so
 * activity is read against price.
 *
 * HONESTY (web-research + ADR-093 degraded-explicit + Eliot "marche
 * exactement") : the `volume` field is a Polygon tick/aggregate ACTIVITY
 * proxy. Real FX volume does not exist (decentralised market) ; index
 * "volume" is a proxy too. The panel says so — it never claims true
 * exchange volume. On weekends/holidays the last bar is Friday's close ;
 * a "marché fermé" badge surfaces the staleness instead of a misleading
 * flat live chart.
 *
 * ADR-017 : pure descriptive activity. No bias, no BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { IntradayBarOut } from "@/lib/api";

const PARIS = "Europe/Paris";

function parisLabel(epochSec: number, withDay = false): string {
  const d = new Date(epochSec * 1000);
  return d.toLocaleString("fr-FR", {
    timeZone: PARIS,
    ...(withDay ? { weekday: "short", day: "2-digit", month: "2-digit" } : {}),
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function VolumePanel({ asset, bars }: { asset: string; bars: IntradayBarOut[] }) {
  const usable = bars.filter((b) => typeof b.volume === "number" && b.volume >= 0);

  if (usable.length < 2) {
    return (
      <m.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
      >
        <header className="border-b border-[--color-border-subtle] px-6 py-4">
          <h3 className="font-serif text-lg text-[--color-text-primary]">
            Activité (volume proxy)
          </h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            Aucune barre intraday disponible — marché fermé ou source en attente.
          </p>
        </header>
        <p className="px-6 py-8 text-center text-sm text-[--color-text-muted]">
          Pas d&apos;activité récente pour {asset.replace("_", "/")}.
        </p>
      </m.section>
    );
  }

  const last = usable[usable.length - 1]!;
  const vols = usable.map((b) => b.volume as number);
  const maxVol = Math.max(...vols, 1);
  const avgVol = vols.reduce((s, v) => s + v, 0) / vols.length;
  const closes = usable.map((b) => b.close);
  const pMin = Math.min(...closes);
  const pMax = Math.max(...closes);
  const pSpan = pMax - pMin || 1;

  // Staleness: last bar older than ~2h ⇒ market closed (weekend/holiday).
  const ageMin = (Date.now() - last.time * 1000) / 60000;
  const closed = ageMin > 120;

  // SVG geometry — fixed viewBox, no client measurement.
  const W = 640;
  const H = 150;
  const PAD_B = 18;
  const volH = H - PAD_B;
  const n = usable.length;
  const slot = W / n;
  const barW = Math.max(1, slot * 0.62);

  const pricePts = usable
    .map((b, i) => {
      const x = i * slot + slot / 2;
      const y = volH - ((b.close - pMin) / pSpan) * (volH * 0.78) - volH * 0.11;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const desc = `Activité intraday ${asset.replace("_", "/")} : ${n} barres, volume proxy moyen ${avgVol.toFixed(0)}, max ${maxVol.toFixed(0)}, dernière ${parisLabel(last.time, true)} (heure de Paris).`;

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
            Activité (volume proxy)
          </h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            Agrégat tick Polygon · le volume réel FX n&apos;existe pas (marché décentralisé) · ligne
            = prix de clôture
          </p>
        </div>
        {closed ? (
          <span className="rounded-full border border-[--color-border-default] px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[--color-text-muted]">
            Marché fermé · dernière {parisLabel(last.time, true)}
          </span>
        ) : (
          <span className="rounded-full border border-[--color-bull]/40 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[--color-bull]">
            Session active
          </span>
        )}
      </header>

      <div className="px-4 pt-4">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={desc}
          className="h-40 w-full"
        >
          <title>{`Activité ${asset.replace("_", "/")}`}</title>
          <desc>{desc}</desc>
          <line
            x1="0"
            y1={volH}
            x2={W}
            y2={volH}
            stroke="var(--color-border-default)"
            strokeWidth="1"
          />
          {usable.map((b, i) => {
            const v = b.volume as number;
            const h = (v / maxVol) * (volH * 0.92);
            const x = i * slot + (slot - barW) / 2;
            const up = b.close >= b.open;
            return (
              <m.rect
                key={b.time}
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.85 }}
                transition={{ duration: 0.25, delay: Math.min(i * 0.003, 0.6) }}
                x={x.toFixed(1)}
                y={(volH - h).toFixed(1)}
                width={barW.toFixed(1)}
                height={Math.max(0.5, h).toFixed(1)}
                rx="0.5"
                fill={up ? "var(--color-bull)" : "var(--color-bear)"}
              />
            );
          })}
          <m.polyline
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.7 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            points={pricePts}
            fill="none"
            stroke="var(--color-text-secondary)"
            strokeWidth="1.25"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 px-6 py-4 text-sm sm:grid-cols-4">
        {[
          ["Dernière", `${(last.volume as number).toFixed(0)}`],
          ["Moyenne", `${avgVol.toFixed(0)}`],
          ["Max", `${maxVol.toFixed(0)}`],
          ["Fenêtre", `${parisLabel(usable[0]!.time)}→${parisLabel(last.time)}`],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col">
            <dt className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">{k}</dt>
            <dd className="font-mono tabular-nums text-[--color-text-secondary]">{v}</dd>
          </div>
        ))}
      </dl>
    </m.section>
  );
}
