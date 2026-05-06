// /geopolitics — globe + GPR (Geopolitical Risk Index) + GDELT events.
//
// Cf SPEC.md §5 Phase A item #10 + delta Q VISION_2026 (upgrade
// react-globe.gl 3D).
//
// Live: GET /v1/geopolitics/heatmap?hours=24 → per-country event count +
// mean tone + worst headline. The hardcoded HOTSPOTS map (with lat/lon)
// stays mock until a country→coords resolver lands ; the live data is
// surfaced in a "Top countries by GDELT activity" panel + the header
// pill counters.
//
// Recent GDELT events table remains illustrative until /v1/geopolitics
// exposes a per-event endpoint (currently aggregates only).

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type GeopoliticsHeatmap } from "@/lib/api";

interface Hotspot {
  id: string;
  region: string;
  lat: number;
  lon: number;
  intensity: number; // 0..1
  events_24h: number;
}

const HOTSPOTS: Hotspot[] = [
  { id: "ukr", region: "Ukraine ↔ Russia", lat: 49, lon: 32, intensity: 0.72, events_24h: 18 },
  { id: "isr", region: "Israel ↔ Lebanon", lat: 33, lon: 35, intensity: 0.61, events_24h: 12 },
  { id: "kor", region: "Korean Peninsula", lat: 38, lon: 127, intensity: 0.32, events_24h: 4 },
  { id: "tw", region: "Taiwan Strait", lat: 23.5, lon: 121, intensity: 0.41, events_24h: 6 },
  { id: "sah", region: "Sahel (Mali/Burkina)", lat: 14, lon: 0, intensity: 0.28, events_24h: 3 },
  { id: "myr", region: "Myanmar", lat: 21, lon: 96, intensity: 0.24, events_24h: 2 },
];

interface GdeltEvent {
  ts: string;
  actor1: string;
  actor2: string;
  goldstein: number; // -10..+10
  tone: number; // -100..+100
  url: string;
}

const RECENT_EVENTS: GdeltEvent[] = [
  {
    ts: "2026-05-04T05:42Z",
    actor1: "RUS",
    actor2: "UKR",
    goldstein: -8.0,
    tone: -7.2,
    url: "https://example.com/event1",
  },
  {
    ts: "2026-05-04T03:18Z",
    actor1: "ISR",
    actor2: "HEZ",
    goldstein: -5.0,
    tone: -4.1,
    url: "https://example.com/event2",
  },
  {
    ts: "2026-05-04T01:55Z",
    actor1: "USA",
    actor2: "CHN",
    goldstein: 1.2,
    tone: 0.8,
    url: "https://example.com/event3",
  },
];

