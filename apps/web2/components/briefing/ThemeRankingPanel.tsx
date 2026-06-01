"use client";

/**
 * ThemeRankingPanel — r186 N1 — Eliot Fathom transcript étape 1
 * verbatim materialised : « identifier le thème sous-jacent du marché ».
 * Surfaces the LIVE r185 endpoint `GET /v1/theme-dominant` output on
 * `/briefing/[asset]` as a top-banner contextual pane.
 *
 * Asset-agnostic : the theme drives the GLOBAL macro regime (not per-
 * asset). One panel renders on every priority asset briefing — Eliot
 * sees "Thème dominant aujourd'hui : Politique monétaire 95% (FOMC)"
 * as a CONTEXT layer his NY 14h-20h position-taking must respect.
 *
 * ADR-017 boundary : descriptive labels for the GLOBAL macro regime
 * driver, NEVER directional bias for any asset. The panel renders
 * "le marché est driven by monetary_policy" as a context pane.
 *
 * Doctrine #11 calibrated honesty : the API returns 404 when no driver
 * meets the 0.5 dominance threshold (mixed/insufficient inputs). The
 * panel renders an explicit honest-absence prose pane in that case
 * rather than fabricating a forced ranking.
 *
 * Doctrine #5 (RSC client-boundary) : this is a THIN view ; all
 * derived logic + FR copy maps live in `lib/themeDominant.ts` (pure
 * module, server-safe, unit-testable without motion/react in node).
 */

import { useEffect, useState } from "react";

import { m } from "motion/react";

import {
  THEME_DRIVER_HINT_FR,
  THEME_DRIVER_KEYS,
  THEME_DRIVER_LABEL_FR,
  THEME_DRIVER_TONE,
  formatFreshness,
  formatStrengthPct,
  type ThemeDriverKey,
} from "@/lib/themeDominant";

interface ThemeDominantOut {
  top_theme: ThemeDriverKey;
  top_theme_strength_pct: number;
  secondary_themes: ThemeDriverKey[];
  driver_strengths_pct: Record<ThemeDriverKey, number>;
  computed_at_utc: string;
  provenance: "practitioner_stamp";
}

type State =
  | { status: "loading" }
  | { status: "absent" }
  | { status: "ready"; data: ThemeDominantOut }
  | { status: "error" };

const POLL_INTERVAL_MS = 60_000;

async function fetchTheme(signal: AbortSignal): Promise<State> {
  try {
    const res = await fetch("/v1/theme-dominant", {
      signal,
      cache: "no-store",
    });
    if (res.status === 404) return { status: "absent" };
    if (!res.ok) return { status: "error" };
    const data: ThemeDominantOut = await res.json();
    return { status: "ready", data };
  } catch (e) {
    if ((e as DOMException)?.name === "AbortError") return { status: "loading" };
    return { status: "error" };
  }
}

export function ThemeRankingPanel() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const tick = async () => {
      const next = await fetchTheme(controller.signal);
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
  }, []);

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      role="region"
      aria-labelledby="theme-ranking-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2
            id="theme-ranking-heading"
            className="font-display text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Thème dominant aujourd&apos;hui
          </h2>
          {state.status === "ready" && (
            <span className="text-xs text-[var(--color-text-muted)]">
              {formatFreshness(state.data.computed_at_utc)}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          Quel grand moteur dirige le marché en ce moment.
        </p>
      </header>

      <div className="px-6 py-5">
        {state.status === "loading" && (
          <p className="text-sm text-[var(--color-text-muted)]">Chargement du thème dominant…</p>
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
                Aucun thème ne domine clairement
              </span>{" "}
              le marché en ce moment. Tous les moteurs restent faibles — signaux mitigés ou
              insuffisants.
            </p>
            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
              Aucun classement n&apos;est forcé quand rien ne ressort vraiment. Calibre ta prise de
              risque sans miser sur un thème dominant aujourd&apos;hui.
            </p>
          </div>
        )}

        {state.status === "ready" && (
          <div className="space-y-4">
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline gap-3">
                <span
                  className={`font-display text-2xl tracking-tight ${THEME_DRIVER_TONE[state.data.top_theme]}`}
                >
                  {THEME_DRIVER_LABEL_FR[state.data.top_theme]}
                </span>
                <span className="font-mono text-3xl tabular-nums text-[var(--color-text-primary)]">
                  {formatStrengthPct(state.data.top_theme_strength_pct)}
                </span>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {THEME_DRIVER_HINT_FR[state.data.top_theme]}
              </p>
            </div>

            {state.data.secondary_themes.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                  Moteurs secondaires
                </p>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {state.data.secondary_themes.map((key) => (
                    <li
                      key={key}
                      className="rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/60 px-3 py-1 text-xs"
                    >
                      <span className={`font-semibold ${THEME_DRIVER_TONE[key]}`}>
                        {THEME_DRIVER_LABEL_FR[key]}
                      </span>{" "}
                      <span className="font-mono tabular-nums text-[var(--color-text-secondary)]">
                        {formatStrengthPct(state.data.driver_strengths_pct[key])}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <details className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/30 p-3">
              <summary className="cursor-pointer text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                Détail des 8 moteurs
              </summary>
              <ul className="mt-3 space-y-1">
                {THEME_DRIVER_KEYS.map((key) => (
                  <li key={key} className="flex items-baseline justify-between gap-3 text-xs">
                    <span className={THEME_DRIVER_TONE[key]}>{THEME_DRIVER_LABEL_FR[key]}</span>
                    <span className="font-mono tabular-nums text-[var(--color-text-secondary)]">
                      {formatStrengthPct(state.data.driver_strengths_pct[key])}
                    </span>
                  </li>
                ))}
              </ul>
            </details>

            <p className="text-xs text-[var(--color-text-muted)]">
              Description du décor de marché global, jamais un signal de direction pour un actif ·
              contexte d&apos;aide à la décision, pas un signal d&apos;achat ou de vente.
            </p>
          </div>
        )}
      </div>
    </m.section>
  );
}
