// TodaySessionPulse — Tier 4 r123 panel surfacing today's LIVE intraday
// calibration on the primary `/briefing/[asset]` page (ADR-099
// §Implementation(r123)). Closes the Axis-1 GAP : the briefing page had
// `BriefingHeader` decorative Sparklines, `VolumePanel` activity bars,
// `HourlyVolReport` 30-day seasonality — but NO panel surfacing "what is
// the market doing TODAY since open, vs typical for these elapsed hours".
//
// Aligns with Eliot's 2026-05-20-morning POINT FONDAMENTAL :
//   - "Reset complet quotidien" → renders ONLY today's bars (filter by
//     Paris-date boundary on the LATEST bar) ; the H2 carries the FR
//     long-form date label ("Aujourd'hui · jeudi 20 mai") so the date
//     itself is the no-carry-over-d'hier freshness anchor (ui Important-2).
//   - "Session de Londres en cours" → the london_range_bp tile surfaces
//     live London-window stats (Paris hour ≥ 9, DST-safe by construction
//     since London-Paris offset = 1h year-round).
//   - "Anticipation lucide par profondeur" → the tempo label cross-
//     references today's realized range against the 30-day p75 seasonality
//     baseline ; the inline meter visualizes the ratio against 1.0×
//     baseline (ui Important-3) — ADR-017 descriptive, never predictive.
//   - "Calibré pour NY" → positioned AFTER BriefingHeader, BEFORE
//     VerdictBanner → live tape FIRST, then synthesis (Pass-2 narrative
//     + Pass-6 scenarios + bias direction with the live context anchored).
//
// Pure presentational, RSC-safe (NO "use client" — pure SSR-rendered SVG,
// per the lesson-#5 RSC-leak discipline + the r120/VolumePanel pattern).
// Reuses the existing microchart SSOT (`linScale`, `svgCoord`, `xLinear`)
// — NO new coord-math, doctrine-#9 ledger UNCHANGED.
//
// r123 post-review apply-set (doctrine #14 1-pass review):
//   C-1 — `--color-accent-amber` (undefined) → `--color-warn` (the
//         actually-existing amber token at globals.css:263), restoring
//         the breakout/active visual distinction (ui Critical + a11y
//         SHOULD-FIX-1 concordant 2-of-3).
//   I-1 — removed the state pill (was duplicating the global
//         <SessionStatus> chip at page.tsx:230 — same labels, different
//         cadence ; single source of truth = the chip).
//   I-2 — H2 carries the FR long-form Paris date label (pulse.today_paris_label).
//   I-3 — thin inline meter under tempo_ratio (visual reference to 1.0×).
//   N-2 — dashed baseline at open_price in the mini area chart (frames
//         the bull/bear tone with a visible anchor).
//   N-3 — dropped the redundant delta_bp display (delta_pct is sufficient).
//   N-4 — empty-state mirrors the VolumePanel header+border-b shell.

import type { SessionPulse } from "@/lib/sessionPulse";
import { linScale, svgCoord, xLinear } from "@/lib/microchart";

/** Format a price by asset magnitude — 5 decimals for FX (EUR_USD,
 * GBP_USD), 3 for XAU (around 2000), 2 for indices (SPX/NAS around 5000).
 * Asset-symbol-agnostic : magnitude alone determines the decimal count. */
function formatPrice(price: number): string {
  if (!Number.isFinite(price)) return "—";
  if (Math.abs(price) >= 100) return price.toFixed(2);
  if (Math.abs(price) >= 10) return price.toFixed(3);
  return price.toFixed(5);
}

/** Tempo label → human FR + tone (visual cue mapping). `breakout` → warn
 * (amber, the volatility-alert tone — high vol = caution warranted,
 * NOT directional) ; `active` → neutral text-primary (above-typical
 * range but no directional implication — trader R28 NIT applied here :
 * the previous bull-green leaned subtly directional). `trending` →
 * text-secondary ; range-bound / compressed → muted. */
const TEMPO_FR: Record<NonNullable<SessionPulse["tempo_label"]>, string> = {
  breakout: "Breakout",
  active: "Active",
  trending: "Tendance",
  "range-bound": "Range",
  compressed: "Compressé",
};

const TEMPO_TONE: Record<
  NonNullable<SessionPulse["tempo_label"]>,
  "warn" | "primary" | "secondary" | "muted"
