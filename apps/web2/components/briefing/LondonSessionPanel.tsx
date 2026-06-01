"use client";

/**
 * LondonSessionPanel — §6.2 (owner CAPITAL point) — surfaces the LIVE
 * `GET /v1/london-session/{asset}` read : how the asset traded during the
 * LONDON MORNING (the session before / into the NY open), to calibrate the
 * upcoming NY-session view. Polls every 60s while the tab is visible (Page
 * Visibility API), mirroring `<PreviousSessionContextPanel>` (origin-zone)
 * + `<FreshDataBanner>`.
 *
 * ADR-017 boundary : the direction / activity labels describe HOW LONDON
 * TRADED THIS MORNING — a geometric read, NEVER a directional signal for the
 * NY session. The panel is calibration CONTEXT for the trader's own decision.
 *
 * Doctrine #11 calibrated honesty : the API returns 404 when there's no
 * usable London window (no bars OR < 30 bars). The panel renders an explicit
 * honest-absence pane rather than fabricating a read.
 *
 * Doctrine #5 (RSC client-boundary) : THIN view ; derived logic + FR copy
 * live in `lib/londonSession.ts` (pure module).
 */

import { useEffect, useState } from "react";

import { m } from "motion/react";

import {
  LONDON_ACTIVITY_LABEL_FR,
  LONDON_ACTIVITY_TONE,
  LONDON_DIRECTION_HINT_FR,
  LONDON_DIRECTION_LABEL_FR,
  LONDON_DIRECTION_TONE,
  RATIO_DISPLAY_CAP,
  classifyLondonActivity,
  formatFreshness,
  formatPrice,
  formatRatio,
  formatSignedPrice,
  freshnessLabel,
  londonAbsenceCopy,
  londonCalibrationHint,
  type LondonDirectionKey,
} from "@/lib/londonSession";

interface LondonSessionOut {
  asset: string;
  session_date: string;
  is_today: boolean;
  open_price: number;
  high: number;
  low: number;
  close: number;
  range_abs: number;
  net_change: number;
  direction: LondonDirectionKey;
  bar_count: number;
  avg_range: number | null;
  range_ratio: number | null;
  computed_at_utc: string;
  provenance: "practitioner_stamp";
}

type State =
  | { status: "loading" }
  | { status: "absent" }
  | { status: "ready"; data: LondonSessionOut }
  | { status: "error" };

const POLL_INTERVAL_MS = 60_000;

async function fetchLondonSession(asset: string, signal: AbortSignal): Promise<State> {
  try {
    const res = await fetch(`/v1/london-session/${encodeURIComponent(asset)}`, {
      signal,
      cache: "no-store",
    });
    if (res.status === 404) return { status: "absent" };
    if (!res.ok) return { status: "error" };
    const data: LondonSessionOut = await res.json();
    return { status: "ready", data };
  } catch (e) {
    if ((e as DOMException)?.name === "AbortError") return { status: "loading" };
    return { status: "error" };
  }
}

interface Props {
  asset: string;
}

export function LondonSessionPanel({ asset }: Props) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const tick = async () => {
      const next = await fetchLondonSession(asset, controller.signal);
      if (alive) setState(next);
    };
    void tick();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void tick();
    }, POLL_INTERVAL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      controller.abort();
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [asset]);

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      role="region"
      aria-labelledby="london-session-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2
            id="london-session-heading"
            className="font-display text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Séance de Londres — pour calibrer New&nbsp;York
          </h2>
          {state.status === "ready" && (
            <span className="text-xs text-[var(--color-text-muted)]">
              {formatFreshness(state.data.computed_at_utc)}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          Comment {asset} a tradé ce matin à Londres — la séance qui mène à l&apos;ouverture de New
          York. Un point d&apos;appui pour ta lecture, pas un signal.
        </p>
      </header>

      <div className="px-6 py-5">
        {state.status === "loading" && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Chargement de la séance de Londres…
          </p>
        )}

        {state.status === "error" && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Service indisponible momentanément.
          </p>
        )}

        {state.status === "absent" && (
          <div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              <span className="font-semibold text-[var(--color-text-primary)]">
                {londonAbsenceCopy(asset).title}
              </span>{" "}
              — {londonAbsenceCopy(asset).body}
            </p>
          </div>
        )}

        {state.status === "ready" && <LondonReady data={state.data} />}
      </div>
    </m.section>
  );
}

