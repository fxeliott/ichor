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

import { freshnessSubtitleVariant } from "@/lib/freshness";
import { linScale, svgCoord, xLinear } from "@/lib/microchart";
import { getNyWindowStatus, type NyWindowKind } from "@/lib/nyWindow";
import type { SessionPulse } from "@/lib/sessionPulse";

/** Format a price by asset magnitude — 5 decimals for FX (EUR_USD,
 * GBP_USD), 3 for XAU (around 2000), 2 for indices (SPX/NAS around 5000).
 * Asset-symbol-agnostic : magnitude alone determines the decimal count. */
function formatPrice(price: number): string {
  if (!Number.isFinite(price)) return "—";
  if (Math.abs(price) >= 100) return price.toFixed(2);
  if (Math.abs(price) >= 10) return price.toFixed(3);
  return price.toFixed(5);
}

/** r129 — format the staleness of a calibration timestamp into a FR phrase
 * (ADR-104 data-honesty banner). The reference time is `Date.now()` on
 * the server during the SSR pass. The briefing page is rendered per
 * request (the page's `apiGet` calls default to `no-store` which marks
 * the route dynamic per Next.js 15 rules — `next build` shows the route
 * as `ƒ Dynamic`), so the staleness is fresh-as-of-the-request. Quantize
 * to the 5-min ISR cache of `/v1/tempo-thresholds` means the banner is
 * live-ish ±5 min ; not real-time but well within human-readable
 * staleness resolution. No hydration mismatch risk because the component
 * is pure SSR (no `"use client"`, the calculation runs ONCE server-side
 * and the resulting string is baked into the HTML).
 *
 * FR phrasing : "à l'instant" (clock-skew negative) / "aujourd'hui" /
 * "hier" / "il y a N jours" / "il y a 30+ jours" (capped — beyond a
 * month the cron has likely failed ; the cap is honest ceiling, NOT a
 * deception). `window_days` from the metadata is the actual rolling
 * window — the JSDoc avoids the literal "90j" since the cron's
 * `--window-days` flag is parameterized (trader Y-1 doc drift guard).
 *
 * Returns `null` if the input is unparseable — caller renders no banner. */