> = {
  breakout: "warn",
  active: "primary",
  trending: "secondary",
  "range-bound": "muted",
  compressed: "muted",
};

const TONE_COLOR: Record<"bull" | "bear" | "warn" | "primary" | "secondary" | "muted", string> = {
  bull: "var(--color-bull)",
  bear: "var(--color-bear)",
  warn: "var(--color-warn)",
  primary: "var(--color-text-primary)",
  secondary: "var(--color-text-secondary)",
  muted: "var(--color-text-muted)",
};

interface TodaySessionPulseProps {
  asset: string;
  pulse: SessionPulse | null;
}

export function TodaySessionPulse({ asset, pulse }: TodaySessionPulseProps) {
  if (!pulse) {
    // N-4 — mirror the sibling glass-panel empty-state shell (header
    // with border-b + body), so the page reads consistently when the
    // pulse is unavailable (e.g., fresh deploy + intraday API cold).
    return (
      <section
        aria-labelledby="today-pulse-heading"
        className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      >
        <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
          <h2
            id="today-pulse-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Aujourd&apos;hui
          </h2>
          <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Lecture en temps réel · recalibrée chaque session · pas de carry-over d&apos;hier
          </p>
        </header>
        <p className="px-6 py-8 text-center text-sm text-[var(--color-text-muted)]">
          Pas de barres intraday récentes pour {asset.replace("_", "/")} — pulse indisponible.
        </p>
      </section>
    );
  }

  const deltaTone = pulse.delta_pct >= 0 ? "bull" : "bear";
  const deltaSign = pulse.delta_pct >= 0 ? "+" : "";
  const tempoTone = pulse.tempo_label ? TEMPO_TONE[pulse.tempo_label] : "muted";
  const tempoFr = pulse.tempo_label ? TEMPO_FR[pulse.tempo_label] : "Indisponible";

  // Mini area chart of today's closes since open. Uses microchart SSOT
  // (linScale + xLinear + svgCoord) — NO new coord math.
  const closes = pulse.closes_today;
  const W = 480;
  const H = 64;
  const PAD_X = 4;
  const PAD_Y = 6;
  const n = closes.length;
  const yDataMin = Math.min(...closes, pulse.open_price);
  const yDataMax = Math.max(...closes, pulse.open_price);
  // Inverted y-range (top of screen = small y) ; r108 inverted-range
  // linScale idiom, NOT a new primitive. Domain includes the open_price
  // so the N-2 baseline dashed line is always inside the plot area.
  const sy = linScale(yDataMin, yDataMax, H - PAD_Y, PAD_Y);
  const points = closes
    .map((c, i) => {
      const x = xLinear(i, n, W, PAD_X);
      const y = sy(c);
      return `${svgCoord(x)},${svgCoord(y)}`;
    })
    .join(" ");
  const baseY = H - PAD_Y;
  const areaPoints =
    n > 1
      ? `${svgCoord(xLinear(0, n, W, PAD_X))},${svgCoord(baseY)} ${points} ${svgCoord(
          xLinear(n - 1, n, W, PAD_X),
        )},${svgCoord(baseY)}`
      : "";
  const pathColor = TONE_COLOR[deltaTone];
  // N-2 — dashed line at today's open_price so the bull/bear tone has a
  // visible anchor. text-muted color, strokeDasharray gentle.
  const openY = sy(pulse.open_price);

  // I-3 — thin inline meter visualizing tempo_ratio against the 1.0×
  // baseline (the "typical" marker). Width capped at 2× for visual
  // consistency ; ratio > 2 visually maxes the bar (the numeric ratio
  // text below still shows the raw value).
  const meterRatio = pulse.tempo_ratio ?? 0;
  const meterFillPct = Math.min(meterRatio / 2, 1) * 100;
  const meterColor = TONE_COLOR[tempoTone];

  const ariaLabel = `Lecture intraday ${asset.replace("_", "/")} — ouverture ${pulse.open_time_paris} Paris à ${formatPrice(
    pulse.open_price,
  )}, prix actuel ${formatPrice(pulse.current_price)} (${deltaSign}${pulse.delta_pct.toFixed(2)}%), range jour ${pulse.range_bp.toFixed(0)} points de base${
    pulse.london_range_bp !== null
      ? `, Londres ${pulse.london_range_bp.toFixed(0)} points de base`
      : ""
  }, tempo ${tempoFr.toLowerCase()}${
    pulse.tempo_ratio !== null ? ` (${pulse.tempo_ratio.toFixed(1)}× vs typique 30 jours)` : ""
  }.`;

  return (
    <section
      aria-labelledby="today-pulse-heading"
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h2
          id="today-pulse-heading"
          className="font-serif text-2xl text-[var(--color-text-primary)]"
        >
          Aujourd&apos;hui ·{" "}
          <span className="text-[var(--color-text-secondary)]">{pulse.today_paris_label}</span>
        </h2>
        <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Lecture en temps réel · recalibrée chaque session · pas de carry-over d&apos;hier
        </p>
      </header>

      <div className="grid grid-cols-2 gap-x-6 gap-y-4 px-6 py-5 sm:grid-cols-4">
        <div className="flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Ouverture {pulse.open_time_paris} Paris
          </p>
          <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
            {formatPrice(pulse.open_price)}
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Maintenant {pulse.current_time_paris}
          </p>
          <p className="font-mono text-2xl tabular-nums" style={{ color: TONE_COLOR[deltaTone] }}>
            {formatPrice(pulse.current_price)}
          </p>
          <p className="font-mono text-xs tabular-nums" style={{ color: TONE_COLOR[deltaTone] }}>
            {deltaSign}
            {pulse.delta_pct.toFixed(2)}%
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Range jour
          </p>
          <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
            {pulse.range_bp.toFixed(0)} bp
          </p>
          <p className="font-mono text-xs tabular-nums text-[var(--color-text-secondary)]">
            {formatPrice(pulse.high)} / {formatPrice(pulse.low)}
          </p>
          {pulse.london_range_bp !== null ? (
            <p className="font-mono text-[11px] tabular-nums text-[var(--color-text-muted)]">
              Londres {pulse.london_range_bp.toFixed(0)} bp
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Tempo
          </p>
          <p className="font-mono text-2xl tabular-nums" style={{ color: meterColor }}>
            {tempoFr}
          </p>
          {pulse.tempo_ratio !== null ? (
            <>
              <p className="font-mono text-xs tabular-nums text-[var(--color-text-secondary)]">
                {pulse.tempo_ratio.toFixed(1)}× vs p75 30 j
              </p>
              <svg
                viewBox="0 0 100 6"
                preserveAspectRatio="none"
                role="img"
                aria-label={`Meter tempo ${pulse.tempo_ratio.toFixed(1)} fois la baseline 1× (30 jours)`}
                className="mt-1 block h-1.5 w-full max-w-[140px]"
              >
                <rect x={0} y={0} width={100} height={6} rx={3} fill="var(--color-bg-base)" />
                <rect
                  x={0}
                  y={0}
                  width={meterFillPct}
                  height={6}
                  rx={3}
                  fill={meterColor}
                  opacity={0.85}
                />
                {/* 1.0× baseline marker (the "typical" anchor) at 50%
                    width since the meter caps at 2× = 100%. */}
                <line
                  x1={50}
                  y1={0}
                  x2={50}
                  y2={6}
                  stroke="var(--color-text-muted)"
                  strokeWidth={0.5}
                  strokeDasharray="1 1"
                />
              </svg>
            </>
          ) : (
            <p className="font-mono text-[11px] text-[var(--color-text-muted)]">
              Comparaison 30 j indisponible
            </p>
          )}
        </div>
      </div>

      <div className="px-4 pb-4">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={ariaLabel}
          className="block h-16 w-full"
        >
          <title>{`Lecture intraday ${asset.replace("_", "/")}`}</title>
          {n > 1 ? (
            <>
              {/* N-2 — dashed baseline at today's open_price */}
              <line
                x1={0}
                y1={svgCoord(openY)}
                x2={W}
                y2={svgCoord(openY)}
                stroke="var(--color-text-muted)"
                strokeWidth="0.5"
                strokeDasharray="2 3"
                opacity="0.55"
              />
              <polygon points={areaPoints} fill={pathColor} fillOpacity="0.12" />
              <polyline
                points={points}
                fill="none"
                stroke={pathColor}
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            </>
          ) : (
            <text
              x={W / 2}
              y={H / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="11"
              fill="var(--color-text-muted)"
            >
              1 barre — chemin indisponible
            </text>
          )}
        </svg>
      </div>

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[10px] text-[var(--color-text-muted)]">
        Contexte pré-trade — comportement réel du jour vs typique 30 j · pas un signal (ADR-017)
      </p>
    </section>
  );
}
