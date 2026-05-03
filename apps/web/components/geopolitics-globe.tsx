/**
 * GeopoliticsGlobe — equirectangular world heatmap of GDELT events.
 *
 * Pure SVG, no globe lib. Each known country renders as a circle whose :
 *   - radius = log(event count) — visible from 1 event
 *   - color  = mean tone (-10 red ↔ 0 grey ↔ +10 green)
 *
 * Dot positions use plain (lon, lat) → (x, y) equirectangular projection.
 * Continent outlines are intentionally omitted — minimal viz, max signal.
 *
 * VISION_2026 delta Q.
 */

"use client";

import * as React from "react";
import { motion } from "motion/react";

interface CountryHotspot {
  country: string;
  count: number;
  mean_tone: number;
  most_negative_title: string | null;
}

export interface GeopoliticsGlobeProps {
  countries: CountryHotspot[];
  width?: number;
  height?: number;
}

// Country code (GDELT 2-letter) → (lat, lon, displayName).
// Restricted to the macro-relevant set ; unknown codes get dropped.
const COUNTRY_GEO: Record<string, [number, number, string]> = {
  US: [39, -98, "United States"],
  CN: [35, 105, "China"],
  RU: [60, 90, "Russia"],
  UK: [54, -2, "United Kingdom"],
  GB: [54, -2, "United Kingdom"],
  DE: [51, 10, "Germany"],
  FR: [46, 2, "France"],
  IT: [42, 12, "Italy"],
  ES: [40, -4, "Spain"],
  JP: [36, 138, "Japan"],
  KR: [37, 127, "South Korea"],
  IN: [21, 78, "India"],
  IL: [31, 35, "Israel"],
  IR: [32, 53, "Iran"],
  SA: [24, 45, "Saudi Arabia"],
  UA: [49, 32, "Ukraine"],
  TR: [39, 35, "Turkey"],
  BR: [-14, -52, "Brazil"],
  AR: [-34, -64, "Argentina"],
  ZA: [-30, 25, "South Africa"],
  EG: [27, 30, "Egypt"],
  AU: [-25, 133, "Australia"],
  CA: [56, -106, "Canada"],
  MX: [23, -102, "Mexico"],
  TW: [24, 121, "Taiwan"],
  HK: [22, 114, "Hong Kong"],
  SG: [1, 104, "Singapore"],
  CH: [47, 8, "Switzerland"],
  NL: [52, 5, "Netherlands"],
  PL: [52, 19, "Poland"],
  SE: [60, 18, "Sweden"],
  NO: [60, 9, "Norway"],
};

const project = (
  lon: number,
  lat: number,
  width: number,
  height: number
): [number, number] => {
  const x = ((lon + 180) / 360) * width;
  const y = ((90 - lat) / 180) * height;
  return [x, y];
};

const toneToColor = (tone: number): string => {
  // Clamp tone to [-6, 6], map to red-grey-emerald
  const t = Math.max(-6, Math.min(6, tone));
  if (t < 0) {
    // red interpolation
    const f = -t / 6;
    return `rgba(248, 113, 113, ${0.4 + 0.5 * f})`;
  }
  if (t > 0) {
    const f = t / 6;
    return `rgba(52, 211, 153, ${0.4 + 0.5 * f})`;
  }
  return "rgba(163, 163, 163, 0.5)";
};

const radius = (count: number): number => 4 + Math.min(20, Math.log2(count + 1) * 4);

export const GeopoliticsGlobe: React.FC<GeopoliticsGlobeProps> = ({
  countries,
  width = 800,
  height = 380,
}) => {
  const [focus, setFocus] = React.useState<string | null>(null);

  const points = React.useMemo(() => {
    return countries
      .map((c) => {
        const geo = COUNTRY_GEO[c.country];
        if (!geo) return null;
        const [lat, lon, label] = geo;
        const [x, y] = project(lon, lat, width, height);
        return {
          ...c,
          x,
          y,
          label,
        };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null);
  }, [countries, width, height]);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
      <div className="relative" style={{ height }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label="Carte géopolitique GDELT — densité d'événements par pays"
        >
          {/* Faint grid for orientation */}
          {[0.25, 0.5, 0.75].map((f) => (
            <React.Fragment key={f}>
              <line
                x1={0}
                y1={height * f}
                x2={width}
                y2={height * f}
                stroke="rgba(64,64,64,0.4)"
                strokeDasharray="2 6"
              />
              <line
                x1={width * f}
                y1={0}
                x2={width * f}
                y2={height}
                stroke="rgba(64,64,64,0.4)"
                strokeDasharray="2 6"
              />
            </React.Fragment>
          ))}
          {/* Equator label */}
          <text
            x={4}
            y={height / 2 - 4}
            fontSize={10}
            fill="rgba(115,115,115,0.7)"
          >
            équateur
          </text>

          {/* Country dots */}
          {points.map((p, i) => {
            const dimmed = focus !== null && focus !== p.country;
            return (
              <motion.g
                key={p.country}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: dimmed ? 0.25 : 1 }}
                transition={{ delay: i * 0.02, duration: 0.3 }}
                style={{ cursor: "pointer" }}
                onMouseEnter={() => setFocus(p.country)}
                onMouseLeave={() => setFocus(null)}
              >
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={radius(p.count)}
                  fill={toneToColor(p.mean_tone)}
                  stroke="rgba(255,255,255,0.4)"
                />
                {(p.count > 5 || focus === p.country) && (
                  <text
                    x={p.x}
                    y={p.y - radius(p.count) - 4}
                    textAnchor="middle"
                    fontSize={11}
                    fill="rgba(229, 229, 229, 0.95)"
                    fontFamily="ui-monospace, SFMono-Regular, monospace"
                    pointerEvents="none"
                  >
                    {p.country}
                  </text>
                )}
              </motion.g>
            );
          })}
        </svg>
      </div>

      {/* Legend + focused country detail */}
      <div className="mt-3 flex items-center justify-between gap-4 flex-wrap text-[11px]">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-rose-400/80" />
            <span className="text-neutral-400">tone négatif</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-neutral-400/60" />
            <span className="text-neutral-400">neutre</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-full bg-emerald-400/80" />
            <span className="text-neutral-400">positif</span>
          </span>
          <span className="text-neutral-500 italic">
            taille = nb d&apos;événements
          </span>
        </div>
        {focus && (() => {
          const c = countries.find((x) => x.country === focus);
          if (!c) return null;
          return (
            <p className="text-neutral-300 max-w-md text-right">
              <span className="font-mono">{c.country}</span> · {c.count} évts ·
              tone {c.mean_tone >= 0 ? "+" : ""}
              {c.mean_tone.toFixed(2)}
              {c.most_negative_title && (
                <span className="block text-neutral-500 italic line-clamp-1">
                  “{c.most_negative_title}”
                </span>
              )}
            </p>
          );
        })()}
      </div>
    </div>
  );
};