function LondonReady({ data }: { data: LondonSessionOut }) {
  const activity = classifyLondonActivity(data.range_ratio);
  const ratioPct =
    data.range_ratio !== null
      ? Math.min(Math.max(data.range_ratio, 0), RATIO_DISPLAY_CAP) / RATIO_DISPLAY_CAP
      : null;
  // Baseline (1.0× = typical morning) marker position on the meter.
  const baselinePct = (1.0 / RATIO_DISPLAY_CAP) * 100;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
          {freshnessLabel(data.is_today, data.session_date)}
        </span>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span
            className={`font-display text-2xl tracking-tight ${LONDON_DIRECTION_TONE[data.direction]}`}
          >
            {LONDON_DIRECTION_LABEL_FR[data.direction]}
          </span>
          {activity && (
            <span className={`text-sm font-medium ${LONDON_ACTIVITY_TONE[activity]}`}>
              {LONDON_ACTIVITY_LABEL_FR[activity]}
            </span>
          )}
        </div>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {LONDON_DIRECTION_HINT_FR[data.direction]}
        </p>
      </div>

      {/* Activity meter — this morning's range vs the typical London morning. */}
      {ratioPct !== null && (
        <div
          role="img"
          aria-label={`Range de ce matin : ${formatRatio(data.range_ratio)} la moyenne des 5 dernières séances de Londres.`}
        >
          <div className="mb-1 flex items-baseline justify-between text-xs text-[var(--color-text-muted)]">
            <span>Activité vs séance typique</span>
            <span className="font-mono tabular-nums text-[var(--color-text-secondary)]">
              {formatRatio(data.range_ratio)}
            </span>
          </div>
          <div className="relative h-2 overflow-hidden rounded-full bg-[var(--color-bg-surface)]/60 ring-1 ring-[var(--color-border-subtle)]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--color-accent-1)] to-[var(--color-accent-2)] transition-[width] duration-500"
              style={{ width: `${ratioPct * 100}%` }}
            />
            {/* 1.0× baseline tick — "typical morning" reference. */}
            <div
              className="absolute top-0 h-full w-px bg-[var(--color-text-muted)]/70"
              style={{ left: `${baselinePct}%` }}
              aria-hidden="true"
            />
          </div>
          <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
            Le repère vertical = une séance « normale » (1×). À droite = plus agitée que
            d&apos;habitude.
          </p>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/30 p-4 text-sm sm:grid-cols-3">
        <Stat label="Ouverture" value={formatPrice(data.open_price)} />
        <Stat label="Clôture" value={formatPrice(data.close)} />
        <Stat
          label="Variation"
          value={formatSignedPrice(data.net_change)}
          tone={LONDON_DIRECTION_TONE[data.direction]}
        />
        <Stat label="Haut" value={formatPrice(data.high)} />
        <Stat label="Bas" value={formatPrice(data.low)} />
        <Stat label="Range" value={formatPrice(data.range_abs)} />
      </dl>

      <p className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/20 px-4 py-3 text-sm text-[var(--color-text-secondary)]">
        <span className="font-semibold text-[var(--color-text-primary)]">
          À surveiller à l&apos;open NY :
        </span>{" "}
        {londonCalibrationHint(data.direction, activity)}
      </p>

      <p className="text-xs text-[var(--color-text-muted)]">
        Lecture factuelle de la matinée de Londres ({data.bar_count} minutes), jamais un signal de
        direction pour la session de New York · contexte d&apos;aide à la décision, pas un signal
        d&apos;achat ou de vente.
      </p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">{label}</dt>
      <dd className={`font-mono tabular-nums ${tone ?? "text-[var(--color-text-primary)]"}`}>
        {value}
      </dd>
    </div>
  );
}
