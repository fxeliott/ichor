"use client";

/**
 * PreviousSessionContextPanel — r187 G5 — Eliot Fathom transcript §V
 * verbatim materialised : « savoir d'où vient le mouvement de la
 * session précédente, son zone d'origine, son sens, ses hauts et bas ».
 * Surfaces the LIVE r184 endpoint `GET /v1/origin-zone/{asset}` output
 * on `/briefing/[asset]`.
 *
 * Asset-specific : the snapshot is per-asset (FX vs equity have
 * different session-zone activity patterns). Polls every 60s while
 * tab visible (Page Visibility API mirror r186 ThemeRankingPanel +
 * r171b DxyCorrelationPanel + r140 FreshDataBanner pattern).
 *
 * ADR-017 boundary : geometric/probabilistic labels for the PREVIOUS
 * session, NEVER directional bias for the CURRENT session. The panel
 * renders « session précédente Londres haussière 36 pips » as a
 * CONTEXT pane Eliot's NY 14h-20h position-taking respects.
 *
 * Doctrine #11 calibrated honesty : the API returns 404 when no bars
 * in window OR dominant zone bar_count < 30 (Cohen 1988 §3.3). The
 * panel renders an explicit honest-absence prose pane in that case
 * rather than fabricating a forced snapshot.
 *
 * Doctrine #5 (RSC client-boundary) : THIN view ; derived logic + FR
 * copy maps live in `lib/originZone.ts` (pure module).
 */

import { useEffect, useState } from "react";

import { m } from "motion/react";

import {
  ORIGIN_DIRECTION_HINT_FR,
  ORIGIN_DIRECTION_LABEL_FR,
  ORIGIN_DIRECTION_TONE,
  SESSION_ZONE_HINT_FR,
  SESSION_ZONE_LABEL_FR,
  formatFreshness,
  formatPrice,
  formatWindowBound,
  type OriginDirectionKey,
  type SessionZoneKey,
} from "@/lib/originZone";

interface OriginZoneOut {
  asset: string;
  session_zone: SessionZoneKey;
  direction: OriginDirectionKey;
  high_price: number;
  low_price: number;
  range_observed: number;
  bar_count: number;
  start_utc: string;
  end_utc: string;
  computed_at_utc: string;
  provenance: "practitioner_stamp";
}

type State =
  | { status: "loading" }
  | { status: "absent" }
  | { status: "ready"; data: OriginZoneOut }
  | { status: "error" };

const POLL_INTERVAL_MS = 60_000;

async function fetchOriginZone(asset: string, signal: AbortSignal): Promise<State> {
  try {
    const res = await fetch(`/v1/origin-zone/${encodeURIComponent(asset)}`, {
      signal,
      cache: "no-store",
    });
    if (res.status === 404) return { status: "absent" };
    if (!res.ok) return { status: "error" };
    const data: OriginZoneOut = await res.json();
    return { status: "ready", data };
  } catch (e) {
    if ((e as DOMException)?.name === "AbortError") return { status: "loading" };
    return { status: "error" };
  }
}

interface Props {
  asset: string;
}

export function PreviousSessionContextPanel({ asset }: Props) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const tick = async () => {
      const next = await fetchOriginZone(asset, controller.signal);
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
      aria-labelledby="previous-session-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2
            id="previous-session-heading"
            className="font-display text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Session précédente — zone d&apos;origine
          </h2>
          {state.status === "ready" && (
            <span className="text-xs text-[var(--color-text-muted)]">
              {formatFreshness(state.data.computed_at_utc)}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          D&apos;où vient le mouvement dominant des dernières 24 h sur {asset}.
        </p>
      </header>

      <div className="px-6 py-5">
        {state.status === "loading" && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Chargement de la zone d&apos;origine…
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
                Contexte session précédente indisponible
              </span>{" "}
              — pas assez de données dans la fenêtre des dernières 24 h (week-end / jour férié OU
              trop peu d&apos;activité dans la zone dominante).
            </p>
            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
              Aucune donnée n&apos;est inventée. Lis l&apos;absence comme un manque réel de
              contexte.
            </p>
          </div>
        )}

        {state.status === "ready" && (
          <div className="space-y-4">
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline gap-3">
                <span className="font-display text-2xl tracking-tight text-[var(--color-text-primary)]">
                  {SESSION_ZONE_LABEL_FR[state.data.session_zone]}
                </span>
                <span
                  className={`font-display text-2xl tracking-tight ${ORIGIN_DIRECTION_TONE[state.data.direction]}`}
                >
                  {ORIGIN_DIRECTION_LABEL_FR[state.data.direction]}
                </span>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {SESSION_ZONE_HINT_FR[state.data.session_zone]}
              </p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {ORIGIN_DIRECTION_HINT_FR[state.data.direction]}
              </p>
            </div>

            <dl className="grid grid-cols-2 gap-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/30 p-4 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  High
                </dt>
                <dd className="font-mono tabular-nums text-[var(--color-text-primary)]">
                  {formatPrice(state.data.high_price)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  Low
                </dt>
                <dd className="font-mono tabular-nums text-[var(--color-text-primary)]">
                  {formatPrice(state.data.low_price)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  Range observé
                </dt>
                <dd className="font-mono tabular-nums text-[var(--color-text-primary)]">
                  {formatPrice(state.data.range_observed)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  Points de données
                </dt>
                <dd className="font-mono tabular-nums text-[var(--color-text-primary)]">
                  {state.data.bar_count}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  Fenêtre UTC
                </dt>
                <dd className="font-mono tabular-nums text-[var(--color-text-secondary)]">
                  {formatWindowBound(state.data.start_utc)} →{" "}
                  {formatWindowBound(state.data.end_utc)}
                </dd>
              </div>
            </dl>

            <p className="text-xs text-[var(--color-text-muted)]">
              Photo factuelle de la session passée, jamais un signal de direction pour la session en
              cours · contexte d&apos;aide à la décision, pas un signal d&apos;achat ou de vente.
            </p>
          </div>
        )}
      </div>
    </m.section>
  );
}