function formatCalibrationAge(computedAtIso: string): string | null {
  const computedMs = Date.parse(computedAtIso);
  if (!Number.isFinite(computedMs)) return null;
  const nowMs = Date.now();
  const deltaMs = nowMs - computedMs;
  if (deltaMs < 0) {
    // Clock skew between SSR and DB ; treat as fresh.
    return "à l'instant";
  }
  const days = Math.floor(deltaMs / 86_400_000);
  if (days === 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 30) return `il y a ${days} jours`;
  return "il y a 30+ jours";
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

/** r132 — NY 13-16h Paris window status badge ; r133 — US holiday
 * awareness wired (closes the r132 honest-scope gap "calendrier US
 * fériés non géré") + per-asset-class label routing per trader R28
 * MF-1 honest-scope fix (FX/XAU continue trading globally on US
 * holidays — "Marché US fermé" overclaims closure for those assets,
 * so the badge routes to "Férié US · … · liquidité réduite" except
 * for SPX500/NAS100 which are genuinely closed).
 *
 * Renders the `getNyWindowStatus(new Date(), asset)` output. Pure RSC
 * server-component (no `"use client"`, no `useEffect`) — `new Date()`
 * evaluates at SSR request time, the resulting string is baked into
 * the HTML. The briefing route is `ƒ Dynamic` (no SSG bake-in risk,
 * mirror of r129 formatCalibrationAge SSR-stamping pattern).
 *
 * Tone palette (post-r132 reviews — trader Y-2 + ui-designer CONCORDANT
 * amber-overload fix : `active` uses primary text NOT amber, since
 * amber is already overloaded on tempo `breakout` + r131 velocity
 * `rapid`/`major` ; reserving amber for genuinely anomalous states
 * preserves its semantic weight) :
 *   - `active`  → `--color-text-primary` (full-weight neutral, signals
 *                 "operational LIVE" via contrast vs muted siblings)
 *   - `pre`     → `--color-text-secondary` (slate-350 countdown)
 *   - `post`    → `--color-text-muted` (slate-500 passive, closed)
 *   - `weekend` → `--color-text-muted` (no NY today)
 *   - `holiday` → `--color-text-muted` (r133 ; same muted tone as
 *                 weekend — semantically equivalent "no NY today" state,
 *                 just with the holiday name surfaced. NOT amber : the
 *                 closed-market is the EXPECTED state on a holiday, not
 *                 anomalous behavior worth alerting on.)
 *
 * Status role : the `<p>` carries `role="status"` (a11y SF-1
 * concordant r130 empty-state doctrine + r131 — "this is a state
 * readout" not body prose) ; no `aria-live` because RSC-only update
 * cadence makes it dead-code per request.
 *
 * Wrap behaviour (r133 SC 1.4.10 fix — CONCORDANT ui-designer
 * IMPORTANT-2 + a11y SHOULD-FIX-1) : `whitespace-nowrap` is kept ONLY
 * for the short time-bracket states (pre/active/post = 22-32 chars,
 * fit on a single line in narrow viewports). For weekend/holiday the
 * `nowrap` is DROPPED so the longer labels ("Marché US fermé · Martin
 * Luther King Jr. Day" = 43 chars + "Férié US · … · liquidité réduite"
 * = up to 65 chars) can wrap to a 2nd line on 320 CSS px viewports
 * + at 200% browser zoom (SC 1.4.4). `leading-tight` keeps the wrapped
 * line spacing visually grouped with the single-line states.
 *
 * Mission centrale axis 3 closure : Eliot SEES "T-2h avant NY 13h"
 * on every briefing rendered today, didn't see it pre-r132. Surfaced
 * in BOTH the no-pulse early-return branch AND the main render path
 * (code-reviewer MF-1 + ui-designer CONCORDANT empty-state parity —
 * NY context is INDEPENDENT of intraday pulse availability).
 *
 * r133 closes the "US holidays not detected" honest-scope gap : the
 * obsolete "calendrier US fériés non géré" micro-text is DROPPED ; the
 * badge now reads "Marché US fermé · Memorial Day" (SPX/NAS) or
 * "Férié US · Memorial Day · liquidité réduite" (EUR/GBP/XAU) on
 * NYSE/Nasdaq full-day holidays. Drift-guard vitest pins 2026+2027
 * fixtures against the canonical Python algorithm in
 * `apps/api/.../services/market_session.us_market_holidays(year)`. */
const NY_TONE_COLOR: Record<NyWindowKind, string> = {
  active: "var(--color-text-primary)",
  pre: "var(--color-text-secondary)",
  post: "var(--color-text-muted)",
  weekend: "var(--color-text-muted)",
  holiday: "var(--color-text-muted)",
};

/** Per-kind wrap policy (r133 SC 1.4.10 + ui-designer IMPORTANT-2
 * CONCORDANT fix). Short time-bracket states stay single-line ; longer
 * weekend/holiday labels are allowed to wrap. */
const NY_WRAP_CLASS: Record<NyWindowKind, string> = {
  active: "whitespace-nowrap",
  pre: "whitespace-nowrap",
  post: "whitespace-nowrap",
  weekend: "leading-tight",
  holiday: "leading-tight",
};

function NyWindowBadge({ asset }: { asset?: string }) {
  const status = getNyWindowStatus(new Date(), asset);
  return (
    <p
      role="status"
      className={`mt-2 text-[11px] tracking-wide ${NY_WRAP_CLASS[status.kind]}`}
      style={{ color: NY_TONE_COLOR[status.kind] }}
    >
      {status.label}
    </p>
  );
}

/** HONEST FRESHNESS GATE for the "temps réel / recalibrée" claim.
 * The unconditional "Lecture en temps réel · recalibrée chaque session ·
 * pas de carry-over d'hier" wording is a LIE when the session card is
 * stale (engine down → yesterday's card served). Gate it on the card's
 * freshness : show the live wording ONLY when `fresh` ; when `stale`
 * show an honest amber variant ; when `absent` stay neutral-muted.
 * State is conveyed by TEXT + colour, never colour alone (WCAG 1.4.1). */
function FreshnessSubtitle({
  asset,
  cardGeneratedAt,
}: {
  asset?: string;
  cardGeneratedAt: string | null;
}) {
  // Compose card-freshness with the market-open state — same getNyWindowStatus
  // source as the NyWindowBadge above, so the two NEVER contradict. Weekend
  // closes all assets ; a US holiday closes only equity index (SPX/NAS) —
  // FX/XAU keep trading globally so they stay on the freshness-only gate.
  // Fixes the "Lecture en temps réel" claim showing over "Marchés fermés ·
  // week-end" on a fresh weekend card (the 2026-05-29 contradiction class).
  const ny = getNyWindowStatus(new Date(), asset);
  const isEquity = asset === "SPX500_USD" || asset === "NAS100_USD";
  const marketClosed = ny.kind === "weekend" || (ny.kind === "holiday" && isEquity);
  const { variant, ageLabel } = freshnessSubtitleVariant(cardGeneratedAt, marketClosed);

  if (variant === "market_closed") {
    const closedLabel = ny.kind === "weekend" ? "Week-end · marchés fermés" : "Marché US fermé";
    return (
      <p
        className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
        role="status"
      >
        {closedLabel} · dernière lecture {ageLabel} · recalibrée à la réouverture
      </p>
    );
  }
  if (variant === "stale") {
    return (
      <p
        className="mt-1 text-[10px] font-semibold uppercase tracking-widest text-[var(--color-warn)]"
        role="status"
      >
        Lecture de la session précédente · non recalibrée aujourd&apos;hui · {ageLabel}
      </p>
    );
  }
  if (variant === "live") {
    return (
      <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Lecture en temps réel · recalibrée chaque session · pas de carry-over d&apos;hier
      </p>
    );
  }
  // absent — no card timestamp ; stay honestly neutral (do not claim live).
  return (
    <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
      Pas de lecture de session disponible
    </p>
  );
}

interface TodaySessionPulseProps {
  asset: string;
  pulse: SessionPulse | null;
  /** r-freshness — the session card's `generated_at` (or null). Gates the
   * "temps réel / recalibrée" subtitle so a stale card never claims live.
   * Threaded from the page; the pulse itself has no card-generation
   * timestamp (its date anchor is the latest intraday bar, a distinct
   * signal). */
  cardGeneratedAt: string | null;
}

export function TodaySessionPulse({ asset, pulse, cardGeneratedAt }: TodaySessionPulseProps) {
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
          {/* r132 code-reviewer MF-1 + ui-designer CONCORDANT empty-
              state parity : NY window context is INDEPENDENT of pulse
              availability (Eliot still needs the cible marker when the
              intraday API is cold). Same NyWindowBadge in BOTH branches. */}
          <NyWindowBadge asset={asset} />
          <FreshnessSubtitle asset={asset} cardGeneratedAt={cardGeneratedAt} />
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

  // r129 — calibration age computed ONCE (code-reviewer N-1 extract-to-const).
  // null when `tempo_metadata` is null OR the ISO is unparseable. The banner
  // in the footer reads from `calibrationAge` ; on `null` the banner doesn't
  // render (progressive enhancement, doctrine #11 honest silent absence).
  const calibrationAge = pulse.tempo_metadata
    ? formatCalibrationAge(pulse.tempo_metadata.computed_at)
    : null;

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
        {/* r132 — NY 13-16h Paris window UI marker placed DIRECTLY
            under the H2 (operational state next to date anchor, per
            ui-designer hierarchy fix : the time-critical operational
            state ranks higher than the meta-process subtitle). The
            10px uppercase subtitle moves to position 3 since it's
            descriptive about the panel's lifecycle, not operational.
            r133 : `asset` prop threaded through for per-class label
            routing on US holidays (equity → "Marché US fermé" ;
            FX/XAU → "Férié US · liquidité réduite") per trader R28
            MF-1 honest-scope fix. */}
        <NyWindowBadge asset={asset} />
        <FreshnessSubtitle asset={asset} cardGeneratedAt={cardGeneratedAt} />
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

      <div className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        <p className="text-[10px] text-[var(--color-text-muted)]">
          Contexte pré-trade — comportement réel du jour vs typique 30 j · pas un signal (ADR-017)
        </p>
        {/* r129 — ADR-104 data-honesty staleness banner (closes the r127
            trader NIT). Placed in the footer alongside the ADR-017
            disclaimer because the staleness applies to the THRESHOLDS
            used by the whole panel (provenance-with-provenance), not the
            tempo cell alone. Renders only when `calibrationAge` is
            non-null (progressive enhancement, doctrine #11 honest silent
            absence — never replaces missing metadata with a fabricated
            fresh state). Concordant 2-reviewer YELLOW resolution (ui-
            designer placement + mobile-wrap + a11y SC 1.4.4 size). */}
        {calibrationAge && pulse.tempo_metadata ? (
          <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
            Calibration des seuils · {calibrationAge} · n={pulse.tempo_metadata.sample_size} ·
            fenêtre {pulse.tempo_metadata.window_days} j
          </p>
        ) : null}
      </div>
    </section>
  );
}