export default async function GeopoliticsPage() {
  const data = await apiGet<GeopoliticsHeatmap>("/v1/geopolitics/heatmap?hours=24", {
    revalidate: 30,
  });
  const apiOnline = isLive(data);
  const liveCountries = apiOnline ? data.countries.slice(0, 10) : [];
  const nEvents = apiOnline ? data.n_events : null;
  const gprTotal = HOTSPOTS.reduce((s, h) => s + h.intensity * h.events_24h, 0);
  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <header className="mb-6 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Géopolitique · GPR + GDELT 2.0
          {nEvents !== null && (
            <span className="text-[var(--color-text-muted)]/70"> · {nEvents} events 24h</span>
          )}{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? "live" : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Géopolitique
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Suivi en temps réel des hotspots via{" "}
          <MetricTooltip
            term="GPR"
            definition="Geopolitical Risk Index (Caldara & Iacoviello, FRED). Indice quotidien du stress géopolitique mondial. Élevé = bid USD/gold, sell EUR/risk."
            glossaryAnchor="gpr"
            density="compact"
          >
            GPR
          </MetricTooltip>{" "}
          (FRED quotidien) + flux events{" "}
          <MetricTooltip
            term="GDELT 2.0"
            definition="Global Database of Events, Language, and Tone. Codifie chaque event news en (actor1, actor2, goldstein, tone). Goldstein < -5 = action conflictuelle forte."
            glossaryAnchor="gdelt"
            density="compact"
          >
            GDELT 2.0
          </MetricTooltip>{" "}
          (15-min refresh).
        </p>
      </header>

      <section className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat
          label="GPR composite (24h)"
          value={gprTotal.toFixed(1)}
          delta={1.4}
          bias="bear"
          sub="vs 30d avg"
        />
        <Stat
          label="Events Goldstein < -5"
          value={String(RECENT_EVENTS.filter((e) => e.goldstein < -5).length)}
          delta={1}
          bias="bear"
          sub="last 6h"
        />
        <Stat
          label="Hotspots actifs"
          value={String(HOTSPOTS.length)}
          delta={0}
          bias="neutral"
          sub="region count"
        />
      </section>

      <section className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Hotspots map · equirectangular (placeholder)
        </h2>
        <WorldMap hotspots={HOTSPOTS} />
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          Phase 2 Sprint : SVG equirectangular 2D (~3 kB).{" "}
          <span className="text-[var(--color-text-secondary)]">Sprint suivant</span> : migration{" "}
          <code className="font-mono">react-globe.gl</code> 3D avec dynamic import client (delta Q
          VISION_2026, ~250 kB bundle gated par intersection observer).
        </p>
      </section>

      {liveCountries.length > 0 && (
        <section className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Top countries · GDELT activity 24h (live)
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border-default)] text-left">
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Country
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Events
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Mean tone
                </th>
                <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Most-negative headline
                </th>
              </tr>
            </thead>
            <tbody>
              {liveCountries.map((c) => {
                const toneBias = c.mean_tone < -2 ? "bear" : c.mean_tone > 2 ? "bull" : "neutral";
                return (
                  <tr
                    key={c.country}
                    className="border-b border-[var(--color-border-subtle)] last:border-b-0"
                  >
                    <td className="py-2 pr-3 font-mono">{c.country}</td>
                    <td className="py-2 pr-3 font-mono tabular-nums text-[var(--color-text-primary)]">
                      {c.count}
                    </td>
                    <td className="py-2 pr-3">
                      <BiasIndicator
                        bias={toneBias}
                        value={c.mean_tone}
                        unit="%"
                        variant="compact"
                        size="xs"
                        ariaLabel={`Mean tone ${c.mean_tone}, ${toneBias}`}
                      />
                    </td>
                    <td className="py-2 text-xs text-[var(--color-text-secondary)]">
                      {c.most_negative_title ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
        <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Recent GDELT events · Goldstein scale
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border-default)] text-left">
              <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Time
              </th>
              <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Actor 1
              </th>
              <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Actor 2
              </th>
              <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Goldstein
              </th>
              <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Tone
              </th>
            </tr>
          </thead>
          <tbody>
            {RECENT_EVENTS.map((e, i) => {
              const bias = e.goldstein < -3 ? "bear" : e.goldstein > 3 ? "bull" : "neutral";
              return (
                <tr
                  key={i}
                  className="border-b border-[var(--color-border-subtle)] last:border-b-0"
                >
                  <td className="py-2 pr-3 font-mono text-xs text-[var(--color-text-muted)]">
                    {new Date(e.ts).toLocaleTimeString("fr-FR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="py-2 pr-3 font-mono">{e.actor1}</td>
                  <td className="py-2 pr-3 font-mono">{e.actor2}</td>
                  <td className="py-2 pr-3">
                    <BiasIndicator
                      bias={bias}
                      value={e.goldstein}
                      unit="%"
                      variant="compact"
                      size="xs"
                      ariaLabel={`Goldstein: ${e.goldstein}, ${bias}`}
                    />
                  </td>
                  <td className="py-2 font-mono tabular-nums text-[var(--color-text-secondary)]">
                    {e.tone.toFixed(1)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  delta,
  bias,
  sub,
}: {
  label: string;
  value: string;
  delta: number;
  bias: "bull" | "bear" | "neutral";
  sub: string;
}) {
  return (
    <article className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-3xl tabular-nums text-[var(--color-text-primary)]">
          {value}
        </span>
        <BiasIndicator bias={bias} value={delta} unit="%" variant="compact" size="sm" />
      </div>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{sub}</p>
    </article>
  );
}

function WorldMap({ hotspots }: { hotspots: Hotspot[] }) {
  // Equirectangular projection: lon ∈ [-180, 180] → x ∈ [0, W]; lat ∈ [-90, 90] → y ∈ [0, H]
  const W = 800;
  const H = 320;
  const project = (lat: number, lon: number) => ({
    x: ((lon + 180) / 360) * W,
    y: ((90 - lat) / 180) * H,
  });
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label={`World map with ${hotspots.length} active geopolitical hotspots`}
      className="block"
    >
      {/* Frame */}
      <rect
        x="0"
        y="0"
        width={W}
        height={H}
        fill="var(--color-bg-elevated)"
        stroke="var(--color-border-subtle)"
      />
      {/* Equator + prime meridian */}
      <line
        x1="0"
        y1={H / 2}
        x2={W}
        y2={H / 2}
        stroke="var(--color-border-subtle)"
        strokeDasharray="4 4"
      />
      <line
        x1={W / 2}
        y1="0"
        x2={W / 2}
        y2={H}
        stroke="var(--color-border-subtle)"
        strokeDasharray="4 4"
      />

      {hotspots.map((h) => {
        const p = project(h.lat, h.lon);
        const r = 6 + h.intensity * 12;
        return (
          <g key={h.id}>
            <circle
              cx={p.x}
              cy={p.y}
              r={r}
              fill="var(--color-bear)"
              fillOpacity="0.25"
              stroke="var(--color-bear)"
              strokeWidth="1.5"
            />
            <circle cx={p.x} cy={p.y} r="3" fill="var(--color-bear)" />
            <text
              x={p.x + r + 4}
              y={p.y + 4}
              fontSize="11"
              fontFamily="var(--font-mono)"
              fill="var(--color-text-primary)"
            >
              {h.region}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
